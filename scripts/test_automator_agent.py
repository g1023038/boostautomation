"""
The test automator agent: given a Jira test case, it writes a pytest test
under mobile-tests/, actually RUNS it against the real app on LambdaTest,
reads the real failure if there is one, fixes its own code, and repeats --
it does not open a PR on a test it has never seen pass. This is what
generate_script.py's one-shot "write code and hope" approach was missing:
a one-shot LLM call can produce code that looks right and still breaks on
the first run (every bug found this session -- the cardholder-name field,
the KFC naming mismatch, the stale-element races -- only ever showed up by
actually running something, never by reading the code).

Tools given to the agent: read_file (repo context), write_test_file
(mobile-tests/test_*.py only), run_pytest (costs real LambdaTest device
time -- the agent is told to use it to verify, not to explore blindly),
git_commit_and_push, open_pr. MAX_ITERATIONS bounds the loop so a confused
agent can't burn device minutes or tool calls indefinitely.

Usage: same inputs as generate_script.py (TEST_KEY, TEST_TYPE from the Jira
Test issue), but only wired up for TEST_TYPE=mobile so far -- that's the
one target with a real, runnable test suite to iterate against.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

from jira_client import JiraClient

REPO_ROOT = Path(__file__).parent.parent
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-5-5"  # pinned -- see llm_client.py for why
MAX_ITERATIONS = 12
PYTEST_TIMEOUT_SECONDS = 600

SYSTEM_PROMPT = """You are the test automator agent for the Booost Android app \
(com.sanlam.boost.ppe). You write a pytest test under mobile-tests/ for the \
test case you're given, then you RUN it for real against the live app on a \
LambdaTest device and read the actual result -- you do not stop after writing \
code that merely looks correct.

Ground rules, all learned the hard way by a human running this suite manually:
- Read mobile-tests/ARCHITECTURE.md first, before anything else. It explains \
  the composable-actions design (small verbs chained per test, the state dict, \
  when to reuse vs. write a new action) -- the code alone doesn't make the \
  intent obvious.
- Read mobile-tests/boost_actions.py next. Reuse its action_* functions \
  (action_login, action_goto_product, action_set_payment, action_checkout, \
  action_voucher_details, action_recheck_balance, ...) -- never write driver \
  setup, login, or navigation from scratch. The app is Jetpack Compose with no \
  resource-ids anywhere, so every locator is by visible text.
- Read mobile-tests/test_purchases.py for the exact pattern other tests follow, \
  including the data-driven scenario file at \
  testdata/reference/booost_buy_purchase_scenarios.json.
- The pytest fixtures `driver` and `base_state` already exist in \
  mobile-tests/conftest.py -- your test function just takes them as parameters. \
  Never write Appium/LambdaTest connection code; that's already handled.
- Known gotchas: Peach Payments' "add new card" form needs 4 fields including \
  Card Holder Name, not 3. The Purchase complete screen's balance badge can show \
  a stale value -- use action_recheck_balance, never assert a delta directly off \
  that screen. Booost Buy has no shared cart. Catalog tile names and detail-page \
  titles can differ (e.g. "KFC_Brand" tile vs "KFC_Display" detail title) -- \
  navigation needs the tile name.
- Use type_into_element() (in boost_actions.py) instead of raw find+click+send_keys \
  when filling any field -- a cached element reference can go stale if the screen \
  re-renders in between, and this has broken tests for real before.
- Read mobile-tests/TEST_INDEX.md first, always. It's the coverage index -- what's \
  already implemented (don't duplicate it), known app findings worth reusing, and \
  a gap list of what's genuinely still missing. After you successfully commit a \
  passing test, add a row for it to TEST_INDEX.md in the same commit.

Your loop: write the test with write_test_file, run it with run_pytest, read the \
actual output. If it fails, read the real error (not a guess) and fix the code. \
Repeat. Only call git_commit_and_push and then open_pr once run_pytest has shown \
the test passing. If you are still failing after several honest attempts, open \
the PR anyway with the failure clearly explained in the body rather than silently \
giving up or claiming success it hasn't earned.

After open_pr returns the PR URL, call update_jira_ticket with that URL --
this is what makes the ticket traceable end to end (PR link comment,
"automated" label, status moves to In Progress). Do this every time a PR is
opened, not just on success.

Note: a separate, human-triggered Rovo agent also automates tests in this
same Jira project, coordinating via the same "automated" label (it checks
for the label before writing code, same as this agent does before you're
even invoked). You won't see it in your tools, but it's why the label check
in main() happens before you're started at all -- don't second-guess or
bypass it."""

TOOLS = [
    {
        "name": "read_file",
        "description": "Read a file from the repo for context, e.g. mobile-tests/boost_actions.py or an existing test.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Repo-relative path"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_test_file",
        "description": "Write or overwrite a pytest test file. Path must be under mobile-tests/ and the filename must start with test_.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_pytest",
        "description": ("Run pytest against the real app on a LambdaTest device for the given test "
                         "expression (e.g. 'test_new_thing.py::test_x' or 'test_new_thing.py'). "
                         "Returns exit code, stdout, and stderr. This costs real device minutes -- "
                         "use it to verify a specific change, not to explore blindly."),
        "input_schema": {
            "type": "object",
            "properties": {"test_expr": {"type": "string"}},
            "required": ["test_expr"],
        },
    },
    {
        "name": "git_commit_and_push",
        "description": "Commit the new/changed test file to a new branch and push it. Call only after run_pytest has shown it passing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "branch": {"type": "string"},
                "message": {"type": "string"},
                "path": {"type": "string", "description": "The test file path to commit"},
            },
            "required": ["branch", "message", "path"],
        },
    },
    {
        "name": "open_pr",
        "description": "Open a GitHub PR for the branch created by git_commit_and_push. Returns the PR URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "branch": {"type": "string"},
                "title": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["branch", "title", "body"],
        },
    },
    {
        "name": "update_jira_ticket",
        "description": ("Comment the PR URL on the Jira test ticket, add the 'automated' label, and "
                         "transition it to In Progress. Call once, after open_pr returns a URL."),
        "input_schema": {
            "type": "object",
            "properties": {
                "test_key": {"type": "string"},
                "pr_url": {"type": "string"},
            },
            "required": ["test_key", "pr_url"],
        },
    },
]


def tool_read_file(path):
    p = REPO_ROOT / path
    if not p.exists():
        return f"ERROR: {path} does not exist"
    return p.read_text()


def tool_write_test_file(path, content):
    if not path.startswith("mobile-tests/") or not Path(path).name.startswith("test_"):
        return "ERROR: path must be under mobile-tests/ and the filename must start with test_"
    p = REPO_ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"wrote {path} ({len(content)} bytes)"


def tool_run_pytest(test_expr):
    result = subprocess.run(
        ["python", "-m", "pytest", test_expr, "-v"],
        cwd=REPO_ROOT / "mobile-tests",
        capture_output=True, text=True, timeout=PYTEST_TIMEOUT_SECONDS,
    )
    return (f"exit_code={result.returncode}\n"
            f"--- stdout (tail) ---\n{result.stdout[-4000:]}\n"
            f"--- stderr (tail) ---\n{result.stderr[-2000:]}")


def tool_git_commit_and_push(branch, message, path):
    subprocess.run(["git", "checkout", "-b", branch], cwd=REPO_ROOT, check=True)
    subprocess.run(["git", "add", path], cwd=REPO_ROOT, check=True)
    subprocess.run(["git", "-c", "user.email=qa-automation@bot", "-c", "user.name=qa-automation-bot",
                     "commit", "-m", message], cwd=REPO_ROOT, check=True)
    subprocess.run(["git", "push", "-u", "origin", branch], cwd=REPO_ROOT, check=True)
    return f"pushed branch {branch}"


def tool_open_pr(branch, title, body):
    full_body = body + "\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"
    result = subprocess.run(
        ["gh", "pr", "create", "--title", title, "--body", full_body, "--base", "main", "--head", branch],
        cwd=REPO_ROOT, check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()  # gh pr create prints the PR URL to stdout


def tool_update_jira_ticket(test_key, pr_url):
    jira = JiraClient()
    jira.add_comment(test_key, f"Automation PR opened: {pr_url}")

    issue = jira.get_issue(test_key, fields="labels")
    labels = issue["fields"].get("labels") or []
    if "automated" not in labels:
        jira.update_fields(test_key, {"labels": labels + ["automated"]})

    try:
        jira.transition_issue(test_key, "In Progress")
    except ValueError as exc:
        # Transition name can differ per workflow scheme -- don't fail the
        # whole run over it, the comment + label are the important part.
        return f"commented + labeled {test_key}, but could not transition: {exc}"
    return f"updated {test_key}: PR comment, 'automated' label, transitioned to In Progress"


DISPATCH = {
    "read_file": lambda i: tool_read_file(i["path"]),
    "write_test_file": lambda i: tool_write_test_file(i["path"], i["content"]),
    "run_pytest": lambda i: tool_run_pytest(i["test_expr"]),
    "git_commit_and_push": lambda i: tool_git_commit_and_push(i["branch"], i["message"], i["path"]),
    "open_pr": lambda i: tool_open_pr(i["branch"], i["title"], i["body"]),
    "update_jira_ticket": lambda i: tool_update_jira_ticket(i["test_key"], i["pr_url"]),
}


def call_claude(messages):
    r = requests.post(ANTHROPIC_URL, headers={
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }, json={
        "model": MODEL,
        "max_tokens": 8192,
        "system": SYSTEM_PROMPT,
        "tools": TOOLS,
        "messages": messages,
    })
    r.raise_for_status()
    return r.json()


def run_agent(task_description):
    messages = [{"role": "user", "content": task_description}]

    for iteration in range(MAX_ITERATIONS):
        response = call_claude(messages)
        messages.append({"role": "assistant", "content": response["content"]})

        tool_uses = [b for b in response["content"] if b["type"] == "tool_use"]
        if not tool_uses:
            print(f"[iteration {iteration}] agent finished without a tool call -- stopping")
            break

        tool_results = []
        ticket_updated = False
        for block in tool_uses:
            print(f"[iteration {iteration}] tool: {block['name']}({block['input']})")
            try:
                result = DISPATCH[block["name"]](block["input"])
            except Exception as exc:
                result = f"ERROR: {exc}"
            print(f"[iteration {iteration}] result: {str(result)[:500]}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block["id"],
                "content": str(result),
            })
            if block["name"] == "update_jira_ticket":
                ticket_updated = True

        messages.append({"role": "user", "content": tool_results})
        if ticket_updated:
            print("Jira ticket updated -- agent run complete")
            break
    else:
        print(f"Hit MAX_ITERATIONS ({MAX_ITERATIONS}) without opening a PR -- stopping")


def main():
    test_key = os.environ["TEST_KEY"]
    jira = JiraClient()
    issue = jira.get_issue(test_key, fields="summary,description,labels")

    # Coordination gate with Rovo's human-triggered "Test Automation Engineer"
    # agent, which automates the same LRQA project and uses this same label:
    # it checks for "automated" before writing anything and sets it after a
    # successful PR. This has to check first too, or the two systems can race
    # to automate the same ticket -- setting the label afterward alone isn't
    # enough, since both could start before either one sets it.
    if "automated" in (issue["fields"].get("labels") or []):
        print(f"{test_key} already has the 'automated' label -- skipping, already handled")
        return

    steps_text = JiraClient.extract_text(issue["fields"].get("description")) or issue["fields"]["summary"]

    task = (f"Write and verify a pytest test for Xray test case {test_key}:\n\n{steps_text}\n\n"
            f"Save it as mobile-tests/test_{test_key.lower()}.py. Name the branch "
            f"auto-tests/{test_key} and reference {test_key} in a comment near the top "
            f"of the test file, for consistency with the other agent that also automates "
            f"this Jira project.")
    run_agent(task)


if __name__ == "__main__":
    sys.exit(main() or 0)

import os
import subprocess
import sys
from pathlib import Path

from jira_client import JiraClient
from llm_client import call_llm

MOBILE_SYSTEM_PROMPT = """You write pytest test functions for the Booost Android app \
(com.sanlam.boost.ppe), reusing the existing action library at \
mobile-tests/boost_actions.py -- you are the agent that writes this test because \
no developer needs to; ground every test in that library's real, already-verified \
conventions instead of inventing new locators or a new login flow:

- The app is Jetpack Compose with no resource-ids or testTags anywhere. Every \
  locator in the library (and every one you write) is by visible text via \
  tap_by_text(driver, text, contains=True/False, timeout=...).
- Never write driver setup, login, or navigation from scratch. Import and call \
  the existing action_* functions: action_login, action_get_balance, \
  action_goto_product, action_start_checkout, action_set_payment, \
  action_checkout, action_voucher_details, action_recheck_balance. Each takes \
  (driver, state) where state is a plain dict -- see mobile-tests/test_purchases.py \
  for the exact pattern (the _run_purchase helper chaining them).
- payment_method is one of: points | card_saved | card_new | split. For \
  card_new, state needs card_number/card_exp (the test cards are in \
  testdata/reference/ppe_payment_and_vas.json: success card 4200000000000091, \
  decline card 4012001037461114, both exp 12/28 cvc 123) plus card_holder_name \
  (Peach Payments requires it -- a real bug was found when it was omitted).
- Known app bug: the Purchase complete screen's own balance badge can show a \
  stale pre-purchase value for a few seconds. Never assert a balance delta \
  directly off that screen -- call action_recheck_balance first (it navigates \
  away and re-reads), then assert against state["balance_settled"].
- The pytest fixtures `driver` and `base_state` already exist in \
  mobile-tests/conftest.py (handles Appium/LambdaTest session setup, test \
  identity from env vars) -- test functions just take them as parameters.
- Booost Buy (More > Booost Buy > Vouchers) has no shared cart -- every \
  product is its own independent Buy now -> checkout -> pay; don't write a \
  multi-item cart flow, it doesn't exist in this app.

Output ONLY the test file's code, no commentary, no markdown fences. Write \
one or more clearly-named test_ functions, not a single monolithic test."""

SYSTEM_PROMPTS = {
    "api": ("You write API test scripts for this project's conventions (requests + pytest). "
            "Output ONLY the code file contents, no commentary, no markdown fences."),
    "ui": ("You write Playwright test scripts for this project's conventions, configured to run "
           "against LambdaTest using its capabilities object. "
           "Output ONLY the code file contents, no commentary, no markdown fences."),
    "mobile": MOBILE_SYSTEM_PROMPT,
}

# Placeholder field ID -- replace once the real "Test Data Key" custom field
# is created in Jira (see rovo-handoff/xray-custom-fields.md).
TEST_DATA_KEY_FIELD = "customfield_10050"


def main():
    test_key = os.environ["TEST_KEY"]
    test_type = os.environ["TEST_TYPE"]

    jira = JiraClient()
    issue = jira.get_issue(test_key, fields=f"summary,description,{TEST_DATA_KEY_FIELD}")
    steps_text = JiraClient.extract_text(issue["fields"].get("description")) or issue["fields"]["summary"]
    test_data_key = issue["fields"].get(TEST_DATA_KEY_FIELD) or "none"

    prompt = f"Test case ({test_key}):\n{steps_text}\n\nTest data key: {test_data_key}"
    code = call_llm(SYSTEM_PROMPTS[test_type], prompt)

    target_dir = {"api": "api-tests", "mobile": "mobile-tests"}.get(test_type, "app-tests/tests")
    ext = "spec.ts" if test_type == "ui" else "py"
    prefix = "test_" if test_type in ("api", "mobile") else ""  # pytest's default discovery needs this
    path = Path(target_dir) / f"{prefix}{test_key.lower()}.{ext}"
    path.write_text(code)

    branch = f"auto/{test_key.lower()}"
    subprocess.run(["git", "checkout", "-b", branch], check=True)
    subprocess.run(["git", "add", str(path)], check=True)
    subprocess.run(["git", "-c", "user.email=qa-automation@bot", "-c", "user.name=qa-automation-bot",
                     "commit", "-m", f"Add generated {test_type} test for {test_key}"], check=True)
    subprocess.run(["git", "push", "-u", "origin", branch], check=True)
    subprocess.run(["gh", "pr", "create", "--title", f"Automated {test_type} test: {test_key}",
                     "--body", f"Generated from approved Xray test {test_key}. Review before merge.",
                     "--base", "main"], check=True)


if __name__ == "__main__":
    sys.exit(main() or 0)

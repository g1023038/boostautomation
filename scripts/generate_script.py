import os
import subprocess
import sys
from pathlib import Path

from jira_client import JiraClient
from llm_client import call_llm

SYSTEM_PROMPTS = {
    "api": ("You write API test scripts for this project's conventions (requests + pytest). "
            "Output ONLY the code file contents, no commentary, no markdown fences."),
    "ui": ("You write Playwright test scripts for this project's conventions, configured to run "
           "against LambdaTest using its capabilities object. "
           "Output ONLY the code file contents, no commentary, no markdown fences."),
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

    target_dir = "api-tests" if test_type == "api" else "app-tests/tests"
    ext = "py" if test_type == "api" else "spec.ts"
    path = Path(target_dir) / f"{test_key.lower()}.{ext}"
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

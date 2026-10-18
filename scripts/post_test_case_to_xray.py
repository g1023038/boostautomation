import os
import re
import sys

from jira_client import JiraClient
from xray_client import XrayClient


def extract_gherkin_comment(jira, issue_key):
    for comment in reversed(jira.get_comments(issue_key)):
        text = JiraClient.extract_text(comment["body"])
        if "Scenario" in text or "Feature" in text:
            return text
    raise RuntimeError(f"No Gherkin draft found in comments on {issue_key}")


def main():
    issue_key = os.environ["TEST_ISSUE_KEY"]
    test_plan_key = os.environ.get("TEST_PLAN_KEY")

    jira = JiraClient()
    xray = XrayClient()

    gherkin = extract_gherkin_comment(jira, issue_key)
    # Tagging with the issue's own key tells Xray to update LRQA-123 in place
    # instead of creating a duplicate Test issue.
    if not re.search(rf"@{issue_key}\b", gherkin):
        gherkin = f"@{issue_key}\n{gherkin}"
    if not gherkin.lower().lstrip().startswith("feature"):
        gherkin = f"Feature: {issue_key}\n{gherkin}"

    result = xray.import_feature(gherkin, test_plan_key=test_plan_key)
    jira.add_comment(issue_key, "Posted to Xray as a structured test.")
    print(result)


if __name__ == "__main__":
    sys.exit(main() or 0)

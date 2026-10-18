import os
import sys

from jira_client import JiraClient
from llm_client import call_llm

SYSTEM_PROMPT = """You write Gherkin test scenarios for a QA team from an approved Jira test plan.
Output ONLY valid Gherkin (Feature + Scenario blocks), no commentary, no markdown fences.
Each scenario must be independently executable and cover one clear behavior from the plan."""


def main():
    test_plan_key = os.environ["TEST_PLAN_KEY"]
    project_key = os.environ["JIRA_PROJECT_KEY"]

    jira = JiraClient()
    plan = jira.get_issue(test_plan_key, fields="summary,description")
    plan_text = JiraClient.extract_text(plan["fields"].get("description")) or plan["fields"]["summary"]

    gherkin = call_llm(SYSTEM_PROMPT, f"Test plan:\n{plan_text}\n\nGenerate the test case scenarios.")

    issue_key = jira.create_issue(
        project_key=project_key,
        issue_type="Test",
        summary=f"[Draft] Generated from {test_plan_key}",
        description="Auto-generated draft. Pending QA review before this gets posted to Xray.",
    )
    jira.add_comment(issue_key, gherkin, as_code=True)
    jira.add_comment(test_plan_key, f"Draft test case generated: {issue_key}")

    print(f"Created draft test case {issue_key}")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(f"Draft test case created: {issue_key}\n")


if __name__ == "__main__":
    sys.exit(main() or 0)

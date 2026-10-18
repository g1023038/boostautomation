import glob
import os
import sys

from confluence_client import ConfluenceClient
from jira_client import JiraClient
from xray_client import XrayClient


def main():
    test_plan_key = os.environ["TEST_PLAN_KEY"]
    test_exec_key = os.environ.get("TEST_EXEC_KEY")
    report_glob = os.environ.get("JUNIT_REPORT_GLOB", "reports/**/*.xml")

    xray = XrayClient()
    reports = glob.glob(report_glob, recursive=True)
    if not reports:
        print("No reports found, nothing to publish")
        return

    last_result = None
    for report in reports:
        last_result = xray.import_execution_junit(report, test_exec_key=test_exec_key, test_plan_key=test_plan_key)
    print(last_result)

    failed = os.environ.get("RUN_STATUS") == "failure"
    if failed:
        jira = JiraClient()
        bug_key = jira.create_issue(
            project_key=os.environ["JIRA_PROJECT_KEY"],
            issue_type="Bug",
            summary=f"Automated test failure in {test_plan_key} run",
            description=f"See Xray execution for details. Run: {os.environ.get('GITHUB_RUN_URL', '')}",
        )
        print(f"Filed defect: {bug_key}")

    confluence = ConfluenceClient()
    confluence.upsert_page(
        space_key=os.environ["CONFLUENCE_SPACE_KEY"],
        title=f"Test results - {test_plan_key}",
        body_html=f"<p>Latest run: {'FAILED' if failed else 'PASSED'}. See Xray Test Plan {test_plan_key} for details.</p>",
    )


if __name__ == "__main__":
    sys.exit(main() or 0)

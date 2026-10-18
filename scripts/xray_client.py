import os
import requests

XRAY_BASE = "https://xray.cloud.getxray.app/api/v2"


class XrayClient:
    def __init__(self):
        self._token = None

    def _auth_token(self):
        if self._token:
            return self._token
        r = requests.post(f"{XRAY_BASE}/authenticate", json={
            "client_id": os.environ["XRAY_CLIENT_ID"],
            "client_secret": os.environ["XRAY_CLIENT_SECRET"],
        })
        r.raise_for_status()
        self._token = r.json().strip('"')
        return self._token

    def _headers(self):
        return {"Authorization": f"Bearer {self._auth_token()}"}

    def import_feature(self, feature_text, test_plan_key=None, project_key=None):
        # Creates a new Xray Test, or updates one in place if the feature text
        # is tagged with an existing issue key (e.g. "@LRQA-123" above the Scenario).
        params = {}
        if test_plan_key:
            params["testPlanKey"] = test_plan_key
        if project_key:
            params["projectKey"] = project_key
        files = {"file": ("generated.feature", feature_text, "text/plain")}
        r = requests.post(f"{XRAY_BASE}/import/feature", headers=self._headers(), params=params, files=files)
        r.raise_for_status()
        return r.json()

    def import_execution(self, payload):
        # Native JSON import. Include "testExecutionKey" in payload to update
        # an existing Test Execution in place instead of creating a new one.
        r = requests.post(f"{XRAY_BASE}/import/execution",
                           headers={**self._headers(), "Content-Type": "application/json"}, json=payload)
        r.raise_for_status()
        return r.json()

    def import_execution_junit(self, junit_xml_path, test_exec_key=None, test_plan_key=None):
        params = {}
        if test_exec_key:
            params["testExecKey"] = test_exec_key
        if test_plan_key:
            params["testPlanKey"] = test_plan_key
        with open(junit_xml_path, "rb") as f:
            files = {"file": (os.path.basename(junit_xml_path), f, "application/xml")}
            r = requests.post(f"{XRAY_BASE}/import/execution/junit", headers=self._headers(), params=params,
                               files=files)
        r.raise_for_status()
        return r.json()

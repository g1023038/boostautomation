import os
import requests


class JiraClient:
    def __init__(self):
        self.base_url = os.environ["JIRA_BASE_URL"].rstrip("/")
        self.auth = (os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"])

    def get_issue(self, issue_key, fields=None):
        params = {"fields": fields} if fields else {}
        r = requests.get(f"{self.base_url}/rest/api/3/issue/{issue_key}", auth=self.auth, params=params)
        r.raise_for_status()
        return r.json()

    def get_comments(self, issue_key):
        r = requests.get(f"{self.base_url}/rest/api/3/issue/{issue_key}/comment", auth=self.auth)
        r.raise_for_status()
        return r.json()["comments"]

    def create_issue(self, project_key, issue_type, summary, description, extra_fields=None):
        fields = {
            "project": {"key": project_key},
            "issuetype": {"name": issue_type},
            "summary": summary,
            "description": self._adf_text(description),
        }
        if extra_fields:
            fields.update(extra_fields)
        r = requests.post(f"{self.base_url}/rest/api/3/issue", auth=self.auth, json={"fields": fields})
        r.raise_for_status()
        return r.json()["key"]

    def update_fields(self, issue_key, fields):
        r = requests.put(f"{self.base_url}/rest/api/3/issue/{issue_key}", auth=self.auth, json={"fields": fields})
        r.raise_for_status()

    def add_comment(self, issue_key, body, as_code=False, language="gherkin"):
        payload = {"body": self._adf_code(body, language) if as_code else self._adf_text(body)}
        r = requests.post(f"{self.base_url}/rest/api/3/issue/{issue_key}/comment", auth=self.auth, json=payload)
        r.raise_for_status()

    def transition_issue(self, issue_key, transition_name):
        r = requests.get(f"{self.base_url}/rest/api/3/issue/{issue_key}/transitions", auth=self.auth)
        r.raise_for_status()
        match = next((t for t in r.json()["transitions"] if t["name"].lower() == transition_name.lower()), None)
        if not match:
            raise ValueError(f"No transition named '{transition_name}' available for {issue_key}")
        r = requests.post(f"{self.base_url}/rest/api/3/issue/{issue_key}/transitions", auth=self.auth,
                           json={"transition": {"id": match["id"]}})
        r.raise_for_status()

    @staticmethod
    def _adf_text(text):
        return {"type": "doc", "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}

    @staticmethod
    def _adf_code(code, language):
        return {"type": "doc", "version": 1,
                "content": [{"type": "codeBlock", "attrs": {"language": language},
                              "content": [{"type": "text", "text": code}]}]}

    @staticmethod
    def extract_text(adf):
        if not adf:
            return ""
        parts = []

        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "text":
                    parts.append(node.get("text", ""))
                for child in node.get("content", []):
                    walk(child)
            elif isinstance(node, list):
                for n in node:
                    walk(n)

        walk(adf)
        return "\n".join(parts)

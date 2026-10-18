import os
import requests


class ConfluenceClient:
    def __init__(self):
        self.base_url = os.environ["JIRA_BASE_URL"].rstrip("/")
        self.auth = (os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"])

    def find_page(self, space_key, title):
        r = requests.get(f"{self.base_url}/wiki/rest/api/content", auth=self.auth,
                          params={"spaceKey": space_key, "title": title, "expand": "version"})
        r.raise_for_status()
        results = r.json()["results"]
        return results[0] if results else None

    def upsert_page(self, space_key, title, body_html, parent_id=None):
        existing = self.find_page(space_key, title)
        payload = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "body": {"storage": {"value": body_html, "representation": "storage"}},
        }
        if parent_id:
            payload["ancestors"] = [{"id": parent_id}]
        if existing:
            payload["version"] = {"number": existing["version"]["number"] + 1}
            r = requests.put(f"{self.base_url}/wiki/rest/api/content/{existing['id']}", auth=self.auth, json=payload)
        else:
            r = requests.post(f"{self.base_url}/wiki/rest/api/content", auth=self.auth, json=payload)
        r.raise_for_status()
        return r.json()

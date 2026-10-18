# Jira Automation rules to create

Three rules, each a straight "Send web request" action to GitHub's
`repository_dispatch` endpoint. No middleware, no GitHub webhook config needed
on the repo side -- `on: repository_dispatch` in the workflow files already
listens for these.

Replace `<OWNER>/<REPO>` and `<GITHUB_PAT>` in all three. The PAT only goes
into these rule configs -- it should not end up anywhere else (see main README).

---

## Rule 1 -- Test plan approved

- **Trigger:** Issue transitioned
  - Issue type: Test Plan
  - Status: → Approved
- **Action:** Send web request
  - URL: `https://api.github.com/repos/<OWNER>/<REPO>/dispatches`
  - Method: POST
  - Headers:
    - `Authorization: Bearer <GITHUB_PAT>`
    - `Accept: application/vnd.github+json`
    - `X-GitHub-Api-Version: 2022-11-28`
  - Body:
    ```json
    {
      "event_type": "test_plan_approved",
      "client_payload": {
        "test_plan_key": "{{issue.key}}"
      }
    }
    ```

## Rule 2 -- Draft test case approved

- **Trigger:** Issue transitioned
  - Issue type: Test
  - Status: Draft → Approved
- **Action:** Send web request (same URL/headers as above)
  - Body:
    ```json
    {
      "event_type": "draft_approved",
      "client_payload": {
        "test_issue_key": "{{issue.key}}",
        "test_plan_key": "{{issue.parent.key}}"
      }
    }
    ```
  - `{{issue.parent.key}}` assumes the draft is linked to its Test Plan as a
    parent/epic link -- if your scheme links them a different way (a custom
    field, or an "is tested by" issue link), swap in the right smart value.

## Rule 3 -- Xray test case approved (post-import, final sign-off)

- **Trigger:** Issue transitioned
  - Issue type: Test
  - Status: → Approved (this fires again, now on the Xray-structured version
    of the same issue -- same key, later in its life)
- **Action:** Send web request (same URL/headers as above)
  - Body:
    ```json
    {
      "event_type": "test_case_approved",
      "client_payload": {
        "test_key": "{{issue.key}}",
        "test_type": "api"
      }
    }
    ```
  - `test_type` needs to come from somewhere -- either a custom field on the
    Test issue ("Automation type": api/ui/perf) that you add alongside the
    Test Data Key field, or a label/component convention. Hardcoding "api"
    above is a placeholder; replace it with a smart value once that field
    exists.

---

## What to ask Rovo to do with this

Ask Rovo directly: "Can you create these three Jira Automation rules for me
in project <PROJECT_KEY>, using this trigger and action configuration?" and
paste the relevant rule block. If Rovo can't action Jira Automation config
changes directly (it may be read/suggest-only depending on permissions),
fall back to a Jira admin creating them by hand in
**Project settings → Automation** -- the config above is copy-pasteable
either way.

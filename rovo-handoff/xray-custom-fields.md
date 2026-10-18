# Custom fields to add to the Test issue type

Ask Rovo or your Jira admin to add these to the Test issue screen in the QA
project:

1. **Test Data Key** (short text field)
   - Holds the key into `testdata/reference/*.json` (e.g. `standard_user`)
     that this test case needs.
   - Once created, Jira will assign it a field ID like `customfield_10050`.
   - That exact ID needs to replace the placeholder `TEST_DATA_KEY_FIELD`
     constant at the top of `scripts/generate_script.py` -- it's currently a
     guess and will not work until corrected.

2. **Automation type** (select list: `api` / `ui` / `mobile` / `perf`)
   - `mobile` routes to `mobile-tests/`, built on Appium + `boost_actions.py`
     against the real Booost Android app; `ui` is the (currently unused)
     Playwright/web path.
   - Lets Jira Automation Rule 3 (see `jira-automation-rules.md`) know which
     codegen path to dispatch to, instead of the hardcoded `"api"` placeholder
     currently in that rule's request body.

Once both exist, two things need updating: the field ID constant in
`generate_script.py`, and the `test_type` value in Rule 3's JSON body (swap
the hardcoded string for `{{issue.fields.customfield_XXXXX.value}}`).

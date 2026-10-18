# QA automation pipeline

End-to-end: approved Jira test plan -> drafted test cases -> QA approval ->
posted to Xray -> QA approval -> generated automation script -> PR review ->
execution on LambdaTest/JMeter -> results published to Xray/Confluence/Jira.
Three human approval gates (test plan, test case, script/PR); everything else,
including publishing results, is automatic. No standing middleware service --
just Jira Automation rules and GitHub Actions workflows calling each system's
API directly.

## Layout

```
.github/workflows/      the 4 pipeline workflows (see below)
scripts/                shared API clients + the 4 pipeline entrypoints
api-tests/               generated + hand-written API tests (pytest)
app-tests/               generated + hand-written UI/app tests (Playwright, via LambdaTest)
performance/            JMeter .jmx plans (not wired into a workflow yet)
testdata/reference/     versioned, non-sensitive test fixtures
rovo-handoff/           exact configs to hand to Rovo or your Jira admin
```

## Pipeline flow

| Trigger | Workflow | What it does |
|---|---|---|
| Test Plan → Approved (Jira Automation Rule 1) | `generate-test-cases.yml` | Calls a pinned LLM, drafts Gherkin, creates a draft Jira Test issue |
| Draft Test → Approved (Jira Automation Rule 2) | `post-to-xray.yml` | Tags the draft with its own issue key, posts to Xray via Cucumber Feature Import -- updates the same issue in place |
| Xray Test → Approved (Jira Automation Rule 3) | `generate-script.yml` | Calls the LLM again to write the automation script, opens a PR |
| Push to `main` | `execute-tests.yml` | Runs API tests, runs UI/app tests on LambdaTest, publishes results to Xray + Confluence, files a Jira Bug on failure |

## Required GitHub Secrets

| Secret | Used by |
|---|---|
| `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY` | all Jira/Confluence calls (service account -- see `rovo-handoff/service-account-setup.md`) |
| `XRAY_CLIENT_ID`, `XRAY_CLIENT_SECRET` | Xray Cloud API auth |
| `ANTHROPIC_API_KEY` | test case + script generation (pinned model, see `scripts/llm_client.py`) |
| `LAMBDATEST_USERNAME`, `LAMBDATEST_ACCESS_KEY` | app-tests execution |
| `CONFLUENCE_SPACE_KEY` | results page target |
| `GITHUB_TOKEN` | automatic, already provided per workflow run -- just needs `permissions: contents: write, pull-requests: write`, already set in `generate-script.yml` |

The classic PAT you generated for `repository_dispatch` does **not** go in
this list -- it lives only in the Jira Automation rule configs
(`rovo-handoff/jira-automation-rules.md`), not in this repo.

## What's still open before this runs end to end

1. **Sample script not yet provided.** `app-tests/` and `api-tests/` are
   placeholders -- once you share an existing script, the LLM system prompts
   in `generate_script.py` and the Playwright config get rewritten to match
   your real locator/page-object conventions instead of generic boilerplate.
2. **`TEST_DATA_KEY_FIELD` in `generate_script.py` is a guessed field ID**
   (`customfield_10050`). Needs the real one once the field exists (see
   `rovo-handoff/xray-custom-fields.md`).
3. **`test_type` in Rule 3 is hardcoded to `"api"`.** Needs the "Automation
   type" custom field (same doc) before `ui`/`perf` cases route correctly.
4. **`execute-tests.yml` doesn't yet know which Test Plan/Execution a given
   push relates to** -- it currently publishes against
   `vars.DEFAULT_TEST_PLAN_KEY`, a single hardcoded fallback. Properly wiring
   this means threading the Test key through the PR (e.g. from the
   `auto/<test-key>` branch name `generate_script.py` already creates) into
   the execution-import step. Worth solving once the first real run proves
   the rest of the chain out.
5. **Performance (JMeter) has no workflow yet** -- `performance/README.md`
   describes the intended path (`.jtl` → JUnit → `publish_results.py`) but
   nothing executes it.

## Next step

Send the sample LambdaTest/app automation script whenever you have it --
that's what turns `app-tests/` from a placeholder into something real.

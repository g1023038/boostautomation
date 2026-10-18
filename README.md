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
.github/workflows/      the 4 pipeline workflows + run-purchase-test.yml (see below)
scripts/                shared API clients + the pipeline entrypoints
scripts/boost_actions.py       composable Booost Buy actions (login, get_balance, buy, add card...) -- primary
scripts/run_purchase_test.py   earlier single-flow purchase test, superseded by boost_actions.py
api-tests/               generated + hand-written API tests (pytest)
app-tests/               generated + hand-written UI/app tests (Playwright, via LambdaTest)
performance/            JMeter .jmx plans (not wired into a workflow yet)
testdata/reference/     versioned, non-sensitive test fixtures (incl. PPE payment/voucher test data)
rovo-handoff/           exact configs to hand to Rovo or your Jira admin
```

## Booost app (com.sanlam.boost.ppe) -- what's been verified live

Explored and tested directly against the real app on a LambdaTest Android
device (`lt://APP10160362051791552008064620`). Login: ID number + DOB
(auto-derived from the ID's first 6 digits) -> cellphone number -> 6-digit
OTP (any value accepted in PPE) -> location/notification permission screens.
No resource-ids anywhere -- it's a Compose app without `testTag`s set, so
every locator here is by visible text. Worth raising with the dev team:
automation would be far less fragile with `testTag`s on key elements.

Booost Buy (More > Booost Buy > Vouchers) has **no shared cart** -- every
product (fixed, like Plato Coffee, or variable-amount, like KFC_Display) is
an independent "Buy now" -> checkout -> pay. All 3 payment methods verified
end-to-end, including balance deltas and voucher provisioning (wiCode + QR
on the Order details screen, and the purchased item showing up under
Vouchers > Your vouchers):

| Method | How | Verified |
|---|---|---|
| Full Boost Points | default checkout state | yes, repeatedly, balance deltas all correct |
| Full card (saved card) | edit the "Pay with Booosts" amount box to 0 | yes -- routes to a Peach Payments modal (saved test card ****0042) then a 3DS "Demo Bank" mock challenge, Approve by default |
| Full card (new, not-yet-saved card) | tap "Add new payment method" in the Peach modal | yes -- **4 fields, not 3**: Card Number, Expiry (single "MM / YY" field), CVC, and **Card Holder Name**, which Peach requires -- a first attempt that only filled 3 fields got rejected with "Card Holder's name required" |
| Split (points + card) | edit the amount box to a partial value | yes -- remainder correctly auto-calculated, same Peach/3DS flow for the card portion |
| Buy without completing | stop after the Peach modal appears, never submit | yes -- no order created, no balance change, confirmed clean |
| Balance check only, no purchase | `STEPS=login,get_balance` | yes -- for "get me the balance for user X" without buying anything |

**One confirmed bug, recurring**: the Boosts balance badge on the "Purchase
complete" screen can show the *stale pre-purchase* value instead of the
updated one -- now seen on 4 of 10 purchases across both test scripts,
frequent enough to call a real pattern, not a one-off. The deduction itself
is always correct (confirmed by re-reading the balance in a fresh session
or a later screen); it's a display refresh timing issue specific to that
confirmation screen. Worth a ticket: assert the badge updates within a few
seconds after "Purchase complete" renders, not that it's instant or
synchronous with that message.

## scripts/boost_actions.py -- composable actions, not one fixed flow

Each action is a small function (`login`, `get_balance`, `goto_product`,
`start_checkout`, `set_payment`, `checkout`, `voucher_details`) that can run
standalone or be chained via the `STEPS` env var -- built this way
specifically so a request like "just get me the balance for this user"
doesn't have to run a purchase to get it, and "buy but don't complete the
purchase" is a first-class option (`COMPLETE_PURCHASE=false`), not a hack.

Every action records **everything visible on screen** (not just the fields
it cares about) into `state["screens"]`, flushed to `result.json` after
every single screen -- not just at the end -- so a crash mid-run still
leaves a diagnosable trail of exactly what the app showed at each step.
This is how the cardholder-name bug above actually got found: the crash
left the unfilled form's full text on disk to read back.

| Option | Values | Notes |
|---|---|---|
| `STEPS` | comma-separated action names | default: full purchase chain |
| `PAYMENT_METHOD` | `points` \| `card_saved` \| `card_new` \| `split` | |
| `BOOSTS_AMOUNT` | number | only for `split` |
| `CARD_NUMBER`, `CARD_EXP`, `CARD_CVC`, `CARD_HOLDER_NAME` | | only for `card_new` |
| `COMPLETE_PURCHASE` | `true` \| `false` | `false` stops right after the Peach modal/card form, before submitting |

`run-purchase-test.yml` currently wraps the older `run_purchase_test.py` --
worth repointing it at `boost_actions.py` once the `STEPS`-based interface
is the one being relied on long-term. See
`rovo-handoff/chat-triggered-execution.md` for the design to trigger this
from a Rovo chat conversation ("buy 1 Plato Coffee, pay with points", "get
the balance for user X", "add a new card and pay but don't confirm") rather
than the GitHub UI -- the `STEPS`/option model above is exactly what a
Forge action would need to assemble from parsed chat intent.

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
| `LAMBDATEST_USERNAME`, `LAMBDATEST_ACCESS_KEY` | app-tests execution, `run_purchase_test.py` |
| `TEST_ID_NUMBER`, `TEST_PHONE_LOCAL`, `TEST_OTP` | login for `run_purchase_test.py` -- a PPE test identity, not a real customer |
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

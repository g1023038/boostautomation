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
.github/workflows/      the pipeline workflows (see below)
scripts/                shared API clients + the Jira/Xray/Confluence pipeline entrypoints
mobile-tests/           real pytest tests for the Booost Android app (Appium, real device)
mobile-tests/boost_actions.py   composable actions the tests (and codegen) are built on
mobile-tests/TEST_INDEX.md      coverage index -- the agent reads this before writing anything new
api-tests/               generated + hand-written API tests (pytest)
app-tests/               generated + hand-written web UI tests (Playwright, via LambdaTest)
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
product (fixed, like Plato Coffee, or variable-amount, like the KFC voucher)
is an independent "Buy now" -> checkout -> pay. **Naming inconsistency in the
app itself**: the catalog tile reads "KFC_Brand" but that same product's
detail page title then reads "KFC_Display" -- navigation needs the tile
name (`KFC_Brand`), not the detail-page name; cost a test failure before
this was understood (see `testdata/reference/booost_buy_purchase_scenarios.json`).
All payment methods verified
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

**Product lookup is search-based, not scroll-and-match.** `action_goto_product`
types the product name into the catalog's own Search box (confirmed it
filters live -- searching a non-existent product correctly hid both real
ones) rather than assuming the target is already visible on-screen. This is
what lets any catalog product be found and bought generically, including
ones never seen before, not just the two we happened to scroll past during
exploration. One real trap avoided: after typing, the search box's own
`text` attribute equals the product name too, so the result tap is scoped
specifically to `TextView` (tile labels) -- an unscoped match risks grabbing
the search box itself instead of the result. Variable-denomination products
(KFC) are also tested at both ends of their stated range (R10.00 min,
R1,000.00 max), not just one arbitrary amount -- see
`testdata/reference/booost_buy_purchase_scenarios.json`.

## No developer needed to write these tests -- the agent does, on this base

See `mobile-tests/ARCHITECTURE.md` for how `boost_actions.py` is actually
designed -- the composable-actions pattern, the state dict, when to reuse
an action vs. write a new one. Written specifically as context for whichever
agent (ours or Rovo's) is about to generate code here; `mobile-tests/TEST_INDEX.md`
is the complementary "what's already covered" view.

`mobile-tests/boost_actions.py` isn't just a diagnostic tool -- it's the base
library the codegen step (`scripts/generate_script.py`, `mobile` test type)
is explicitly instructed to build on. When a new Xray test case for this app
is approved and has no script yet, the agent writes a pytest test that
imports the existing `action_*` functions (`action_login`,
`action_goto_product`, `action_set_payment`, ...) and composes them for the
new scenario -- it does not re-derive locators, login, or payment handling
from scratch, and it already knows about the cardholder-name requirement and
the stale-balance-badge workaround below. See `MOBILE_SYSTEM_PROMPT` in
`generate_script.py` for exactly what it's told. `mobile-tests/test_purchases.py`
*is* what that process produces -- data-driven from
`testdata/reference/booost_buy_purchase_scenarios.json` (add a row for a new
product/payment combo instead of writing a new function), plus two dedicated
tests for the cases that need different handling (the points-balance
precondition, buy-without-completing). All passing against the real app
(one test-data caveat below).

`type_into_element()` in `boost_actions.py` is the hardening worth copying
into any new action: find-and-act in two separate calls (`find_elements()`
then `.click()`/`.send_keys()` later) can hit a `StaleElementReferenceException`
if the screen re-renders in between -- hit this for real on the KFC
variable-amount field, which renders slightly slower than the screens that
had already been exercised. It re-finds fresh on every retry instead of
reusing one cached handle.

**Test-data caveat, not a code bug**: `test_buy_with_boost_points` consumes
the shared test account's Boosts balance every time it runs (the other
payment methods don't touch it) -- it was drained from 108.25 to single
digits over one day of exploration plus these tests, with no known top-up
mechanism yet. The test checks `balance_before` and skips itself cleanly
rather than false-failing when there isn't enough left to cover one
purchase. This is the stateful test-data problem flagged early on in
`testdata/reference/` finally showing up in practice -- worth prioritizing
a real fix (a seeded points balance per CI run, or a top-up endpoint) over
leaving the skip in place long-term.

## mobile-tests/boost_actions.py -- composable actions, not one fixed flow

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

`run-purchase-test.yml` wraps this directly for ad-hoc/chat-triggered runs
with arbitrary options; `execute-tests.yml`'s `mobile-tests` job runs the
full `pytest` suite in `mobile-tests/` on every push to `main`. See
`rovo-handoff/chat-triggered-execution.md` for the design to trigger a
one-off run from a Rovo chat conversation ("buy 1 Plato Coffee, pay with
points", "get the balance for user X", "add a new card and pay but don't
confirm") rather than the GitHub UI -- the `STEPS`/option model above is
exactly what a Forge action would need to assemble from parsed chat intent.

## Pipeline flow

| Trigger | Workflow | What it does |
|---|---|---|
| Test Plan → Approved (Jira Automation Rule 1) | `generate-test-cases.yml` | Calls a pinned LLM, drafts Gherkin, creates a draft Jira Test issue |
| Draft Test → Approved (Jira Automation Rule 2) | `post-to-xray.yml` | Tags the draft with its own issue key, posts to Xray via Cucumber Feature Import -- updates the same issue in place |
| Xray Test → Approved (Jira Automation Rule 3) | `generate-script.yml` | Calls the LLM again to write the automation script (api/ui/mobile), opens a PR |
| Push to `main` | `execute-tests.yml` | Runs API tests, web UI tests, and the `mobile-tests/` pytest suite on LambdaTest, publishes results to Xray + Confluence, files a Jira Bug on failure |
| Manual / chat-triggered | `run-purchase-test.yml` | One-off `boost_actions.py` run with arbitrary `STEPS`/options -- see `rovo-handoff/chat-triggered-execution.md` |

## Required GitHub Secrets

| Secret | Used by |
|---|---|
| `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY` | all Jira/Confluence calls (service account -- see `rovo-handoff/service-account-setup.md`) |
| `XRAY_CLIENT_ID`, `XRAY_CLIENT_SECRET` | Xray Cloud API auth |
| `ANTHROPIC_API_KEY` | test case + script generation (pinned model, see `scripts/llm_client.py`) |
| `LAMBDATEST_USERNAME`, `LAMBDATEST_ACCESS_KEY` | app-tests execution, `mobile-tests/` |
| `TEST_ID_NUMBER`, `TEST_PHONE_LOCAL`, `TEST_OTP` | login for `mobile-tests/` -- a PPE test identity, not a real customer |
| `CONFLUENCE_SPACE_KEY` | results page target |
| `GITHUB_TOKEN` | automatic, already provided per workflow run -- just needs `permissions: contents: write, pull-requests: write`, already set in `generate-script.yml` |

The classic PAT you generated for `repository_dispatch` does **not** go in
this list -- it lives only in the Jira Automation rule configs
(`rovo-handoff/jira-automation-rules.md`), not in this repo.

## What's still open before this runs end to end

1. **`mobile-tests/` is real now; `app-tests/` (web Playwright) is still a
   placeholder.** It was scaffolded on a guess before we confirmed Booost is
   a native Android app, not a web/PWA one -- keep it only if there's
   actually a web surface to test; otherwise it's dead weight to prune.
2. **`TEST_DATA_KEY_FIELD` in `generate_script.py` is a guessed field ID**
   (`customfield_10050`). Needs the real one once the field exists (see
   `rovo-handoff/xray-custom-fields.md`).
3. **`test_type` in Rule 3 is hardcoded to `"api"`.** Needs the "Automation
   type" custom field (same doc, now `api`/`ui`/`mobile`/`perf`) before
   anything but `api` routes correctly.
4. **The shared test account's Boosts balance needs a real top-up story**
   (see the test-data caveat above) -- it's the one thing standing between
   `mobile-tests/` and being fully green in CI long-term.
5. **`execute-tests.yml` doesn't yet know which Test Plan/Execution a given
   push relates to** -- it currently publishes against
   `vars.DEFAULT_TEST_PLAN_KEY`, a single hardcoded fallback. Properly wiring
   this means threading the Test key through the PR (e.g. from the
   `auto/<test-key>` branch name `generate_script.py` already creates) into
   the execution-import step. Worth solving once the first real run proves
   the rest of the chain out.
6. **Performance (JMeter) has no workflow yet** -- `performance/README.md`
   describes the intended path (`.jtl` → JUnit → `publish_results.py`) but
   nothing executes it.

## Next step

Decide what to do about the Boosts balance top-up (item 4 above) -- that's
the real blocker to `mobile-tests/` running green in CI indefinitely rather
than skipping the points test once the account runs dry.

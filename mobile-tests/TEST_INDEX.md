# Test coverage index

See `ARCHITECTURE.md` first for how `boost_actions.py` is actually designed
(the composable-actions pattern, the state dict, known traps) -- this file
is the *what's covered*, that one is the *how to build on it*.

Canonical source of truth for what's automated against the Booost app --
kept in this repo (not Confluence) so it stays in lockstep with the code via
the same PR review, not a separate page that drifts. The codegen agent reads
this first to do gap analysis before writing a new test, instead of scanning
every file.

If a Confluence view is wanted for non-technical visibility, publish it
*from* this file (same pattern `scripts/publish_results.py` already uses
for results) -- never maintain it by hand in two places.

## Implemented (`mobile-tests/`, pytest + `boost_actions.py`)

| Test | Covers | File::Function |
|---|---|---|
| Login succeeds, balance readable | ID+DOB auto-derive, phone, OTP, permission screens | `test_balance.py::test_login_succeeds_and_balance_is_readable` |
| Balance check, no purchase | "get me the balance" without buying anything | `test_balance.py::test_get_balance_without_any_purchase` |
| Buy with saved card | Full card payment via Peach + 3DS, doesn't touch points | `test_purchases.py::test_purchase_scenario_completes[plato_coffee_card_saved]` |
| Buy with a newly-added card | Peach "Add new payment method" (4 fields incl. Card Holder Name) | `test_purchases.py::test_purchase_scenario_completes[plato_coffee_card_new]` |
| Split-tender payment | Partial points + card remainder via Peach/3DS | `test_purchases.py::test_purchase_scenario_completes[plato_coffee_split]` |
| Variable-denomination purchase | KFC voucher, typical amount (R50) | `test_purchases.py::test_purchase_scenario_completes[kfc_variable_amount_card]` |
| Variable-denomination boundaries | KFC at the stated R10.00 min and R1,000.00 max | `..._completes[kfc_minimum_amount_boundary]`, `[kfc_maximum_amount_boundary]` |
| Full points payment | Default checkout, skips cleanly if balance can't cover it | `test_purchases.py::test_buy_with_boost_points` |
| Buy without completing | Stops at the Peach modal, confirms nothing charged | `test_purchases.py::test_buy_without_completing_purchase_charges_nothing` |

Data-driven scenarios (payment method/product/amount combinations) live in
`testdata/reference/booost_buy_purchase_scenarios.json` -- add a row there
for a new combination rather than a new test function.

## Known app findings (not test gaps, but worth tracking here too)

- Peach's "Add new card" form needs 4 fields (Card Number, Expiry, CVC, Card
  Holder Name), not 3 -- missing the 4th gets rejected.
- Purchase complete screen's balance badge can show a stale pre-purchase
  value (confirmed recurring, ~4 of 10 purchases) -- always re-read via
  `action_recheck_balance`, never assert directly off that screen.
- Catalog tile name and product detail page title can differ for the same
  product (`KFC_Brand` tile vs `KFC_Display` detail title).
- No shared cart anywhere in Booost Buy -- every product is independent
  Buy now -> checkout -> pay.
- Compose app, no resource-ids/testTags anywhere -- every locator here is
  by visible text.

## Not yet implemented -- gap list from Daniel Motlokoa's "Boost regression" suite

Found via LambdaTest App Automation (33 tests, Cucumber/Gherkin-style,
running since ~September). Not ported -- these are fresh agent-written
targets once prioritized, same as everything above. Listed here so the
agent (and anyone doing gap analysis) can see what's covered elsewhere vs.
genuinely missing from this repo:

- [ ] Registration/age validation (error when member age is under 18)
- [ ] Device permissions enablement from Settings
- [ ] FAQ access
- [ ] Virtual card add + view
- [ ] Loyalty cards display (all cards visible)
- [ ] Name/Surname field validation (error handling)
- [ ] Logout
- [ ] Boost-a-Million landing page: element display, tab interaction logic
- [ ] Claiming unclaimed badges
- [ ] Countdown/persistence when member leaves device idle or switches sections
- [ ] Voucher receipt: no voucher issued when payment is unconfirmed/cancelled
      (partially analogous to our `test_buy_without_completing_purchase_charges_nothing`,
      but that test doesn't yet assert on the Voucher Wallet specifically --
      worth closing that precise gap)

Not included: the ones Daniel's suite got right that we also now cover better
(payment methods, provisioning) -- no need to re-track those here.

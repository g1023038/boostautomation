# How boost_actions.py is actually designed

This is written for whichever agent is about to generate code against this
repo (ours or Rovo's) -- reading the source is not a substitute for this,
because the *design intent* (why it's shaped this way, what's safe to reuse
vs. what to avoid repeating) doesn't fully show up in the code itself.

## The core idea: small verbs, not one big flow

Every `action_*` function in `boost_actions.py` does exactly one thing on
the app, takes `(driver, state)`, and returns nothing -- it mutates `state`
(a plain dict) and optionally raises if something went wrong. There is no
"the purchase flow" function. There's `action_login`, `action_goto_product`,
`action_start_checkout`, `action_set_payment`, `action_checkout`,
`action_voucher_details`, `action_get_balance`, `action_recheck_balance` --
and a *test* is just whichever of these get called in sequence.

This exists because real requests aren't all "do a full purchase":

```python
# "Get me the balance for user X" -- no purchase at all
action_login(driver, state)
action_get_balance(driver, state)

# "Buy a KFC voucher for R50 with a new card"
action_login(driver, state)
action_goto_product(driver, state)      # state["product_name"]="KFC_Brand", state["product_amount"]="50"
action_start_checkout(driver, state)
action_set_payment(driver, state)       # state["payment_method"]="card_new", card details in state
action_checkout(driver, state)

# "Start a purchase but don't actually pay" -- verifying checkout state only
action_login(driver, state)
action_goto_product(driver, state)
action_start_checkout(driver, state)
action_set_payment(driver, state)
state["complete_purchase"] = False
action_checkout(driver, state)          # stops at the Peach modal, never submits
```

Same five functions, three completely different tests, zero duplicated
login/navigation/payment code. **This is the thing to copy when writing a
new test: figure out which existing actions the new scenario needs, call
them in order, add only the parts that are genuinely new** (a new assertion,
maybe a new action if the screen has never been touched before).

## The state dict is the only thing passed around

`state` starts as whatever options the caller provides (`base_state` fixture
in tests, or env vars in `boost_actions.py`'s own CLI mode) and accumulates
facts as actions run: `state["balance_before"]`, `state["order_id"]`,
`state["wicode"]`, `state["screens"]` (every screen's full visible text,
appended by every action via `record_screen`). Read `boost_actions.py`
itself for the exact keys each action reads and writes -- they're listed as
plain dict lookups (`state["product_name"]`, `state.get("boosts_amount")`),
not hidden behind any abstraction.

## When to write a new action vs. reuse an existing one

Reuse if the screen/flow has already been automated -- check
`TEST_INDEX.md` first, it lists what's implemented. Write a new
`action_*` function only when a genuinely new screen is involved (e.g.
nothing here touches Loyalty Cards or Logout yet). A new action should:

- Take `(driver, state)`, nothing else.
- Call `record_screen(state, driver, "label")` at least once, so the
  screen's content is captured for verification and for diagnosing a
  failure later (every action does this -- it's not optional polish, it's
  how real bugs in this session got found, e.g. the cardholder-name gap was
  spotted by reading a recorded screen's text, not by guessing).
- Use `type_into_element()` for any field fill, never raw
  `find_elements()[i].click(); .send_keys()` -- a cached element reference
  can go stale if the screen re-renders between the find and the act, and
  this has broken a real test before (KFC's slower-rendering detail page).
- Use `tap_by_text()` for any tap -- every locator in this app is by
  visible text, there are no resource-ids (Jetpack Compose, no `testTag`s
  set anywhere).
- Get registered in the `ACTIONS` dict at the bottom of the file if it
  should be runnable standalone via `STEPS=`.

## Two different callers, same actions

- **`mobile-tests/test_*.py`** (pytest): calls actions directly in Python,
  asserts on `state` afterward. This is where real test logic and
  assertions live.
- **`boost_actions.py` run directly** (`python boost_actions.py`): chains
  actions via the `STEPS` env var (comma-separated action names) for
  one-off or chat-triggered runs with no assertions, just a JSON result --
  see the module docstring for the full option list
  (`PAYMENT_METHOD`, `BOOSTS_AMOUNT`, `CARD_NUMBER`, `COMPLETE_PURCHASE`, ...).
  `.github/workflows/run-purchase-test.yml` wraps this as a
  `workflow_dispatch` for exactly this use.

Both exist because "write a regression test" and "run this one specific
thing right now with these specific parameters" are different jobs that
happen to need the same underlying actions.

## Known traps already paid for -- don't rediscover these

- Peach Payments' "Add new payment method" form has **4** fields (Card
  Number, Expiry, CVC, Card Holder Name), not 3 -- omitting the name gets
  rejected.
- The Purchase complete screen's balance badge can show a **stale**
  pre-purchase value for a few seconds (confirmed recurring). Never assert
  a balance delta directly off that screen -- call `action_recheck_balance`
  first and assert against `state["balance_settled"]`.
- A catalog tile's name and that same product's detail-page title can
  **differ** (`KFC_Brand` tile, `KFC_Display` detail title) -- navigation
  needs the tile name, which is why `action_goto_product` searches by the
  name passed in rather than assuming it matches everywhere.
- The split-tender amount box is user-editable, not just a toggle -- and
  the app silently does nothing on "Pay now" if the requested Boosts amount
  exceeds the actual balance ("You only have B0 to spend" appears on
  screen, no error raised) rather than failing loudly. Check the balance
  first if a test needs a specific split amount to succeed.
- There is **no shared cart** anywhere in Booost Buy. Every product is an
  independent Buy now -> checkout -> pay. Don't write a multi-item flow.

"""
Booost Buy purchase journeys, data-driven from
testdata/reference/booost_buy_purchase_scenarios.json rather than one
hand-written function per case -- add a new payment method, a new product,
or a new denomination by adding a row to that file, not by writing new code.

test_buy_with_boost_points is the one exception: it needs a balance
precondition check and a different assertion (the recheck-balance workaround
for the stale-badge bug), so it stays a dedicated test rather than folding
into the parametrized set.
"""
import json
from pathlib import Path

import pytest

from boost_actions import (
    action_checkout,
    action_goto_product,
    action_login,
    action_recheck_balance,
    action_set_payment,
    action_start_checkout,
    action_voucher_details,
)

SCENARIOS_PATH = Path(__file__).parent.parent / "testdata/reference/booost_buy_purchase_scenarios.json"
SCENARIOS = json.loads(SCENARIOS_PATH.read_text())

PRODUCT = "Plato Coffee"
TOTAL_DUE = 13.00  # R10.00 item + R3.00 transaction fee, confirmed live


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
def test_purchase_scenario_completes(driver, base_state, scenario):
    state = base_state
    state.update(scenario)
    action_login(driver, state)
    action_goto_product(driver, state)
    action_start_checkout(driver, state)

    # Same test-data exhaustion problem as test_buy_with_boost_points, just
    # for the points portion of a split payment: the app silently does
    # nothing on "Pay now" if the requested Boosts amount exceeds what's
    # available ("You only have B0 to spend" on screen) rather than erroring,
    # so this has to be checked before attempting it, not inferred from a
    # failure afterward.
    if scenario["payment_method"] == "split":
        required = float(scenario.get("boosts_amount", 0))
        if state["balance_before"] < required:
            pytest.skip(
                f"test account balance ({state['balance_before']}) can't cover "
                f"the split's Boosts portion ({required}) -- needs topping up")

    action_set_payment(driver, state)
    action_checkout(driver, state)
    assert state["status"] == "complete"
    assert state["order_id"]

    if scenario["payment_method"] != "points":
        # Card-funded portion must never touch the Boosts balance; a pure
        # points purchase is the one case where balance_before != after,
        # and it's covered separately in test_buy_with_boost_points below
        # because it needs the stale-badge workaround, not a direct assert.
        assert state["balance_before"] == state["balance_after"]

    if scenario.get("total_due") is not None:
        action_voucher_details(driver, state)
        assert state.get("wicode")


def test_buy_with_boost_points(driver, base_state):
    state = base_state
    state["product_name"] = PRODUCT
    state["payment_method"] = "points"
    action_login(driver, state)
    action_goto_product(driver, state)
    action_start_checkout(driver, state)

    if state["balance_before"] < TOTAL_DUE:
        pytest.skip(
            f"test account balance ({state['balance_before']}) can't cover "
            f"a full-points purchase ({TOTAL_DUE}) -- needs topping up, see "
            f"testdata/reference/ for the stateful test-data gap this is")

    action_set_payment(driver, state)
    action_checkout(driver, state)
    assert state["status"] == "complete"
    assert state["order_id"]

    # The Purchase complete screen's own balance badge can lag the real
    # deduction by a few seconds (confirmed, recurring app bug -- see
    # README). Re-read after navigating away instead of trusting that screen.
    action_recheck_balance(driver, state)
    assert state["balance_settled"] == round(state["balance_before"] - TOTAL_DUE, 2)


def test_buy_without_completing_purchase_charges_nothing(driver, base_state):
    state = base_state
    state["product_name"] = PRODUCT
    state["payment_method"] = "card_saved"
    state["complete_purchase"] = False
    action_login(driver, state)
    action_goto_product(driver, state)
    action_start_checkout(driver, state)
    action_set_payment(driver, state)
    action_checkout(driver, state)
    assert state.get("stopped_before_payment") is True
    assert state.get("order_id") is None
    assert state.get("balance_after") is None

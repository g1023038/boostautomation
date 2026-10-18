"""
Booost Buy purchase journeys, built on the composable actions in
boost_actions.py. Plato Coffee (fixed R10.00 + R3.00 transaction fee = B13.00
on points) is the product used throughout -- cheapest clean item in the
catalog, confirmed live across many runs.

The test account's Boosts balance is a finite, shared resource that these
tests consume every time test_buy_with_boost_points runs (card/split/
card_new purchases don't touch it). It was drained from 108.25 to single
digits over one day of manual exploration plus these tests -- there's no
known top-up mechanism yet. Until the team seeds a dedicated points balance
for CI (the stateful test-data problem flagged in testdata/reference/),
the points test skips itself rather than false-failing when the balance
can't cover one purchase.
"""
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

PRODUCT = "Plato Coffee"
TOTAL_DUE = 13.00  # R10.00 item + R3.00 transaction fee


def _run_purchase(driver, state, payment_method, **extra):
    state["product_name"] = PRODUCT
    state["payment_method"] = payment_method
    state.update(extra)
    action_login(driver, state)
    action_goto_product(driver, state)
    action_start_checkout(driver, state)
    action_set_payment(driver, state)
    action_checkout(driver, state)
    return state


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


def test_buy_with_saved_card_does_not_touch_points(driver, base_state):
    state = _run_purchase(driver, base_state, "card_saved")
    assert state["status"] == "complete"
    assert state["order_id"]
    assert state["balance_before"] == state["balance_after"]


def test_buy_with_newly_added_card(driver, base_state):
    state = _run_purchase(
        driver, base_state, "card_new",
        card_number="4200000000000091", card_exp="12/28",
    )
    assert state["status"] == "complete"
    assert state["order_id"]
    assert state["balance_before"] == state["balance_after"]


def test_buy_with_split_tender(driver, base_state):
    state = _run_purchase(driver, base_state, "split", boosts_amount="5")
    assert state["status"] == "complete"
    assert state["order_id"]


def test_buy_without_completing_purchase_charges_nothing(driver, base_state):
    state = _run_purchase(driver, base_state, "card_saved", complete_purchase=False)
    assert state.get("stopped_before_payment") is True
    assert state.get("order_id") is None
    assert state.get("balance_after") is None


def test_voucher_is_provisioned_with_a_redeemable_wicode(driver, base_state):
    state = _run_purchase(driver, base_state, "points")
    action_voucher_details(driver, state)
    assert state.get("wicode")
    assert state["wicode"].isdigit()

from boost_actions import action_get_balance, action_login


def test_login_succeeds_and_balance_is_readable(driver, base_state):
    action_login(driver, base_state)
    assert base_state["balance"] is not None
    assert base_state["balance"] >= 0


def test_get_balance_without_any_purchase(driver, base_state):
    """Confirms a balance check never has to go through Booost Buy at all --
    the "just get me the balance" case from a chat-triggered request."""
    action_login(driver, base_state)
    action_get_balance(driver, base_state)
    assert base_state["balance"] is not None
    assert "order_id" not in base_state

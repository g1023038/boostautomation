package com.boostautomation.tests;

import com.boostautomation.actions.BoostActions;
import org.testng.Assert;
import org.testng.annotations.Test;

/** Java port of test_balance.py. */
public class BalanceTest extends BaseTest {

    @Test
    public void loginSucceedsAndBalanceIsReadable() {
        BoostActions.actionLogin(driver, state);
        Assert.assertNotNull(state.balance);
        Assert.assertTrue(state.balance >= 0);
    }

    /** Confirms a balance check never has to go through Booost Buy at all --
     * the "just get me the balance" case from a chat-triggered request. */
    @Test
    public void getBalanceWithoutAnyPurchase() {
        BoostActions.actionLogin(driver, state);
        BoostActions.actionGetBalance(driver, state);
        Assert.assertNotNull(state.balance);
        Assert.assertNull(state.orderId);
    }
}

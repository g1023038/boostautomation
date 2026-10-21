package com.boostautomation.tests;

import com.boostautomation.actions.BoostActions;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.testng.Assert;
import org.testng.SkipException;
import org.testng.annotations.DataProvider;
import org.testng.annotations.Test;

import java.io.File;
import java.io.IOException;

/**
 * Java port of test_purchases.py -- Booost Buy purchase journeys,
 * data-driven from the exact same
 * ../testdata/reference/booost_buy_purchase_scenarios.json the Python
 * suite reads. One shared source of scenarios for both languages: add a
 * row there once, not new code in either.
 *
 * buyWithBoostPoints is the one exception: it needs a balance
 * precondition check and a different assertion (the recheck-balance
 * workaround for the stale-badge bug), so it stays a dedicated test
 * rather than folding into the data-driven set.
 */
public class PurchaseTest extends BaseTest {

    private static final String PRODUCT = "Plato Coffee";
    private static final double TOTAL_DUE = 13.00; // R10.00 item + R3.00 transaction fee, confirmed live

    private static final ObjectMapper JSON = new ObjectMapper()
            .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);

    @DataProvider(name = "scenarios")
    public static Object[][] scenarios() throws IOException {
        File file = new File("../testdata/reference/booost_buy_purchase_scenarios.json");
        JsonNode root = JSON.readTree(file);
        Object[][] rows = new Object[root.size()][1];
        int i = 0;
        for (JsonNode node : root) {
            rows[i++] = new Object[]{node};
        }
        return rows;
    }

    @Test(dataProvider = "scenarios")
    public void purchaseScenarioCompletes(JsonNode scenario) throws IOException {
        JSON.readerForUpdating(state).readValue(scenario);
        BoostActions.actionLogin(driver, state);
        BoostActions.actionGotoProduct(driver, state);
        BoostActions.actionStartCheckout(driver, state);

        // Same test-data exhaustion problem as buyWithBoostPoints, just for
        // the points portion of a split payment: the app silently does
        // nothing on "Pay now" if the requested Boosts amount exceeds
        // what's available ("You only have B0 to spend" on screen) rather
        // than erroring, so this has to be checked before attempting it.
        if ("split".equals(state.paymentMethod)) {
            double required = state.boostsAmount != null ? Double.parseDouble(state.boostsAmount) : 0;
            if (state.balanceBefore < required) {
                throw new SkipException(String.format(
                        "test account balance (%s) can't cover the split's Boosts portion (%s) -- needs topping up",
                        state.balanceBefore, required));
            }
        }

        BoostActions.actionSetPayment(driver, state);
        BoostActions.actionCheckout(driver, state);
        Assert.assertEquals(state.status, "complete");
        Assert.assertNotNull(state.orderId);

        if (!"points".equals(state.paymentMethod)) {
            // Card-funded portion must never touch the Boosts balance; a
            // pure points purchase is the one case where balanceBefore !=
            // balanceAfter, covered separately in buyWithBoostPoints
            // because it needs the stale-badge workaround, not a direct
            // assert.
            Assert.assertEquals(state.balanceAfter, state.balanceBefore);
        }

        if (state.totalDue != null) {
            BoostActions.actionVoucherDetails(driver, state);
            Assert.assertNotNull(state.wicode);
        }
    }

    @Test
    public void buyWithBoostPoints() {
        state.productName = PRODUCT;
        state.paymentMethod = "points";
        BoostActions.actionLogin(driver, state);
        BoostActions.actionGotoProduct(driver, state);
        BoostActions.actionStartCheckout(driver, state);

        if (state.balanceBefore < TOTAL_DUE) {
            throw new SkipException(String.format(
                    "test account balance (%s) can't cover a full-points purchase (%s) -- needs topping up, "
                            + "see testdata/reference/ for the stateful test-data gap this is",
                    state.balanceBefore, TOTAL_DUE));
        }

        BoostActions.actionSetPayment(driver, state);
        BoostActions.actionCheckout(driver, state);
        Assert.assertEquals(state.status, "complete");
        Assert.assertNotNull(state.orderId);

        // The Purchase complete screen's own balance badge can lag the
        // real deduction by a few seconds (confirmed, recurring app bug --
        // see README). Re-read after navigating away instead of trusting
        // that screen.
        BoostActions.actionRecheckBalance(driver, state);
        double expected = Math.round((state.balanceBefore - TOTAL_DUE) * 100.0) / 100.0;
        Assert.assertEquals(state.balanceSettled, Double.valueOf(expected));
    }

    @Test
    public void buyWithoutCompletingPurchaseChargesNothing() {
        state.productName = PRODUCT;
        state.paymentMethod = "card_saved";
        state.completePurchase = false;
        BoostActions.actionLogin(driver, state);
        BoostActions.actionGotoProduct(driver, state);
        BoostActions.actionStartCheckout(driver, state);
        BoostActions.actionSetPayment(driver, state);
        BoostActions.actionCheckout(driver, state);
        Assert.assertEquals(state.stoppedBeforePayment, Boolean.TRUE);
        Assert.assertNull(state.orderId);
        Assert.assertNull(state.balanceAfter);
    }
}

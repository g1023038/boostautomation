package com.boostautomation.actions;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import io.appium.java_client.android.AndroidDriver;

import java.io.File;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Java port of boost_actions.py's own CLI entry point -- chains ACTIONS via
 * a STEPS env var the same way, for the same chat-triggered / one-off
 * use case a workflow_dispatch run exercises, not just the TestNG path.
 * See the module header comment in boost_actions.py for the STEPS examples
 * (login,get_balance / PAYMENT_METHOD=card_new / etc.) -- they apply here
 * unchanged, just as environment variables read by main() below.
 */
public final class BoostActionsRunner {

    @FunctionalInterface
    private interface ActionFn {
        void run(AndroidDriver driver, TestState state);
    }

    private static final Map<String, ActionFn> ACTIONS = new LinkedHashMap<>();

    static {
        ACTIONS.put("login", BoostActions::actionLogin);
        ACTIONS.put("get_balance", BoostActions::actionGetBalance);
        ACTIONS.put("goto_product", BoostActions::actionGotoProduct);
        ACTIONS.put("start_checkout", BoostActions::actionStartCheckout);
        ACTIONS.put("set_payment", BoostActions::actionSetPayment);
        ACTIONS.put("checkout", BoostActions::actionCheckout);
        ACTIONS.put("voucher_details", BoostActions::actionVoucherDetails);
        ACTIONS.put("recheck_balance", BoostActions::actionRecheckBalance);
    }

    private static final String DEFAULT_STEPS =
            "login,goto_product,start_checkout,set_payment,checkout,voucher_details";

    public static void main(String[] args) throws Exception {
        String[] steps = getenvOr("STEPS", DEFAULT_STEPS).split(",");

        TestState state = new TestState();
        state.idNumber = TestState.requireEnv("TEST_ID_NUMBER");
        state.phone = TestState.requireEnv("TEST_PHONE_LOCAL");
        state.otp = getenvOr("TEST_OTP", "123456");
        state.productName = System.getenv("PRODUCT_NAME");
        state.productAmount = System.getenv("PRODUCT_AMOUNT");
        state.paymentMethod = getenvOr("PAYMENT_METHOD", "points");
        state.boostsAmount = System.getenv("BOOSTS_AMOUNT");
        state.cardNumber = System.getenv("CARD_NUMBER");
        state.cardExp = System.getenv("CARD_EXP");
        state.cardCvc = getenvOr("CARD_CVC", "123");
        state.cardHolderName = getenvOr("CARD_HOLDER_NAME", "Test User");
        state.completePurchase = Boolean.parseBoolean(getenvOr("COMPLETE_PURCHASE", "true"));

        AndroidDriver driver = DriverFactory.createDriver("boost-actions", String.join("+", steps));
        ObjectMapper mapper = new ObjectMapper().enable(SerializationFeature.INDENT_OUTPUT);
        try {
            for (String step : steps) {
                System.err.println("--- running step: " + step + " ---");
                ActionFn action = ACTIONS.get(step);
                if (action == null) {
                    throw new IllegalArgumentException("unknown step: " + step);
                }
                action.run(driver, state);
            }
        } finally {
            driver.quit();
            mapper.writeValue(new File("result.json"), state);
        }

        System.out.println(mapper.writerWithDefaultPrettyPrinter().writeValueAsString(state));
    }

    private static String getenvOr(String key, String def) {
        String value = System.getenv(key);
        return (value == null || value.isEmpty()) ? def : value;
    }

    private BoostActionsRunner() {
    }
}

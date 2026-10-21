package com.boostautomation.actions;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.ArrayList;
import java.util.List;

/**
 * Mutable bag of fields threaded through every action -- the Java
 * equivalent of the plain dict Python's actions pass around as `state`.
 * Public fields on purpose, same reason the Python version is a dict: this
 * is test-support data, not a domain model, and every action should be able
 * to read/write it directly without ceremony. See
 * mobile-tests/ARCHITECTURE.md for why the design is shaped this way --
 * that doc isn't Python-specific.
 */
public class TestState {
    public String idNumber;
    public String phone;
    public String otp;

    @JsonProperty("product_name")
    public String productName;
    @JsonProperty("product_amount")
    public String productAmount;
    @JsonProperty("payment_method")
    public String paymentMethod = "points";
    @JsonProperty("boosts_amount")
    public String boostsAmount;
    @JsonProperty("card_number")
    public String cardNumber;
    @JsonProperty("card_exp")
    public String cardExp;
    @JsonProperty("card_cvc")
    public String cardCvc = "123";
    @JsonProperty("card_holder_name")
    public String cardHolderName = "Test User";
    @JsonProperty("complete_purchase")
    public boolean completePurchase = true;
    @JsonProperty("total_due")
    public Double totalDue;

    public List<ScreenRecord> screens = new ArrayList<>();

    public Double balance;
    public Double balanceBefore;
    public Double balanceAfter;
    public Double balanceSettled;
    public String orderId;
    public String status;
    public String wicode;
    public Boolean stoppedBeforePayment;

    /** Mirrors conftest.py's base_state fixture / boost_actions.py's
     * main() -- same required env vars, same TEST_OTP empty-string-safe
     * fallback (GitHub Actions substitutes a missing secret as an empty
     * string, not an absent key, so a plain default-arg style fallback
     * silently never engages -- see the commit that fixed this for real). */
    public static TestState fromEnv() {
        TestState state = new TestState();
        state.idNumber = requireEnv("TEST_ID_NUMBER");
        state.phone = requireEnv("TEST_PHONE_LOCAL");
        String otp = System.getenv("TEST_OTP");
        state.otp = (otp == null || otp.isEmpty()) ? "123456" : otp;
        String cvc = System.getenv("CARD_CVC");
        if (cvc != null && !cvc.isEmpty()) {
            state.cardCvc = cvc;
        }
        String holder = System.getenv("CARD_HOLDER_NAME");
        if (holder != null && !holder.isEmpty()) {
            state.cardHolderName = holder;
        }
        return state;
    }

    static String requireEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isEmpty()) {
            throw new IllegalStateException("required environment variable not set: " + key);
        }
        return value;
    }
}

package com.boostautomation.actions;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import io.appium.java_client.android.AndroidDriver;
import org.openqa.selenium.By;
import org.openqa.selenium.StaleElementReferenceException;
import org.openqa.selenium.WebElement;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import java.io.File;
import java.io.IOException;
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;

/**
 * Composable Booost app actions -- the Java port of boost_actions.py. Each
 * action does one thing, takes (driver, state), and mutates state rather
 * than returning anything, so a test is just whichever of these get called
 * in sequence. See mobile-tests/ARCHITECTURE.md for why it's shaped this
 * way (that doc covers both language versions, not just the Python one).
 */
public final class BoostActions {

    private static final ObjectMapper MAPPER = new ObjectMapper().enable(SerializationFeature.INDENT_OUTPUT);

    private BoostActions() {
    }

    // ---------------------------------------------------------------- low level

    public static boolean tapByText(AndroidDriver driver, String text, boolean contains, int timeoutSeconds) {
        String xpath = contains
                ? String.format("//*[contains(@text, '%s')]", text)
                : String.format("//*[@text='%s']", text);
        long deadline = System.currentTimeMillis() + timeoutSeconds * 1000L;
        while (System.currentTimeMillis() < deadline) {
            List<WebElement> els = driver.findElements(By.xpath(xpath));
            if (!els.isEmpty()) {
                els.get(0).click();
                return true;
            }
            sleep(1000);
        }
        return false;
    }

    /** find + click + (optional clear) + sendKeys, re-finding the element
     * fresh on every attempt rather than reusing one handle across calls. A
     * cached reference goes stale if the screen re-renders between finding
     * it and acting on it -- hit this for real on a slower-rendering product
     * detail screen (KFC's variable-amount field), fixed here generically. */
    public static void typeIntoElement(AndroidDriver driver, String xpath, String text, int index, boolean clear,
                                        int retries) {
        Exception lastExc = null;
        for (int attempt = 0; attempt < retries; attempt++) {
            try {
                List<WebElement> els = driver.findElements(By.xpath(xpath));
                WebElement el = els.get(index < 0 ? els.size() + index : index);
                el.click();
                if (clear) {
                    el.clear();
                }
                el.sendKeys(text);
                return;
            } catch (IndexOutOfBoundsException | StaleElementReferenceException exc) {
                lastExc = exc;
                sleep(1000);
            }
        }
        throw new RuntimeException(
                String.format("could not type into %s[%d] after %d attempts", xpath, index, retries), lastExc);
    }

    public static void typeIntoElement(AndroidDriver driver, String xpath, String text) {
        typeIntoElement(driver, xpath, text, 0, false, 3);
    }

    public static boolean waitForAnyText(AndroidDriver driver, List<String> texts, int timeoutSeconds) {
        StringBuilder xpath = new StringBuilder("//*[");
        for (int i = 0; i < texts.size(); i++) {
            if (i > 0) {
                xpath.append(" or ");
            }
            xpath.append("contains(@text,'").append(texts.get(i)).append("')");
        }
        xpath.append("]");
        long deadline = System.currentTimeMillis() + timeoutSeconds * 1000L;
        while (System.currentTimeMillis() < deadline) {
            if (!driver.findElements(By.xpath(xpath.toString())).isEmpty()) {
                return true;
            }
            sleep(2000);
        }
        return false;
    }

    /** Every piece of text visible on screen right now, for verification --
     * one page_source snapshot parsed once, never walks live WebElements. */
    public static ScreenRecord scrapeScreen(AndroidDriver driver, String label) {
        Document doc = parseXml(driver.getPageSource());
        List<String> texts = new ArrayList<>();
        collectTexts(doc.getDocumentElement(), texts);
        return new ScreenRecord(label, texts);
    }

    private static void collectTexts(Node node, List<String> out) {
        if (node.getNodeType() == Node.ELEMENT_NODE) {
            String text = ((Element) node).getAttribute("text");
            if (!text.isEmpty()) {
                out.add(text);
            }
        }
        NodeList children = node.getChildNodes();
        for (int i = 0; i < children.getLength(); i++) {
            collectTexts(children.item(i), out);
        }
    }

    /** scrapeScreen + append + flush to result.json immediately, so a crash
     * midway through a multi-stage action (e.g. actionCheckout) still
     * leaves every screen seen so far on disk for diagnosis. */
    public static void recordScreen(TestState state, AndroidDriver driver, String label) {
        state.screens.add(scrapeScreen(driver, label));
        try {
            MAPPER.writeValue(new File("result.json"), state);
        } catch (IOException e) {
            throw new RuntimeException("failed to flush result.json", e);
        }
    }

    /** The balance badge is the only bare "NN.NN" TextView with no currency
     * prefix (prices/amounts always render as "R10.00" / "B13.00" -- the
     * letter is part of the same text node, confirmed from real dumps). */
    public static Double extractBalance(AndroidDriver driver) {
        Document doc = parseXml(driver.getPageSource());
        NodeList nodes = doc.getElementsByTagName("android.widget.TextView");
        for (int i = 0; i < nodes.getLength(); i++) {
            String text = ((Element) nodes.item(i)).getAttribute("text");
            if (text.matches("\\d+\\.\\d+")) {
                return Double.parseDouble(text);
            }
        }
        return null;
    }

    private static Document parseXml(String xml) {
        try {
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            factory.setExpandEntityReferences(false);
            DocumentBuilder builder = factory.newDocumentBuilder();
            return builder.parse(new InputSource(new StringReader(xml)));
        } catch (Exception e) {
            throw new RuntimeException("failed to parse page source", e);
        }
    }

    private static void sleep(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException(e);
        }
    }

    private static int leftBound(WebElement el) {
        String bounds = el.getAttribute("bounds"); // "[x1,y1][x2,y2]"
        String firstPair = bounds.substring(1, bounds.indexOf(']'));
        return Integer.parseInt(firstPair.split(",")[0]);
    }

    private static String nullToEmpty(String s) {
        return s == null ? "" : s;
    }

    // -------------------------------------------------------------------- steps

    public static void actionLogin(AndroidDriver driver, TestState state) {
        sleep(10_000);
        for (int i = 0; i < 5; i++) {
            if (tapByText(driver, "Get Started", true, 3) || tapByText(driver, "Next", true, 3)) {
                sleep(2000);
                continue;
            }
            break;
        }
        sleep(2000);

        WebElement idField = driver.findElement(
                By.xpath("//android.widget.EditText[.//android.widget.TextView[@text='ID number']]"));
        idField.click();
        idField.sendKeys(state.idNumber);
        sleep(2000);
        driver.hideKeyboard();
        sleep(1000);
        if (tapByText(driver, "Continue", true, 5)) {
            sleep(3000);
        }

        WebElement phoneField = driver.findElement(By.xpath(
                "//android.widget.EditText[.//android.widget.TextView[contains(@text,'Cellphone number')]]"));
        phoneField.click();
        phoneField.sendKeys(state.phone);
        sleep(2000);
        driver.hideKeyboard();
        sleep(1000);
        if (tapByText(driver, "Continue", true, 5)) {
            sleep(3000);
        }

        List<WebElement> otpBoxes = new ArrayList<>(driver.findElements(By.className("android.widget.EditText")));
        otpBoxes.sort((a, b) -> Integer.compare(leftBound(a), leftBound(b)));
        String otp = state.otp;
        for (int i = 0; i < Math.min(otpBoxes.size(), otp.length()); i++) {
            otpBoxes.get(i).click();
            otpBoxes.get(i).sendKeys(String.valueOf(otp.charAt(i)));
            sleep(300);
        }
        sleep(3000);
        if (tapByText(driver, "Verify", true, 5) || tapByText(driver, "Continue", true, 3)) {
            sleep(4000);
        }

        for (int i = 0; i < 8; i++) {
            sleep(2000);
            if (tapByText(driver, "While using the app", true, 3)
                    || tapByText(driver, "Continue", true, 3)
                    || tapByText(driver, "Allow", false, 3)
                    || tapByText(driver, "Skip", true, 3)) {
                continue;
            }
            break;
        }
        sleep(3000);
        recordScreen(state, driver, "post_login_home");
        state.balance = extractBalance(driver);
    }

    public static void actionGetBalance(AndroidDriver driver, TestState state) {
        state.balance = extractBalance(driver);
        recordScreen(state, driver, "get_balance");
    }

    public static void actionGotoProduct(AndroidDriver driver, TestState state) {
        tapByText(driver, "More", false, 5);
        sleep(2000);
        tapByText(driver, "Booost Buy", false, 5);
        sleep(3000);
        tapByText(driver, "Vouchers", false, 5);
        sleep(3000);

        // Search first rather than assuming the product is already visible
        // on-screen without scrolling -- this is what lets any catalog
        // product be found and bought generically. Confirmed live: the
        // search box filters as you type.
        typeIntoElement(driver, "//android.widget.EditText", state.productName);
        sleep(2000);
        driver.hideKeyboard();
        sleep(1000);

        // Scoped to TextView specifically, not a generic "any element"
        // match: after typing, the search box's own text attribute equals
        // the product name too, so an unscoped match can grab the search
        // box itself (a real risk, not hypothetical) instead of the tile.
        List<WebElement> tiles = driver.findElements(
                By.xpath(String.format("//android.widget.TextView[@text='%s']", state.productName)));
        if (tiles.isEmpty()) {
            throw new RuntimeException("product not found in catalog after searching: " + state.productName);
        }
        tiles.get(0).click();
        sleep(3000);

        if (state.productAmount != null && !state.productAmount.isEmpty()) {
            typeIntoElement(driver, "//android.widget.EditText", state.productAmount);
            driver.hideKeyboard();
            sleep(1000);
        }
        recordScreen(state, driver, "product_detail_" + state.productName);
    }

    public static void actionStartCheckout(AndroidDriver driver, TestState state) {
        if (!tapByText(driver, "Buy now", false, 5)) {
            throw new RuntimeException("could not find Buy now");
        }
        sleep(3000);
        state.balanceBefore = extractBalance(driver);
        recordScreen(state, driver, "checkout_opened");
    }

    public static void actionSetPayment(AndroidDriver driver, TestState state) {
        String method = state.paymentMethod == null ? "points" : state.paymentMethod;
        if (method.equals("points")) {
            return;
        }
        String amount = (method.equals("card_saved") || method.equals("card_new"))
                ? "0"
                : nullToEmpty(state.boostsAmount).isEmpty() ? "0" : state.boostsAmount;
        typeIntoElement(driver, "//*[contains(@class,'EditText')]", amount, 0, true, 3);
        sleep(1000);
        driver.hideKeyboard();
        sleep(1000);
        recordScreen(state, driver, "payment_split_set");
    }

    private static void fillNewCard(AndroidDriver driver, TestState state) {
        if (!tapByText(driver, "Add new payment method", false, 5)) {
            throw new RuntimeException("could not find 'Add new payment method'");
        }
        sleep(2000);
        recordScreen(state, driver, "add_new_card_form");

        // Confirmed 4 fields in this order: Card Number, Expiry (single
        // "MM / YY" field, auto-formatted as you type), CVC, Card Holder
        // Name -- the 4th is required by Peach and was missed in an
        // earlier version, which only supplied 3 values and left it blank.
        List<String> values = List.of(
                nullToEmpty(state.cardNumber),
                nullToEmpty(state.cardExp),
                nullToEmpty(state.cardCvc),
                nullToEmpty(state.cardHolderName));
        for (int i = 0; i < values.size(); i++) {
            if (!values.get(i).isEmpty()) {
                typeIntoElement(driver, "//android.widget.EditText", values.get(i), i, false, 3);
                sleep(500);
            }
        }
        driver.hideKeyboard();
        sleep(1000);
        recordScreen(state, driver, "new_card_filled");
    }

    /** Returns "peach", "result", or null (neither showed up in time) --
     * which branch fires next depends on which one actually renders first,
     * so this has to poll for both rather than assume a fixed delay. */
    private static String waitForPeachOrResult(AndroidDriver driver, int timeoutSeconds) {
        long deadline = System.currentTimeMillis() + timeoutSeconds * 1000L;
        while (System.currentTimeMillis() < deadline) {
            if (!driver.findElements(By.xpath("//*[contains(@text,'Peach Payments')]")).isEmpty()) {
                return "peach";
            }
            if (!driver.findElements(By.xpath(
                    "//*[contains(@text,'Purchase complete') or contains(@text,'declined') or contains(@text,'failed')]"))
                    .isEmpty()) {
                return "result";
            }
            sleep(1000);
        }
        return null;
    }

    public static void actionCheckout(AndroidDriver driver, TestState state) {
        if (!tapByText(driver, "Pay now", false, 5)) {
            throw new RuntimeException("could not find Pay now on checkout screen");
        }

        String method = state.paymentMethod == null ? "points" : state.paymentMethod;
        String branch = waitForPeachOrResult(driver, 20);
        if ("peach".equals(branch)) {
            recordScreen(state, driver, "peach_modal");

            if ("card_new".equals(method)) {
                fillNewCard(driver, state);
            } else {
                typeIntoElement(driver, "//*[contains(@class,'EditText')]", state.cardCvc, -1, false, 3);
                driver.hideKeyboard();
                sleep(1000);
            }

            if (!state.completePurchase) {
                state.stoppedBeforePayment = true;
                return;
            }

            if (tapByText(driver, "Pay Now", false, 5)) {
                sleep(4000);
                recordScreen(state, driver, "after_peach_pay_now");
                tapByText(driver, "Submit", false, 8); // 3DS mock, Approve by default
            }
        } else if (branch == null) {
            throw new RuntimeException("neither the Peach modal nor a payment result appeared after Pay now");
        }
        // branch == "result": a full-points payment skips the modal
        // entirely and lands straight on the result screen.

        if (!waitForAnyText(driver, List.of("Purchase complete", "declined", "failed"), 30)) {
            throw new RuntimeException("payment did not reach a terminal state within timeout");
        }

        recordScreen(state, driver, "payment_result");
        List<String> texts = state.screens.get(state.screens.size() - 1).texts;
        state.orderId = texts.stream()
                .filter(t -> t.startsWith("ORDER #"))
                .map(t -> t.replace("ORDER #", ""))
                .findFirst().orElse(null);
        state.status = texts.stream().anyMatch(t -> t.contains("declined") || t.contains("failed"))
                ? "declined" : "complete";
        state.balanceAfter = extractBalance(driver);
    }

    public static void actionVoucherDetails(AndroidDriver driver, TestState state) {
        if (tapByText(driver, "Order details", false, 5)) {
            long deadline = System.currentTimeMillis() + 15_000;
            while (System.currentTimeMillis() < deadline) {
                if (!driver.findElements(By.xpath("//*[contains(@text,'wiCode')]")).isEmpty()) {
                    break;
                }
                sleep(1000);
            }
            recordScreen(state, driver, "order_details");
            state.wicode = state.screens.get(state.screens.size() - 1).texts.stream()
                    .filter(t -> t.length() >= 6 && t.chars().allMatch(Character::isDigit))
                    .findFirst().orElse(null);
        }
    }

    /** Navigate away from the Purchase complete screen and re-read the
     * balance. Works around a confirmed app bug: that screen's own balance
     * badge can show the stale pre-purchase value for a few seconds (see
     * README) -- so asserting the delta on it directly is flaky by nature
     * of the app, not the test. Re-reading after navigating elsewhere is
     * stable. */
    public static void actionRecheckBalance(AndroidDriver driver, TestState state) {
        if (tapByText(driver, "Booost Buy", false, 5)) {
            sleep(3000);
            recordScreen(state, driver, "balance_recheck");
            state.balanceSettled = extractBalance(driver);
        }
    }
}

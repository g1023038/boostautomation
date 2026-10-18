"""
Composable Booost app actions. Each action is a small function that does one
thing and appends whatever was visible on screen to state["screens"] (for
verification later) -- they're meant to be run standalone or chained.

Chaining is driven by STEPS (comma-separated action names) + a flat set of
option env vars read once into `state` at startup. Examples:

  Just check balances for a user (no purchase at all):
    STEPS=login,get_balance

  Buy but stop short of actually paying (inspect checkout state only):
    STEPS=login,goto_product,start_checkout,set_payment,checkout
    COMPLETE_PURCHASE=false

  Buy with a card that isn't already saved on the account:
    STEPS=login,goto_product,start_checkout,set_payment,checkout
    PAYMENT_METHOD=card_new
    CARD_NUMBER=4200000000000091 CARD_EXP_MONTH=12 CARD_EXP_YEAR=28 CARD_CVC=123

  Full purchase with the already-saved card:
    PAYMENT_METHOD=card_saved

  Split tender:
    PAYMENT_METHOD=split BOOSTS_AMOUNT=5

PRODUCT_NAME is required for any step from goto_product onward.
Output: one JSON object (also written to result.json) with every option used,
the final balances, order id / wiCode if a purchase happened, and the full
list of per-screen scrapes under "screens".
"""
import json
import os
import sys
import time
import xml.etree.ElementTree as ET

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy

APP_ID = "lt://APP10160362051791552008064620"
HUB_URL = "https://mobile-hub.lambdatest.com/wd/hub"


# ---------------------------------------------------------------- low level

def tap_by_text(driver, text, contains=True, timeout=15):
    xpath = f"//*[contains(@text, '{text}')]" if contains else f"//*[@text='{text}']"
    deadline = time.time() + timeout
    while time.time() < deadline:
        els = driver.find_elements(AppiumBy.XPATH, xpath)
        if els:
            els[0].click()
            return True
        time.sleep(1)
    return False


def wait_for_any_text(driver, texts, timeout=30):
    deadline = time.time() + timeout
    xpath = " or ".join(f"contains(@text,'{t}')" for t in texts)
    while time.time() < deadline:
        if driver.find_elements(AppiumBy.XPATH, f"//*[{xpath}]"):
            return True
        time.sleep(2)
    return False


def scrape_screen(driver, label):
    """Every piece of text visible on screen right now, for verification.
    One page_source snapshot parsed once -- never walks live WebElements."""
    root = ET.fromstring(driver.page_source)
    texts = [el.get("text") for el in root.iter() if el.get("text")]
    return {"screen": label, "texts": texts}


def record_screen(state, driver, label):
    """scrape_screen + append + flush to result.json immediately, so a crash
    midway through a multi-stage action (e.g. action_checkout) still leaves
    every screen seen so far on disk for diagnosis."""
    state["screens"].append(scrape_screen(driver, label))
    with open("result.json", "w") as f:
        json.dump(state, f, indent=2)


def extract_balance(driver):
    # The balance badge is the only bare "NN.NN" TextView with no currency
    # prefix (prices/amounts always render as "R10.00" / "B13.00" -- the
    # letter is part of the same text node, confirmed from real dumps).
    root = ET.fromstring(driver.page_source)
    for el in root.iter("android.widget.TextView"):
        text = el.get("text") or ""
        if text.replace(".", "", 1).isdigit() and "." in text:
            return float(text)
    return None


# -------------------------------------------------------------------- steps

def action_login(driver, state):
    time.sleep(10)
    for _ in range(5):
        if tap_by_text(driver, "Get Started", timeout=3) or tap_by_text(driver, "Next", timeout=3):
            time.sleep(2)
            continue
        break
    time.sleep(2)

    id_field = driver.find_element(
        AppiumBy.XPATH, "//android.widget.EditText[.//android.widget.TextView[@text='ID number']]")
    id_field.click()
    id_field.send_keys(state["id_number"])
    time.sleep(2)
    driver.hide_keyboard()
    time.sleep(1)
    if tap_by_text(driver, "Continue", timeout=5):
        time.sleep(3)

    phone_field = driver.find_element(
        AppiumBy.XPATH, "//android.widget.EditText[.//android.widget.TextView[contains(@text,'Cellphone number')]]")
    phone_field.click()
    phone_field.send_keys(state["phone"])
    time.sleep(2)
    driver.hide_keyboard()
    time.sleep(1)
    if tap_by_text(driver, "Continue", timeout=5):
        time.sleep(3)

    otp_boxes = driver.find_elements(AppiumBy.CLASS_NAME, "android.widget.EditText")
    otp_boxes = sorted(otp_boxes, key=lambda e: int(e.get_attribute("bounds").split(",")[0].strip("[")))
    for box, digit in zip(otp_boxes, state["otp"]):
        box.click()
        box.send_keys(digit)
        time.sleep(0.3)
    time.sleep(3)
    if tap_by_text(driver, "Verify", timeout=5) or tap_by_text(driver, "Continue", timeout=3):
        time.sleep(4)

    for _ in range(8):
        time.sleep(2)
        if (tap_by_text(driver, "While using the app", timeout=3)
                or tap_by_text(driver, "Continue", timeout=3)
                or tap_by_text(driver, "Allow", timeout=3, contains=False)
                or tap_by_text(driver, "Skip", timeout=3)):
            continue
        break
    time.sleep(3)
    record_screen(state, driver, "post_login_home")
    state["balance"] = extract_balance(driver)


def action_get_balance(driver, state):
    state["balance"] = extract_balance(driver)
    record_screen(state, driver, "get_balance")


def action_goto_product(driver, state):
    tap_by_text(driver, "More", timeout=5, contains=False)
    time.sleep(2)
    tap_by_text(driver, "Booost Buy", timeout=5, contains=False)
    time.sleep(3)
    tap_by_text(driver, "Vouchers", timeout=5, contains=False)
    time.sleep(3)
    if not tap_by_text(driver, state["product_name"], timeout=5, contains=False):
        raise RuntimeError(f"product not found in catalog: {state['product_name']!r}")
    time.sleep(3)

    if state.get("product_amount"):
        fields = driver.find_elements(AppiumBy.XPATH, "//android.widget.EditText")
        if fields:
            fields[0].click()
            fields[0].send_keys(str(state["product_amount"]))
            driver.hide_keyboard()
            time.sleep(1)
    record_screen(state, driver, f"product_detail_{state['product_name']}")


def action_start_checkout(driver, state):
    if not tap_by_text(driver, "Buy now", timeout=5, contains=False):
        raise RuntimeError("could not find Buy now")
    time.sleep(3)
    state["balance_before"] = extract_balance(driver)
    record_screen(state, driver, "checkout_opened")


def action_set_payment(driver, state):
    method = state.get("payment_method", "points")
    if method == "points":
        return
    boxes = driver.find_elements(AppiumBy.XPATH, "//*[contains(@class,'EditText')]")
    boosts_box = boxes[0]
    boosts_box.click()
    boosts_box.clear()
    boosts_box.send_keys("0" if method in ("card_saved", "card_new") else str(state.get("boosts_amount", "0")))
    time.sleep(1)
    driver.hide_keyboard()
    time.sleep(1)
    record_screen(state, driver, "payment_split_set")


def _fill_new_card(driver, state):
    if not tap_by_text(driver, "Add new payment method", timeout=5, contains=False):
        raise RuntimeError("could not find 'Add new payment method'")
    time.sleep(2)
    record_screen(state, driver, "add_new_card_form")
    # Confirmed 4 fields in this order: Card Number, Expiry (single "MM / YY"
    # field, auto-formatted as you type), CVC, Card Holder Name -- the 4th
    # is required by Peach and was missed in an earlier version of this
    # function, which only supplied 3 values and left it blank.
    fields = driver.find_elements(AppiumBy.XPATH, "//android.widget.EditText")
    values = [
        state.get("card_number"),
        state.get("card_exp"),
        state.get("card_cvc", "123"),
        state.get("card_holder_name", "Test User"),
    ]
    for field, value in zip(fields, values):
        if value:
            field.click()
            field.send_keys(str(value))
            time.sleep(0.5)
    driver.hide_keyboard()
    time.sleep(1)
    record_screen(state, driver, "new_card_filled")


def _wait_for_peach_or_result(driver, timeout=20):
    """Returns 'peach', 'result', or None (neither showed up in time) --
    which branch fires next depends on which one actually renders first,
    so this has to poll for both rather than assume a fixed delay."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if driver.find_elements(AppiumBy.XPATH, "//*[contains(@text,'Peach Payments')]"):
            return "peach"
        if driver.find_elements(
                AppiumBy.XPATH,
                "//*[contains(@text,'Purchase complete') or contains(@text,'declined') or contains(@text,'failed')]"):
            return "result"
        time.sleep(1)
    return None


def action_checkout(driver, state):
    if not tap_by_text(driver, "Pay now", timeout=5, contains=False):
        raise RuntimeError("could not find Pay now on checkout screen")

    method = state.get("payment_method", "points")
    branch = _wait_for_peach_or_result(driver)
    if branch == "peach":
        record_screen(state, driver, "peach_modal")

        if method == "card_new":
            _fill_new_card(driver, state)
        else:
            cvc_fields = driver.find_elements(AppiumBy.XPATH, "//*[contains(@class,'EditText')]")
            if cvc_fields:
                cvc_fields[-1].click()
                cvc_fields[-1].send_keys(state.get("card_cvc", "123"))
                driver.hide_keyboard()
                time.sleep(1)

        if not state.get("complete_purchase", True):
            state["stopped_before_payment"] = True
            return

        if tap_by_text(driver, "Pay Now", timeout=5, contains=False):
            time.sleep(4)
            record_screen(state, driver, "after_peach_pay_now")
            tap_by_text(driver, "Submit", timeout=8, contains=False)  # 3DS mock, Approve by default
    elif branch is None:
        raise RuntimeError("neither the Peach modal nor a payment result appeared after Pay now")
    # branch == "result": a full-points payment skips the modal entirely and
    # lands straight on the result screen -- nothing else to do before the
    # final wait below, which will resolve immediately.

    if not wait_for_any_text(driver, ["Purchase complete", "declined", "failed"], timeout=30):
        raise RuntimeError("payment did not reach a terminal state within timeout")

    record_screen(state, driver, "payment_result")
    texts = state["screens"][-1]["texts"]
    state["order_id"] = next((t.replace("ORDER #", "") for t in texts if t.startswith("ORDER #")), None)
    state["status"] = "declined" if any("declined" in t or "failed" in t for t in texts) else "complete"
    state["balance_after"] = extract_balance(driver)


def action_voucher_details(driver, state):
    if tap_by_text(driver, "Order details", timeout=5, contains=False):
        deadline = time.time() + 15
        while time.time() < deadline:
            if driver.find_elements(AppiumBy.XPATH, "//*[contains(@text,'wiCode')]"):
                break
            time.sleep(1)
        record_screen(state, driver, "order_details")
        state["wicode"] = next((t for t in state["screens"][-1]["texts"] if t.isdigit() and len(t) >= 6), None)


def action_recheck_balance(driver, state):
    """Navigate away from the Purchase complete screen and re-read the
    balance. Works around a confirmed app bug: that screen's own balance
    badge can show the stale pre-purchase value for a few seconds (see
    README) -- so asserting the delta on it directly is flaky by nature of
    the app, not the test. Re-reading after navigating elsewhere is stable."""
    if tap_by_text(driver, "Booost Buy", timeout=5, contains=False):
        time.sleep(3)
        record_screen(state, driver, "balance_recheck")
        state["balance_settled"] = extract_balance(driver)


ACTIONS = {
    "login": action_login,
    "get_balance": action_get_balance,
    "goto_product": action_goto_product,
    "start_checkout": action_start_checkout,
    "set_payment": action_set_payment,
    "checkout": action_checkout,
    "voucher_details": action_voucher_details,
    "recheck_balance": action_recheck_balance,
}


DEFAULT_STEPS = "login,goto_product,start_checkout,set_payment,checkout,voucher_details"


def main():
    steps = os.environ.get("STEPS", DEFAULT_STEPS).split(",")
    state = {
        "id_number": os.environ["TEST_ID_NUMBER"],
        "phone": os.environ["TEST_PHONE_LOCAL"],
        "otp": os.environ.get("TEST_OTP", "123456"),
        "product_name": os.environ.get("PRODUCT_NAME"),
        "product_amount": os.environ.get("PRODUCT_AMOUNT"),
        "payment_method": os.environ.get("PAYMENT_METHOD", "points"),
        "boosts_amount": os.environ.get("BOOSTS_AMOUNT"),
        "card_number": os.environ.get("CARD_NUMBER"),
        "card_exp": os.environ.get("CARD_EXP"),
        "card_cvc": os.environ.get("CARD_CVC", "123"),
        "card_holder_name": os.environ.get("CARD_HOLDER_NAME", "Test User"),
        "complete_purchase": os.environ.get("COMPLETE_PURCHASE", "true").lower() == "true",
        "screens": [],
    }

    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.app = APP_ID
    options.set_capability("lt:options", {
        "username": os.environ["LT_USERNAME"],
        "accessKey": os.environ["LT_ACCESS_KEY"],
        "deviceName": os.environ.get("LT_DEVICE", "Galaxy S23"),
        "platformVersion": os.environ.get("LT_PLATFORM_VERSION", "13"),
        "isRealMobile": True,
        "build": "boost-actions",
        "name": "+".join(steps),
    })

    driver = webdriver.Remote(HUB_URL, options=options)
    try:
        for step in steps:
            print(f"--- running step: {step} ---", file=sys.stderr)
            ACTIONS[step](driver, state)
    finally:
        driver.quit()
        with open("result.json", "w") as f:
            json.dump(state, f, indent=2)

    print(json.dumps(state, indent=2))


if __name__ == "__main__":
    sys.exit(main() or 0)

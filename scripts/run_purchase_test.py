"""
Parameterized Booost Buy purchase test, driven entirely by inputs -- no
hardcoded product or payment method. This is the real, reusable version of
what scripts/explore_app.py discovered by hand.

Inputs (all via environment variables, so this can be called the same way
from a human's terminal, a GitHub Actions workflow_dispatch, or eventually a
Rovo/Forge action):

  LT_USERNAME, LT_ACCESS_KEY      LambdaTest credentials
  TEST_ID_NUMBER, TEST_PHONE_LOCAL, TEST_OTP   login credentials
  PRODUCT_NAME                    exact catalog tile text, e.g. "Plato Coffee"
  PRODUCT_AMOUNT                  only for variable-denomination products
                                   (e.g. KFC_Display) -- the Rand amount to enter
  PAYMENT_METHOD                  "points" | "card" | "split"
  BOOSTS_AMOUNT                   only for PAYMENT_METHOD=split -- the portion
                                   to pay with Booosts; the rest goes to card
  CARD_CVC                        CVC for the saved Peach Payments test card
                                   (default "123" -- the saved card itself is
                                   provisioned on the PPE test account already)

Output: a single JSON object printed to stdout (and saved to
result.json) with order_id, balance_before, balance_after, and wicode --
exactly what a CI step or a chat-triggered run needs to report back.
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


def read_balance(driver):
    # Parse one page_source snapshot rather than walking live WebElements one
    # at a time -- find_elements() + per-element get_attribute() calls can hit
    # StaleElementReferenceException if the UI re-renders between them.
    # The balance badge is the only header TextView whose text is a bare
    # "NN.NN" number with no currency prefix (UiAutomator2's XPath engine is
    # XPath 1.0, so this filter has to happen in Python, not via matches()).
    root = ET.fromstring(driver.page_source)
    for el in root.iter("android.widget.TextView"):
        text = el.get("text") or ""
        if text.replace(".", "", 1).isdigit() and "." in text:
            return float(text)
    return None


def wait_for_any_text(driver, texts, timeout=30):
    deadline = time.time() + timeout
    xpath = " or ".join(f"contains(@text,'{t}')" for t in texts)
    while time.time() < deadline:
        if driver.find_elements(AppiumBy.XPATH, f"//*[{xpath}]"):
            return True
        time.sleep(2)
    return False


def login(driver):
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
    id_field.send_keys(os.environ["TEST_ID_NUMBER"])
    time.sleep(2)
    driver.hide_keyboard()
    time.sleep(1)
    if tap_by_text(driver, "Continue", timeout=5):
        time.sleep(3)

    phone_field = driver.find_element(
        AppiumBy.XPATH, "//android.widget.EditText[.//android.widget.TextView[contains(@text,'Cellphone number')]]")
    phone_field.click()
    phone_field.send_keys(os.environ["TEST_PHONE_LOCAL"])
    time.sleep(2)
    driver.hide_keyboard()
    time.sleep(1)
    if tap_by_text(driver, "Continue", timeout=5):
        time.sleep(3)

    otp_boxes = driver.find_elements(AppiumBy.CLASS_NAME, "android.widget.EditText")
    otp_boxes = sorted(otp_boxes, key=lambda e: int(e.get_attribute("bounds").split(",")[0].strip("[")))
    otp = os.environ.get("TEST_OTP", "123456")
    for box, digit in zip(otp_boxes, otp):
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


def goto_product(driver, product_name):
    tap_by_text(driver, "More", timeout=5, contains=False)
    time.sleep(2)
    tap_by_text(driver, "Booost Buy", timeout=5, contains=False)
    time.sleep(3)
    tap_by_text(driver, "Vouchers", timeout=5, contains=False)
    time.sleep(3)
    if not tap_by_text(driver, product_name, timeout=5, contains=False):
        raise RuntimeError(f"product not found in catalog: {product_name!r}")
    time.sleep(3)


def set_amount_if_variable(driver, amount):
    if not amount:
        return
    fields = driver.find_elements(AppiumBy.XPATH, "//android.widget.EditText")
    if fields:
        fields[0].click()
        fields[0].send_keys(str(amount))
        driver.hide_keyboard()
        time.sleep(1)


def set_payment_split(driver, payment_method, boosts_amount):
    if payment_method == "points":
        return  # default: fully paid with Booosts, nothing to change
    boxes = driver.find_elements(AppiumBy.XPATH, "//*[contains(@class,'EditText')]")
    boosts_box = boxes[0]
    boosts_box.click()
    boosts_box.clear()
    boosts_box.send_keys("0" if payment_method == "card" else str(boosts_amount))
    time.sleep(1)
    driver.hide_keyboard()
    time.sleep(1)


def pay_and_handle_peach(driver):
    if not tap_by_text(driver, "Pay now", timeout=5, contains=False):
        raise RuntimeError("could not find Pay now on checkout screen")
    time.sleep(4)

    # A full-points payment skips straight to "Purchase complete" -- only
    # card/split payments show the Peach Payments modal. Check for its own
    # marker text before touching any EditText, otherwise a slow transition
    # can hand back a stale reference to the checkout screen's own amount
    # boxes instead of the modal's CVC field.
    if driver.find_elements(AppiumBy.XPATH, "//*[contains(@text,'Peach Payments')]"):
        cvc_fields = driver.find_elements(AppiumBy.XPATH, "//*[contains(@class,'EditText')]")
        if cvc_fields:
            cvc_fields[-1].click()
            cvc_fields[-1].send_keys(os.environ.get("CARD_CVC", "123"))
            driver.hide_keyboard()
            time.sleep(1)
        if tap_by_text(driver, "Pay Now", timeout=5, contains=False):
            time.sleep(4)
            # 3DS mock challenge (Peach "Demo Bank") -- Approve is selected by default.
            tap_by_text(driver, "Submit", timeout=8, contains=False)

    if not wait_for_any_text(driver, ["Purchase complete", "declined", "failed"], timeout=30):
        raise RuntimeError("payment did not reach a terminal state within timeout")


def main():
    product_name = os.environ["PRODUCT_NAME"]
    payment_method = os.environ.get("PAYMENT_METHOD", "points")
    product_amount = os.environ.get("PRODUCT_AMOUNT")
    boosts_amount = os.environ.get("BOOSTS_AMOUNT")

    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.app = APP_ID
    options.set_capability("lt:options", {
        "username": os.environ["LT_USERNAME"],
        "accessKey": os.environ["LT_ACCESS_KEY"],
        "deviceName": os.environ.get("LT_DEVICE", "Galaxy S23"),
        "platformVersion": os.environ.get("LT_PLATFORM_VERSION", "13"),
        "isRealMobile": True,
        "build": "purchase-test",
        "name": f"{product_name}-{payment_method}",
    })

    driver = webdriver.Remote(HUB_URL, options=options)
    result = {"product": product_name, "payment_method": payment_method}
    try:
        login(driver)
        goto_product(driver, product_name)
        set_amount_if_variable(driver, product_amount)

        result["balance_before"] = read_balance(driver)

        if not tap_by_text(driver, "Buy now", timeout=5, contains=False):
            raise RuntimeError("could not find Buy now")
        time.sleep(3)

        set_payment_split(driver, payment_method, boosts_amount)
        pay_and_handle_peach(driver)

        order_els = driver.find_elements(AppiumBy.XPATH, "//*[contains(@text,'ORDER #')]")
        result["order_id"] = order_els[0].get_attribute("text").replace("ORDER #", "") if order_els else None
        result["status"] = "declined" if driver.find_elements(
            AppiumBy.XPATH, "//*[contains(@text,'declined') or contains(@text,'failed')]") else "complete"

        if tap_by_text(driver, "Order details", timeout=5, contains=False):
            time.sleep(3)
            # Verified structure: ['Order details', 'Online', 'In-store',
            # <product>, <price>, 'wiCode', '83508200', 'How to use', ...] --
            # the wiCode is the only bare digit string (>=6 digits) on this screen.
            order_root = ET.fromstring(driver.page_source)
            all_texts = [el.get("text") for el in order_root.iter("android.widget.TextView") if el.get("text")]
            result["wicode"] = next((t for t in all_texts if t.isdigit() and len(t) >= 6), None)

        result["balance_after"] = read_balance(driver)
    finally:
        driver.quit()

    print(json.dumps(result, indent=2))
    with open("result.json", "w") as f:
        json.dump(result, f, indent=2)


if __name__ == "__main__":
    sys.exit(main() or 0)

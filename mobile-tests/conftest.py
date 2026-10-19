import os

import pytest
from appium import webdriver
from appium.options.android import UiAutomator2Options

from boost_actions import APP_ID, HUB_URL


@pytest.fixture
def driver():
    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.app = APP_ID
    options.set_capability("lt:options", {
        "username": os.environ["LT_USERNAME"],
        "accessKey": os.environ["LT_ACCESS_KEY"],
        "deviceName": os.environ.get("LT_DEVICE", "Galaxy S23"),
        "platformVersion": os.environ.get("LT_PLATFORM_VERSION", "13"),
        "isRealMobile": True,
        "build": "pytest-mobile-tests",
        "name": "boost-app-tests",
    })
    d = webdriver.Remote(HUB_URL, options=options)
    yield d
    d.quit()


@pytest.fixture
def base_state():
    return {
        "id_number": os.environ["TEST_ID_NUMBER"],
        "phone": os.environ["TEST_PHONE_LOCAL"],
        "otp": os.environ.get("TEST_OTP") or "123456",
        "card_cvc": os.environ.get("CARD_CVC", "123"),
        "card_holder_name": os.environ.get("CARD_HOLDER_NAME", "Test User"),
        "complete_purchase": True,
        "screens": [],
    }

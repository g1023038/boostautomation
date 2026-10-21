package com.boostautomation.actions;

import io.appium.java_client.android.AndroidDriver;
import io.appium.java_client.android.options.UiAutomator2Options;

import java.net.MalformedURLException;
import java.net.URL;
import java.util.Map;

/** Builds the Appium session against LambdaTest's real-device cloud --
 * same app id, hub url and lt:options capability shape as boost_actions.py
 * and conftest.py, just not duplicated per call site. */
public final class DriverFactory {
    public static final String APP_ID = "lt://APP10160362051791552008064620";
    public static final String HUB_URL = "https://mobile-hub.lambdatest.com/wd/hub";

    private DriverFactory() {
    }

    public static AndroidDriver createDriver(String build, String name) {
        UiAutomator2Options options = new UiAutomator2Options();
        options.setPlatformName("Android");
        options.setApp(APP_ID);
        options.setCapability("lt:options", Map.of(
                "username", requireEnv("LT_USERNAME"),
                "accessKey", requireEnv("LT_ACCESS_KEY"),
                "deviceName", getenvOr("LT_DEVICE", "Galaxy S23"),
                "platformVersion", getenvOr("LT_PLATFORM_VERSION", "13"),
                "isRealMobile", true,
                "build", build,
                "name", name));
        try {
            return new AndroidDriver(new URL(HUB_URL), options);
        } catch (MalformedURLException e) {
            throw new IllegalStateException("invalid HUB_URL: " + HUB_URL, e);
        }
    }

    private static String getenvOr(String key, String def) {
        String value = System.getenv(key);
        return (value == null || value.isEmpty()) ? def : value;
    }

    private static String requireEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isEmpty()) {
            throw new IllegalStateException("required environment variable not set: " + key);
        }
        return value;
    }
}

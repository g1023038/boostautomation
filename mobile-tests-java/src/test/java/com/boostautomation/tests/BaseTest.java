package com.boostautomation.tests;

import com.boostautomation.actions.DriverFactory;
import com.boostautomation.actions.TestState;
import io.appium.java_client.android.AndroidDriver;
import org.testng.annotations.AfterMethod;
import org.testng.annotations.BeforeMethod;

/** Java equivalent of conftest.py's `driver` + `base_state` fixtures --
 * same build/session naming so these sessions land in the same
 * "pytest-mobile-tests" LambdaTest build the Python suite already uses. */
public abstract class BaseTest {

    protected AndroidDriver driver;
    protected TestState state;

    @BeforeMethod
    public void setUp() {
        driver = DriverFactory.createDriver("pytest-mobile-tests", "boost-app-tests");
        state = TestState.fromEnv();
    }

    @AfterMethod
    public void tearDown() {
        if (driver != null) {
            driver.quit();
        }
    }
}

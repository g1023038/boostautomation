package com.boostautomation.tests;

import com.boostautomation.actions.DriverFactory;
import com.boostautomation.actions.TestState;
import com.fasterxml.jackson.databind.JsonNode;
import io.appium.java_client.android.AndroidDriver;
import org.testng.annotations.AfterMethod;
import org.testng.annotations.BeforeMethod;

import java.lang.reflect.Method;

/** Java equivalent of conftest.py's `driver` + `base_state` fixtures. Own
 * build name, deliberately not the Python suite's "pytest-mobile-tests" --
 * sharing one build name across two languages' test runners made the
 * LambdaTest dashboard unable to tell them apart without opening each
 * session individually. */
public abstract class BaseTest {

    private static final String BUILD = "testng-mobile-tests-java";

    protected AndroidDriver driver;
    protected TestState state;

    @BeforeMethod
    public void setUp(Method method, Object[] params) {
        // TestNG injects the running @Test method (and its DataProvider
        // params, if any) when a @BeforeMethod declares them -- every
        // session on the LambdaTest dashboard used to show up as the same
        // "boost-app-tests" regardless of which test ran, same issue the
        // Python suite's hardcoded fixture name had. method.getName() plus
        // the scenario id (when the first param is a JsonNode scenario
        // with an "id" field) mirrors pytest's bracketed parametrize id,
        // e.g. "purchaseScenarioCompletes[plato_coffee_card_saved]".
        driver = DriverFactory.createDriver(BUILD, sessionName(method, params));
        state = TestState.fromEnv();
    }

    private static String sessionName(Method method, Object[] params) {
        if (params.length > 0 && params[0] instanceof JsonNode) {
            JsonNode id = ((JsonNode) params[0]).get("id");
            if (id != null) {
                return method.getName() + "[" + id.asText() + "]";
            }
        }
        return method.getName();
    }

    @AfterMethod
    public void tearDown() {
        if (driver != null) {
            driver.quit();
        }
    }
}

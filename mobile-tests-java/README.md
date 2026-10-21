# Java port of mobile-tests

Same composable-actions design as `../mobile-tests/ARCHITECTURE.md` -- read
that first, it isn't Python-specific -- ported to Appium's Java client +
TestNG so devs who don't read Python can extend this directly.

| Python (`../mobile-tests/`) | Java (here) |
|---|---|
| `boost_actions.py` (the `action_*` functions) | `src/main/java/.../BoostActions.java` |
| `boost_actions.py` (the `state` dict) | `src/main/java/.../TestState.java` |
| `boost_actions.py` (CLI `main()` / `STEPS`) | `src/main/java/.../BoostActionsRunner.java` |
| `conftest.py` (`driver` / `base_state` fixtures) | `src/test/java/.../BaseTest.java` |
| `test_balance.py` | `src/test/java/.../BalanceTest.java` |
| `test_purchases.py` | `src/test/java/.../PurchaseTest.java` |

Both languages read the same
`../testdata/reference/booost_buy_purchase_scenarios.json` -- add a
scenario there once, it's picked up by both suites, not duplicated.

## Running

Same required env vars as the Python suite: `LT_USERNAME`, `LT_ACCESS_KEY`,
`TEST_ID_NUMBER`, `TEST_PHONE_LOCAL`. `TEST_OTP` is optional (falls back to
`123456`, same fix applied here as in the Python version -- a missing
GitHub secret comes through as an empty string, not an absent key).

```
mvn test
```

If `mvn test` fails immediately with a `SunCertPathBuilderException` /
`unable to find valid certification path` before any device session
starts, that's a local TLS-inspecting proxy (common on a corporate
network) -- Java's own trust store doesn't have the proxy's cert, same
root cause the Python suite hit (fixed there with `pip-system-certs`).
Java can read Windows' own trusted cert store directly instead of
needing a cert import:

```
mvn test -DargLine=-Djavax.net.ssl.trustStoreType=Windows-ROOT
```

Verified end to end on 2026-10-21: `BalanceTest` passed against a real
Galaxy S23 on LambdaTest (login, OTP entry, balance read all succeeded)
once that flag was set.

For the one-off/chat-triggered equivalent of `python boost_actions.py`:

```
mvn exec:java -Dexec.mainClass=com.boostautomation.actions.BoostActionsRunner
```

`STEPS`, `PRODUCT_NAME`, `PAYMENT_METHOD`, etc. are read as environment
variables (same names as the Python CLI), not Maven/system properties --
set them in the shell or CI environment before running.

## Not ported, on purpose

The AI-facing glue -- `scripts/test_automator_agent.py`,
`scripts/generate_script.py`, the Jira/Xray/LLM clients -- stays Python.
Nothing there is meant to be hand-read or hand-written by a human dev;
the automation agent is the only thing that touches it.

## Not yet wired up

This module isn't in any GitHub Actions workflow yet -- `run-purchase-test.yml`
and `execute-tests.yml` still only run the Python suite. Adding a parallel
Java job is a reasonable next step once this is in use, not done here.

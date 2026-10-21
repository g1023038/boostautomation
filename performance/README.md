# performance

JMeter `.jmx` test plans live here, run in non-GUI mode on a dedicated runner
(not every PR -- triggered separately, since perf runs are heavier and noisier
than functional tests).

Pending: no workflow wired up yet. Plan is `.jtl` results -> converted to
JUnit XML -> `scripts/publish_results.py` (same path functional results take)
to import into Xray as a Performance Test Execution, plus a summary pushed to
Confluence directly (no native JMeter-to-Jira integration exists, confirmed).

## `202609HRv6_BoostRegistrationLoadTest.jmx`

"BOOOST Auth & Identity Load Test" -- moved here from a local download, to be
edited further with Rovo. Two thread groups against `api-ppe.booost.com`
(host/protocol/etc. all overridable via `-J` properties):

- **BOOOST Registration Flow**: `/v1/auth/otp` -> `/v1/auth/verify` ->
  (if not already registered) `/v1/identity/register` -> `/v1/identity/status`
  -> `/v1/auth/refresh`.
- **Payments Order Flow**: hits a separate payments host
  (`payments-dev.internal.booost.com`) with `CreateEmptyOrderCommand` then
  `CreateOrderCommand` against `/v1/cart/executeCommand`.
- A Datadog backend listener ships metrics/logs if `ddApiKey` is set.

### It already generates its own test users -- worth reusing, not rebuilding

A `setUp` thread group runs a Groovy script ("Username Generator") *before*
the main flow that synthesizes `count` fresh identities (phone, SA ID, DOB,
name, email) and writes them to a CSV the main flow consumes via
`CSVDataSet`. The generator is self-contained, no API calls:

- SA ID numbers are built with a real Luhn-variant checksum, so they pass
  server-side validation as well-formed IDs.
- DOB is fixed at `2000-01-01` by default specifically because dev/PPE skips
  SMS delivery for that DOB and accepts any 6-digit OTP (`123456` is sent) --
  that's *why* `/auth/otp` -> `/auth/verify` works here with zero real SMS
  involved, not a JMeter trick.
- Phone numbers are synthesized in valid `+27` E.164 format from real SA
  mobile prefixes.

This is directly relevant to the mobile suite's long-standing gap (see
`../mobile-tests/README.md` / `ARCHITECTURE.md`): `mobile-tests/` and
`mobile-tests-java/` both still log in as one fixed, shared PPE account
(`TEST_ID_NUMBER`/`TEST_PHONE_LOCAL`), and that account's Boosts balance has
been draining all session with no top-up mechanism. The same
`/auth/otp -> /auth/verify -> /identity/register` flow this JMeter script
already drives could be called directly (same host, same three endpoints)
by `boost_actions.py` / `BoostActions.java` to provision a **brand-new**
identity per test run instead of reusing one shared account -- porting the
Groovy ID/phone generator (it's a small, self-contained algorithm, no
external dependency) to Python/Java would let the mobile suite "create its
own data" rather than needing one fed to it.

Caveat worth being upfront about: a freshly-registered identity almost
certainly starts with zero Boosts points, same as any new member would. That
solves state isolation (no more coordinating around one draining shared
account, no stale-vouchers/history cross-contamination between runs) but
likely does *not* by itself solve the "needs an existing points balance"
skip-guards in `test_buy_with_boost_points` / the split-payment scenario --
unless there's a known seed/promo mechanism for newly registered PPE
accounts, which hasn't been confirmed. Worth asking before building on this
assumption.

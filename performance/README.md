# performance

JMeter `.jmx` test plans live here, run in non-GUI mode on a dedicated runner
(not every PR -- triggered separately, since perf runs are heavier and noisier
than functional tests).

Pending: no workflow wired up yet. Plan is `.jtl` results -> converted to
JUnit XML -> `scripts/publish_results.py` (same path functional results take)
to import into Xray as a Performance Test Execution, plus a summary pushed to
Confluence directly (no native JMeter-to-Jira integration exists, confirmed).

## `202609HRv6_BoostRegistrationLoadTest.jmx`

"BOOOST Performance Test Suite" -- moved here from a local download, rebuilt
against the boost-auth-api Mobile Integration Guide and the Oct 2026 PPE
performance brief (4,000-5,000 expected users, payments out of scope for
that round). One plan, four thread groups, scenario selection is entirely
via `-J` thread-count properties (0 threads = that group does nothing) so
nothing needs hand-editing between runs:

| Thread group | Covers (brief's priority) | Threads property |
|---|---|---|
| `1 - Registration Load` | Registration (P0 #2) | `-JregUsers` |
| `2 - Login Authentication` | Login/auth (P0 #1), + Profile read, + logout/login cycles | `-JloginUsers` |
| `3 - Payments Order Flow` | out of scope this round, kept for later | `-JpayUsers` (default 0) |
| `4 - Mixed Journey` | Test 3's 5,000-user mixed workload | `-JmixedUsers` (mostly placeholders, see below) |

A Datadog backend listener ships every sampler's metrics/logs in real time if
`ddApiKey` is set -- this is what lines up JMeter and Datadog timestamps per
the brief's ask. Percentiles (p90/p95/p99) and per-endpoint breakdowns are
**not** computed inside the JMX; they come from the `results.jtl` file the
"Results File" collector writes (now enabled -- it was off in the original
download, which would have produced no results file at all in a non-GUI
run). Generate the dashboard after each run:

```
jmeter -g results.jtl -o dashboard/
```

### How to run each scenario from the brief

Two-phase for anything involving Login: a pool of identities has to actually
be registered (phase 1) before it can be used to test *login* (phase 2) --
you cannot log in as someone who was never registered.

```
# Phase 1 -- register N fresh identities, creates pool.csv
jmeter -n -t 202609HRv6_BoostRegistrationLoadTest.jmx \
  -Jcsvfile=pool.csv -JregUsers=N -JregRampup=secs -JregLoops=1 -l reg_results.jtl

# Phase 2 -- load-test login against that now-registered pool
jmeter -n -t 202609HRv6_BoostRegistrationLoadTest.jmx \
  -Jcsvfile=pool.csv -JloginUsers=N -JloginRampup=secs -JloginLoops=cycles -l login_results.jtl
```

- **Test 1 (baseline)**: small N (e.g. 10) through both phases, separately.
- **Test 2 (progressive)**: re-run phase 2 with `-JloginUsers` stepped
  250/500/1000/2000/3000/4000/5000 against the *same* pool (`CSVDataSet`
  recycles rows).
- **Test 4 (login spike)**: short `-JloginRampup` (concentrated) at
  500/1000/2000.
- **Test 5 (registration load)**: step `-JregUsers` 100/250/500/1000, fresh
  pool each step.
- **Test 6 (spike) / 7 (stress) / 8 (soak)**: same phase-2 invocation, vary
  `-JloginUsers` / `-JloginLoops` / `-JloginRampup` -- no separate JMX needed.
- **Test 3 (5,000-user mixed journey)**: blocked -- see below.

### Rate limit: the thing most likely to quietly break tomorrow's numbers

`/v1/auth/otp` is capped at **3 requests per phone per hour** and **10 per
IP per hour** (429 `rate_limit_exceeded`, confirmed in the Mobile
Integration Guide). A small identity pool recycled across thousands of
login iterations will mostly measure the rate limiter, not auth
performance. Rule of thumb: pool size &ge; (planned login attempts in any
rolling hour) / 3. For the 5,000-user target, that means **generating and
registering at least 5,000 distinct identities** before running Login at
that scale -- not reusing a smaller pool. Also flag the per-IP limit to the
backend team before tomorrow: if the JMeter load generators share only a
handful of egress IPs, 10/hour per IP can trip even with a large phone pool.

### Test 3 (Mixed Journey) and 7 of the brief's journeys are blocked on missing API docs

Only the boost-auth-api Mobile Integration Guide was provided. The brief
also asks for Home, Future Boost, Balance/transaction history, Vouchers
(browse only), Deals/Rewards, BAM, and Partner/loyalty -- none of those have
documented endpoints yet, so none are real in `4 - Mixed Journey`; they're
scaffolded as disabled placeholders (`${appApiHost}/v1/TODO/...`) carrying
the brief's own workload split (20/20/20/10/10/5/5/5/5) so filling them in
is a data edit (host, path, method, request/response shape) once the docs
exist, not a redesign. Login (20%) and Profile read (5%) are already real in
that group. The Profile *write* (PATCH `/v1/identity/profile`) is
documented and could be added too, but the brief says to keep
profile/settings read-based for this round.

To actually weight the 9 branches by the brief's percentages once they're
all real, use JMeter's `ThroughputController` in "Percent Executions" mode
per branch -- not done here, since wiring up a weighted controller for 7
branches that can't run yet would be complexity with nothing real to weight.

### Not independently verified

I don't have JMeter installed locally, so this plan has been checked for
XML well-formedness and structural consistency with the original working
file, but **not actually run**. Before relying on it for tomorrow's test,
open it once in the JMeter GUI (or a short `-n` dry run with a tiny
`-JregUsers`/`-JloginUsers`) to confirm it loads and executes as expected.

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

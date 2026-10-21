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
| `2 - Login Authentication` | Login/auth (P0 #1) + the full Core Browsing Loop (Home, Balance/History, Future Boost, Vouchers, Deals, BAM, Partner/Loyalty, Profile) + logout | `-JloginUsers` |
| `3 - Payments Order Flow` | out of scope this round, kept for later | `-JpayUsers` (default 0) |
| `4 - Mixed Journey` | Test 3's 5,000-user mixed workload | `-JmixedUsers` (mostly placeholders, see below) |

Every request now carries `X-App-Version` and `X-Platform` (both
`-J`-overridable, default `1.0.1`/`android`) alongside the existing
`Content-Type`/`Accept`, per the Oct 2026 BFF/GraphQL scope doc's header
requirements -- added at the shared Common Headers level so every sampler
gets them automatically, not per-request.

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
  -JtotalUsers=N -Jcsvfile=pool.csv -JregUsers=N -JregRampup=secs -JregLoops=1 -l reg_results.jtl

# Phase 2 -- load-test login against that now-registered pool
jmeter -n -t 202609HRv6_BoostRegistrationLoadTest.jmx \
  -Jcsvfile=pool.csv -JloginUsers=N -JloginRampup=secs -JloginLoops=cycles -l login_results.jtl
```

`-JtotalUsers` must be passed explicitly in phase 1 and must match `-JregUsers`
-- the Username Generator no longer infers a count from `regUsers`
automatically. It used to, and that was a real bug: the generator thread
group runs on *every* invocation regardless of which scenario you're
targeting that run, so phase 2 (which deliberately passes `-JregUsers=0`)
would silently regenerate the pool file with zero rows and wipe out the
very identities phase 1 had just registered. Confirmed live before the fix
(phase 2 failed with raw 400s from empty phone/ID fields) and confirmed
fixed after (phase 2 then authenticated successfully). The generator now
defaults to `count=0`/generate-nothing and leaves an existing pool file
alone unless `-JtotalUsers` is set.

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

### SA ID entropy ceiling: CONFIRMED LIVE, blocks the 5,000-identity target as-is

Tested directly against `api-ppe.booost.com` on 2026-10-21 (full flow proof,
see below) and hit this for real, unprompted: a freshly-generated identity
on the fixed DOB=2000-01-01 bypass got **409 `identity_in_use`** on
`/verify` -- *"This identity document is already registered to a different
phone number"* -- despite never having used that ID in this session.

Why: the bypass only works for that one literal DOB, which fixes `yymmdd`
in the SA ID to `000101`. Citizen/gender digits are policy-fixed too, so
the *only* free entropy is a 4-digit sequence number -- about **10,000
valid distinct IDs, total, for every team that has ever used this
convention against this PPE environment**, not 10,000 per run. Birthday-
paradox math says 5,000 draws from a ~10,000-slot space produce collisions
as the rule, not the exception.

This is a test-tooling ceiling, not a BOOOST performance finding -- if
tomorrow's progressive run shows rising 409/403 rates as user count climbs,
that's this artifact, not the app degrading under load. **Needs resolving
with the backend/MIS team before the 5,000-user registration numbers can be
trusted**: either a wider/dedicated bypass range for the test window, a
pre-allocated ID block, or retry-on-collision logic added to this script
(not built yet, flagged for a decision rather than built silently, since it
changes what the registration numbers actually mean).

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

### GraphQL gateway not reachable as specified -- CONFIRMED LIVE, blocks Scenarios 3-9

The Oct 2026 BFF/GraphQL scope doc provided the missing endpoints for Home,
Balance/History, Future Boost, Vouchers (browse only), Deals, BAM, and
Partner/Loyalty -- all served through one gateway, `POST /graphql`. All
seven are now built into `2 - Login Authentication` as real GraphQL
samplers (toggle the whole loop with `-JincludeBrowsing=false` if a run
needs bare login only), using the exact queries/variables from that doc.

Tested live and the gateway itself isn't reachable yet: `POST
https://api-ppe.booost.com/graphql` returns **404** with a plain-text body
of `"404 page not found"` -- not a GraphQL error, not JSON at all. That's
the signature of a server with no route registered at that path, not
something a correctly-formed request can work around. The scope doc itself
hedged on the host (*"Gateway / BFF Root: `https://api-ppe.booost.com` (or
your target environment gateway)"*), so this needs the real PPE gateway
host confirmed before Scenarios 3-9 can be trusted.

Each GraphQL sampler's domain is independently overridable via
`-JgraphqlHost` (defaults to `${host}`) -- confirmed working by pointing it
at a throwaway host and verifying the sampler's actual request URL changed
accordingly. Once the real gateway is known: `-JgraphqlHost=the-real-host`,
no other changes needed -- the request bodies were accepted as well-formed
JSON by whatever served the 404 (it routed and rejected on path, not on
body).

**Leading candidate host, still unconfirmed (2026-10-21)**: tried
`api-ppe.booost.com/v2/graphql`, `/bff/graphql`, `/api/graphql`,
`apic-ppe.booost.com/graphql`, `/api/graphql`, `/v1/graphql`,
`bff-ppe.booost.com/graphql`, `graphql-ppe.booost.com/graphql`, and
`auth-ppe.booost.com`. A pen-test ticket (BOOST-7553, July 2026) names
`bff-ppe.booost.com` and `auth-ppe.booost.com` as the mobile app's PPE API
domains -- but **neither resolves in public DNS**, confirmed independently
on two different machines/networks, so they're either internal/VPN-only
or stale since July. `api-ppe.booost.com`'s own `/v2`, `/bff`, and `/api`
sub-paths all gave the identical plain 404 as `/graphql`, ruling those out
too. **`apic-ppe.booost.com` does resolve and sits behind Cloudflare like
a real production gateway** -- but every path tried there, including with
a real `Bearer` token from the proven login flow, got the same generic
Cloudflare challenge/block regardless of whether the path is valid.
Cloudflare is rejecting at the edge uniformly, so no amount of path
guessing on this host can distinguish real from wrong -- deliberately not
pushed further, since that's a security control, not a routing question.

Both `-JgraphqlHost` and `-JgraphqlPath` are independently overridable
(both confirmed live) for whenever the real host+path turns up. Likely
only resolvable by: being on the corporate VPN, the `boost-mobile` app's
own PPE env config (`GRAPHQL_URL`/`BFF_URL`/`API_GATEWAY_URL` in
`src/config/`, `.env.ppe`, or `environments/ppe.ts`), the in-app
diagnostics screen (tap the environment indicator, per Build 38/40
release notes), or directly asking David Irvine / Kgolane Thulare
(BOOST-7553's authors).

**Finding the host isn't the whole fix** -- the 10 GraphQL query shapes in
these samplers (`homeDashboard`, `futureBoost`, `wallet`,
`voucherCatalogue`, `deals`, `boostAMillion`, `partners`, etc.) are
illustrative examples from the scope doc, never checked against the real
BFF schema. They'll likely fail with a GraphQL error (not a 404) even once
the host is right. Once reachable: pull the real schema via introspection
(if the gateway allows it) or capture the actual queries the PPE app sends
(proxy capture, or the query files in the `boost-mobile` iOS/Android
repos), then update these samplers' bodies to match before trusting the
results.

`4 - Mixed Journey` (Test 3's weighted 20/20/20/10/10/5/5/5/5 workload)
still has these same 7 journeys as disabled TODO placeholders, not yet
replaced with the real GraphQL calls now built into group 2 -- deferred
until the gateway host is confirmed and group 2's version is proven to
work end to end, rather than duplicating untested samplers a second time.
Weighting them by the brief's percentages once they're real: JMeter's
`ThroughputController` in "Percent Executions" mode per branch, not done
here yet.

The Profile *write* (PATCH `/v1/identity/profile`) is documented too, but
the brief says to keep profile/settings read-based for this round, so it
stays unbuilt.

### Verified live against api-ppe.booost.com (2026-10-21)

Installed JMeter 5.6.3 + JDK 17 and ran the actual plan, not just an XML
check, for one real user through each real thread group:

- **Registration (1 user)**: `Username Generator` -> `POST /v1/auth/otp` 200
  -> `POST /v1/auth/verify` 200 -> `POST /v1/identity/register` **201
  Created** -> `GET /v1/identity/status` 200. All four real HTTP samples
  succeeded, 0 errors.
- **Login (1 user, same now-registered identity)**: `POST /v1/auth/otp` 200
  -> `POST /v1/auth/verify` (hit the SA ID collision above on this
  particular identity, a real account-state conflict, not a script
  defect -- see the finding above) -> `GET /v1/identity/profile` correctly
  401'd once `/verify` didn't return a usable access_token, exactly the
  dependent-failure behaviour the custom assertion messages are meant to
  surface.
- Along the way this caught and fixed a real bug: the Username Generator
  ran unconditionally on every invocation and, when phase 2 passed
  `-JregUsers=0`, regenerated the pool file with zero rows -- silently
  wiping the identity phase 1 had just registered. Fixed by making
  generation opt-in via `-JtotalUsers` (see above); re-ran the full
  two-phase sequence afterward and confirmed phase 2 then read the correct
  pool row.

- **Login + full Core Browsing Loop (1 user, fresh identity, re-tested
  after the fix above)**: `otp` 200 -> `verify` 200 -> all 10 GraphQL
  calls (Home, Wallet Balances, Transaction History, Future Boost L1+L2,
  Voucher Catalogue+Detail, Deals, BAM, Partner Directory) **404** -- see
  the GraphQL gateway finding above, this is the real, live result, not
  a hypothetical -- `profile` 200 -> `logout` 204. Everything that isn't
  the GraphQL gateway worked correctly, including the assertion messages
  firing exactly as designed on the 404s.
- Confirmed the `-JgraphqlHost` override itself works correctly (separate
  from whether the real gateway is reachable) by pointing it at a
  throwaway host and verifying the sampler's request URL changed to match.

Not yet run at real scale (hundreds/thousands of users) or for the
Payments/Mixed Journey groups -- this was a correctness check of the flow
logic, not a dry run of tomorrow's actual load.

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

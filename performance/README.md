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
against the boost-auth-api Mobile Integration Guide, the confirmed GraphQL
gateway, and the Oct 2026 PPE performance brief (4,000-5,000 expected
users, payments out of scope for that round). One plan, **one named thread
group per test** from the brief (not one group reused across tests via
parameters) -- each is independently toggleable by its own thread-count
property (0 = that group does nothing), so running a specific test is
just setting its one property, no need to remember which properties to
zero out on a shared group:

| Thread group | Test | Threads property |
|---|---|---|
| `Baseline` | Test 1 -- Login + Profile + Logout at low N (Home/Future Boost live in Progressive Load, not duplicated here) | `-JbaselineUsers` |
| `Registration Load` | Test 5 (also P0 #2, also Test 1's registration baseline at low N) | `-JregUsers` |
| `Progressive Load` | Test 2 -- Login/auth + the full Core Browsing Loop (Home, Balance/History, Future Boost, Vouchers, Deals, BAM, Partner/Loyalty, Profile) + Logout, stepped 250-5,000 | `-JprogUsers` |
| `Mixed Journey (5000 User)` | Test 3 -- 9-branch workload, all branches every iteration (see below) | `-JmixedUsers` |
| `Login Spike` | Test 4 -- concentrated auth only (otp+verify), no Profile/Logout | `-JloginSpikeUsers` |
| `Spike Test` | Test 6 -- Login + Profile + Logout, up-then-down shape | `-JspikeUsers` |
| `Stress Test (Beyond 5000)` | Test 7 -- same content as Spike Test, pushed past 5,000 | `-JstressUsers` |
| `Soak Endurance` | Test 8 -- same 9-branch content as Mixed Journey, duration-based instead of loop-count-based | `-JsoakUsers` + `-JsoakDuration` (seconds) |
| `Payments Order Flow` | out of scope this round, kept for later | `-JpayUsers` (default 0) |

Progressive Load, Spike Test, and Stress Test share near-identical content
(same login+browsing sequence, different thread count/ramp/purpose) --
that's deliberate duplication, not drift: JMeter has no way to share logic
across thread groups that can be hand-written reliably outside the GUI (a
Test Fragment + Module Controller proof-of-concept was tried live and its
node_path reference couldn't be resolved after several attempts), so each
test gets its own real, independently-verified copy rather than one group
driven by easy-to-misremember parameter combinations.

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

Two-phase for anything that logs in (Baseline, Progressive Load, Login
Spike, Spike Test, Stress Test, Mixed Journey, Soak Endurance): a pool of
identities has to actually be registered first -- you cannot log in as
someone who was never registered.

```
# Phase 1 -- register N fresh identities, creates pool.csv
jmeter -n -t 202609HRv6_BoostRegistrationLoadTest.jmx \
  -JtotalUsers=N -Jcsvfile=pool.csv -JregUsers=N -JregRampup=secs -JregLoops=1 -l reg_results.jtl

# Phase 2 -- run whichever named test you want against that now-registered pool,
# e.g. Progressive Load:
jmeter -n -t 202609HRv6_BoostRegistrationLoadTest.jmx \
  -Jcsvfile=pool.csv -JprogUsers=N -JprogRampup=secs -JprogLoops=cycles -l prog_results.jtl
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

- **Test 1 (baseline)**: `-JbaselineUsers=10` (phase 2), plus `-JregUsers=10`
  on its own phase-1-only run for the registration baseline.
- **Test 2 (progressive)**: `-JprogUsers` stepped
  250/500/1000/2000/3000/4000/5000 against the *same* pool (`CSVDataSet`
  recycles rows).
- **Test 3 (5,000-user mixed journey)**: `-JmixedUsers=5000` -- all 9 of 9
  branches are real and confirmed (see below); not yet weighted by the
  brief's percentages, see the GraphQL section.
- **Test 4 (login spike)**: `-JloginSpikeUsers` stepped 500/1000/2000, short
  `-JloginSpikeRampup` (concentrated).
- **Test 5 (registration load)**: `-JregUsers` stepped 100/250/500/1000,
  fresh pool each step.
- **Test 6 (spike)**: `-JspikeUsers` through the shape
  500 -> 1000 -> 4000 -> 1000 as separate invocations, watching recovery on
  the final low-load step.
- **Test 7 (stress beyond 5,000)**: `-JstressUsers` stepped
  4000/5000/6000/7000+.
- **Test 8 (soak)**: `-JsoakUsers=N -JsoakDuration=seconds` -- duration-based
  (confirmed live: a 15s run produced multiple looped iterations within the
  window, not a single pass), not loop-count-based like the others.

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

### GraphQL gateway: FOUND AND CONFIRMED LIVE (2026-10-21)

The journey was: `api-ppe.booost.com/graphql` (plain 404, no route at all)
-> `apic-ppe.booost.com` (real host, but every path uniformly Cloudflare-
blocked, a security control, deliberately not pushed past) -> the real
answer, handed over directly: **host `app-ppe.booost.com`, path `/v2/`**.
Confirmed independently with a fresh `access_token` from the proven login
flow: `POST https://app-ppe.booost.com/v2/` with a `DashboardPage` query
returned 200 with real PPE data (real voucher/deal/history rows).
`-JgraphqlHost`/`-JgraphqlPath` now default to these confirmed values
(still overridable if the gateway ever moves).

**All 10 scenarios are now real queries, confirmed live through this exact
JMX file -- not ad-hoc requests.** Found by running a GraphQL introspection
query (`query { __schema { queryType { fields { name } } } }`) against the
confirmed gateway -- allowed, returned the entire query schema in one call,
which is how the remaining 7 were found so quickly rather than guessing
field names one at a time:

| Scenario | Real query | Notes |
|---|---|---|
| Login/auth | `/v1/auth/otp` + `/v1/auth/verify` | |
| Home | `DashboardPage` | header, badges, tapTapBoosts, vouchers, deals, history, legal |
| Future Boost | `FutureBoostPage` + `FutureBoostDetailPage(offeringId)` | load + **open detail**, `offeringId` extracted dynamically from the first response via `JSONPostProcessor`, not hardcoded |
| Balance/History | `BalancePage(currency: "ZAR")` | one call covers both load and transaction history; takes a required `currency` arg |
| Vouchers | `BoostBuyPage` + `VouchersPage` + `VoucherOffering(id)` | landing, then real catalogue, then **open voucher details** -- a 3-step chain, replacing the single guessed query this used to be; `id` extracted dynamically |
| Deals | `DealsPage` | "open detail" (`deal(id)`) exists per introspection but every deals list returned empty during testing, so there was no real ID to verify it against -- left unwired rather than guessing |
| BAM | `BoostAMillionPage` | promotion, stories, currentDrawPeriod with prompts/groups/entryMethods, completedDrawPeriods, howItWorks, legal |
| Partner/Loyalty | `PartnerList` + `PartnerPage(partnerId)` | list + **open partner**, `partnerId` extracted dynamically |
| Profile/settings | `GET /v1/identity/profile` | read-only, matches the brief's own instruction |

All three detail-page queries (`FutureBoostDetailPage`, `VoucherOffering`,
`PartnerPage`) take a real ID chained dynamically from the preceding list
call's response, not a hardcoded placeholder -- this is what actually
proves the "open detail"/"open partner" steps the brief's journeys ask
for, not just the landing load.

`Mixed Journey (5000 User)` and `Soak Endurance` both now have **all 9
branches real and confirmed**, each grouped under its own named
`Transaction Controller` for per-branch latency reporting. The earlier
percentage-weighted `ThroughputController` ("Percent Executions" mode,
20/20/20/10/10/5/5/5/5 one-branch-per-iteration selection) was removed at
request -- every branch now runs on **every** loop iteration (a full sweep
of all 9, not a weighted pick of one), reported as 9 separate named
transactions per iteration.

The Profile *write* (PATCH `/v1/identity/profile`) is documented too, but
the brief says to keep profile/settings read-based for this round, so it
stays unbuilt.

### Verified live (2026-10-21)

Installed JMeter 5.6.3 + JDK 17 and ran the actual plan, not just an XML
check:

- **Registration (1 user)**: `Username Generator` -> `otp` 200 -> `verify`
  200 -> `register` **201 Created** -> `status` 200. 0 errors.
- **Progressive Load (1 user, full journey)**: `otp` 200 -> `verify` 200 ->
  `Home` 200 -> `Balance/History` 200 -> `Future Boost` 200 -> `Future
  Boost detail` 200 -> `Vouchers (landing)` 200 -> `Vouchers (catalogue)`
  200 -> `Voucher detail` 200 -> `Deals` 200 -> `BAM` 200 -> `Partner list`
  200 -> `Partner detail` 200 -> `profile` 200 -> `logout` 204. Every one
  of the 10 scenarios, in one real run, 0 errors.
- **Mixed Journey (1 user)**: all 9 of 9 branches in one run -- Login,
  Home, Future Boost, Balance/History, Deals, Voucher Browsing, BAM,
  Partner/Loyalty, Profile -- all 200, 0 errors.
- **Mixed Journey, Transaction Controller only (1 user, 3 iterations)**:
  after removing the `ThroughputController` weighting, confirmed all 9
  branches now fire on every iteration -- 3/3 hits each across all 9 named
  transactions, 0 errors.
- **Soak Endurance (1 user, 15s duration)**: confirmed the scheduler
  mechanism itself works, not just the content -- 17 samples recorded
  across ~18s of actual run time (several looped iterations within the
  window), not a single pass sitting idle for the rest of the duration.
- Along the way this caught and fixed a real bug: the Username Generator
  ran unconditionally on every invocation and, when a later run passed
  `-JregUsers=0`, regenerated the pool file with zero rows -- silently
  wiping an identity a prior run had just registered. Fixed by making
  generation opt-in via `-JtotalUsers` (see above); re-ran the full
  two-phase sequence afterward and confirmed it then read the correct
  pool row.
- Confirmed the `-JgraphqlHost`/`-JgraphqlPath` overrides work correctly
  (separate from whether a given gateway is reachable) by pointing them at
  a throwaway host and verifying the sampler's request URL changed to
  match.

Not yet run at real scale (hundreds/thousands of users), and Payments
remains untouched (deliberately out of scope this round) -- this was a
correctness check of the flow logic and the newly confirmed gateway/
queries, not a dry run of tomorrow's actual load.

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

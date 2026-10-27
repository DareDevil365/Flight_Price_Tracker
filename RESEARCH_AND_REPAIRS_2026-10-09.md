# Research and repairs — 9 October 2026

Three research agents examined coupon systems, browser navigation and forecast reliability. Useful findings were implemented and tested. No paid dependency/service was added. The application still cannot promise every website's cheapest final payment price.

## Implemented changes

| Problem | Repair | Evidence boundary |
|---|---|---|
| Background discovery visited only GrabOn | Added bounded independent EMT public flight/bank advertisement feeds; merchant duplicates take priority | Summary-only terms stay conditional; current native checkout terms take priority over database advertisements |
| Trials could remove an existing cheaper coupon and finish at a higher price | Fail the run and attempt restoration of original code/total | Login/cart changes can prevent restoration; failure remains visible |
| Optional cashback could restrict a universal base coupon or become its advertised amount | Separate additional cashback only when an independent immediate discount remains; preserve raw terms and genuine restrictions | Cashback-only offers stay restricted; conflicting domestic-only/international-only terms become unknown |
| A failed recheck left an old checkout marked verified | Withdraw verification before rechecking; retain a historical receipt; fall back to the old uncorroborated listing or quarantine if no listing exists | Human cart changes are not continuously monitored; users must reverify |
| Trial state/history was difficult to follow | Per-session progress and duplicate-click protection; automatic ledger refresh; explicit connection-loss status | Backend cart locks remain authoritative |
| Large offer lists buried controls/history | Move provider selector above expandable, uncapped candidate list | Discovery is not exhaustive |
| Workers accumulated unused API bodies | Removed response-body decoding/retention from MMT, Cleartrip and EMT; CT retains only five successful exact request-criteria fields | DOM layouts and provider access can still fail |
| Fresh quotes could reactivate outdated model validation | Restart forecast-only cohorts after collection gaps over seven days; withhold outcomes older than fourteen days | Conservative product policies, not learned scientific thresholds |
| Companion could not read the observed Cleartrip review | Added bounded semantic review reader and partial-evidence wording | Read-only prototype, no installed extension/backend bridge/payment proof |

Playwright, local SQLite and deterministic price checks were retained. A new automation library cannot supply denied provider access or missing longitudinal fare observations. No LLM is trusted to establish money, coupon eligibility or measured certainty.

## Primary research and alternatives

- [Honey's official coupon-success explanation](https://help.joinhoney.com/article/364-coupon-success-rates) says store-level frequency does not establish eligibility for a particular checkout. We retained booking-scoped trials and strengthened original-cart preservation; Honey's proprietary internals were not accessed/copied.
- [OpenCoupon](https://github.com/EvgeniiKlepilin/open-coupon), MIT licensed, illustrates merchant selectors, sequential trials and winner application. Its inspected generic money/success matching was weaker than the flight/cart safeguards here. No dependency or source code was imported wholesale.
- [EMT's public deals page](https://www.easemytrip.com/deals.html) links normal public [flight](https://www.easemytrip.com/offers/offerjson/deals/flightoffers.json) and [bank](https://www.easemytrip.com/offers/offerjson/deals/bankoffers.json) advertisement resources. These expanded discovery without replaying private payment APIs. Partial source failures remain visible and retry after fifteen minutes. Explicit first refresh also now works on a fresh database.
- [Microsoft's Playwright extension](https://github.com/microsoft/playwright/blob/main/packages/extension/README.md) supports selecting an existing tab. [Chrome activeTab](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab) provides temporary access after a user gesture; [Playwright warns against automating the default personal profile](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context). No extension was installed or approval bypass enabled.
- [Stagehand](https://github.com/browserbase/stagehand), [Browser-use](https://github.com/browser-use/browser-use) and [Page Agent](https://github.com/alibaba/page-agent) offer useful DOM/observation/action patterns. None was demonstrated to fix these booking denials. No paid cloud/proxy or model-driven replacement was adopted.
- [Forecasting: Principles and Practice](https://otexts.com/fpp3/tscv.html), [StatsForecast cross-validation](https://nixtlaverse.nixtla.io/statsforecast/docs/tutorials/crossvalidation.html) and [River ADWIN](https://riverml.xyz/dev/api/drift/ADWIN/) informed chronological evaluation and stale-evidence safeguards. They do not supply exact-trip fare histories. Seven/fourteen-day policies are our conservative choices; nonoverlapping outcomes can remain correlated. [Detailed forecast research](FORECAST_RESEARCH_2026-10-09.md).

## Browser benchmark and the useful new result

BLR–LKO, 23 November 2026: current factory gave an empty MMT page; plain isolated Chromium gave an access/verification page. CT listings worked in both. Progressive rendering changed card counts, so counts/latency do not establish superiority.

BLR–LKO, 23 February 2027: both fresh browsers selected QP1521, 12:25–15:05, INR 6,785, then failed continuation. Itinerary creation and interstitial requests returned HTTP 403. Neither reached payment. A library/fingerprint replacement was therefore not adopted as a proven fix.

The ordinary Codex in-app browser then reached CT's actual review page for that same flight. It showed BLR Terminal 1, LKO Terminal 3, one adult, base INR 4,624 plus taxes INR 2,161. A **manual native CTBBD application succeeded**, changing **INR 6,785 → 6,344**, saving INR 441. The [linked official offer page](https://www.cleartrip.com/all-offers/ct-bbd-special-offer-international/) advertised all payment modes/open travel dates, but contained conflicting domestic/international wording and explicitly said convenience fees/additional services are extra. Optional card cashback was not subtracted.

This proves ordinary-browser **review access**, not unattended app recovery/payment access. Its ledger record is review_only, cabin UNKNOWN, payment unconfirmed, other codes untested and final eligibility unresolved. No fare-learning record was created.

The companion review logic was checked read-only on actual public elements: 387 descendants, separate time/airport H2 siblings, full displayed year, one adult, INR 6,344 and four coupon tags. The initial 300-element bound withheld identity; the corrected review-only bound accepts 500 and rejects 501 in fixtures. Generic payment bounds remain unchanged. No raw page dump was saved. The extension itself was not installed/tested end to end. Same-tab application still needs explicit invocation, serial trials, stable cart checks, restoration and a separate manual-evidence channel; this is a proposal, not implemented integration. [Companion instructions](browser-companion/README.md).

## Fresh integrated checks

One adult/economy/exact airports and dates. Amounts can change.

| Search | Runtime | Google / EMT / CT / MMT rows | Corroborated / uncorroborated / flagged | Lowest corroborated listing |
|---|---:|---|---|---|
| AMD → IXC, 17 November 2026 | 19.47 s | 4 / 12 / 11 / 0 | 4 / 23 / 0 | CT INR 6,719, IndiGo 20:35 |
| IXC → AMD, 17 February 2027 | 12.62 s | 4 / 12 / 11 / 0 | 2 / 25 / 0 | CT INR 7,602, IndiGo 17:25 |

MMT's empty-page failure remained visible. Uncorroborated rows were not promoted to training. Runtimes are samples, inventory is partial.

Fresh automated EMT review trial: AMD–IXC, 17 November, 6E6506, 20:35–22:20, INR 6,719. It combined 96 native/database candidates before deduplication/filtering and tested **all four eligible collected codes**. BOOKNOW reached **INR 6,499**; EMTQORUM INR 6,569; FREECAB/DELIGHT gave no immediate reduction. BOOKNOW was reapplied and the total rechecked. Conditional/excluded codes were recorded without assumed savings. One RAM-only monetary crop was cleared after inspection. Payment/final fees remain unverified.

Public refresh returned **66 unique EMT candidates**: flight35/bank28/GrabOn9 before overlap removal. Summary-only terms stay conditional; expired/incompatible offers are filtered downstream. The ledger retains **six runs and 223 trial facts**, including earlier failures.

The refreshed accepted-data export has **132 fares**, 177 offer-evidence rows, 355 dated offer snapshots and 79 provider runs. Each exact trip cohort still lacks sufficient longitudinal history. Existing primary context was checked: IOCL's actual ATF table remains dated April 2026, IndiGo's current FY table through July. Footer/import dates do not make them current. No historical fares/future discounts were invented.

## Final validation and remaining limits

**446 backend tests passed** in a disposable project copy, with one warning from an inactive legacy XGBoost pickle. Frontend production build/ESLint and forecast skill validation passed. Tests cover original-cart preservation, cashback/card conditions, conflicting scope, stale verification, duplicate/cancelled requests, timezone-aware expiry, response privacy, forecast gaps, and review parsing/privacy/boundaries. Local fixtures are never production observations.

The runtime was restarted. Real offer refresh, two fresh complete searches, automated EMT review trials, manual CT trial, ledger retrieval and visible review-only labels were checked. Accepted export remains separate from legacy model files. No purchases, real passenger/card entry, paid APIs, challenge bypass or production mock seeding occurred.

MMT app access remains unreliable; CT app continuation still fails despite ordinary-browser review success. Final merchant-payment/convenience-fee coverage and later gateway/issuer charges remain unproven. Coupon discovery cannot be exhaustive. Future-fare percentages remain unavailable until real collection/calibration requirements pass. These limits are shown rather than replaced with guesses.

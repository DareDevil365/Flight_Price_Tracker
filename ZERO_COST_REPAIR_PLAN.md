# Zero-cost research and repair plan

Research date: 8 October 2026.

**Status: partially implemented.** This document records the original planning review and proposed scope. The follow-up implementation and fresh tests are in [REPAIR_VALIDATION_2026-10-08.md](REPAIR_VALIDATION_2026-10-08.md); the earlier baseline is in [VALIDATION_REPORT.md](VALIDATION_REPORT.md). Comparable price snapshots, tighter corroboration, three-valued offer checks, provider diagnostics, journey constraints and durable monitor leases/deduplication are implemented. Universal payment-scenario coverage, new validated provider adapters, broader source-specific offer parsers and pooled forecast models remain proposals. Website documentation is evidence about capabilities and terms, not proof that an adapter works.

## Goal and budget

Find the lowest evidenced price for the user's requirements among the sources successfully checked, including usable coupons and checkout charges. Suggest cheaper compromises and monitor future trips without inventing fares, eligibility, historical trends or certainty.

Use the existing computer, Python, Playwright, React and local SQLite. No paid API, proxy, hosted database, subscription, card-required trial or automatic paid fallback. Existing internet/electricity are still needed; a local service does not run when its computer is powered off. Gemini must remain optional and outside price extraction, eligibility decisions, ranking and prediction.

The product should say which sources were checked, which failed, what remains conditional, when the evidence was observed and whether a price is a listing or a verified payment total. It cannot honestly guarantee the cheapest price across every travel website.

## What the current evidence establishes

The existing report records 86 passing backend tests, frontend build/lint success, fresh searches about one and four months ahead and three EaseMyTrip review-stage coupon trials. These results are useful but do not establish successful final-payment coupon application across all providers. MakeMyTrip returned no usable listings in those runs; Cleartrip booking continuation reached a provider failure page. Their underlying causes still need diagnosis.

The live brain has many individual observations but only one distinct observation day in the recorded validation. Repeated searches in one day cannot establish future-price accuracy. The current model correctly withholds calibrated predictions, but its exact-departure-date series makes learning too slow for many trips.

Additional issues found in this code review:

| Location | Finding | Consequence |
|---|---|---|
| financial_filter.py | Eligibility relies heavily on description regexes and boolean pass/fail. | Excluded payment methods can be confused with required methods; weekday, usage and account conditions can remain unresolved. |
| alternative_planner.py | The original comparator falls back from listed fares to checkout totals, while alternatives may remain listed fares. | A displayed saving can compare different price bases. |
| alternative_planner.py | Child searches inherit departure-time and maximum-stop preferences for each leg. | A second leg can be unnecessarily excluded by a journey-start preference; whole-journey stop limits need separate enforcement. |
| quote_integrity.py | A matching flight number is not required when one side lacks it, and price corroboration uses broad ratio bands. Fare-family/baggage equivalence is absent. | Two seemingly similar offers can receive more corroboration than the evidence warrants. |
| intelligence.py | A current checkout total can be compared with a forecast trained on listing prices. | Coupon/payment fees can be mistaken for market movement. |
| intelligence.py | A published future offer can support a waiting signal before its payable benefit and complete eligibility are established. | An announced sale need not save this user money. |
| intelligence.py / collection | Daily minima can change when provider coverage changes. | Losing a cheap provider can resemble a fare increase even if the market did not move. |

These are code-level findings and risks; they are not claims that every affected live result was wrong.

## Implementation order

| Order | Work | Deliverable and release gate |
|---|---|---|
| 1 | Comparable quote contract and strict integrity checks | No claimed saving across mismatched price bases, passengers, baggage or journey constraints; ambiguous identity cannot become strong corroboration. |
| 2 | Coupon rules and payment-scenario comparison | The winning scenario has the lowest observed payable amount, with complete conditions and trial coverage shown. |
| 3 | Provider diagnostics and recovery | MakeMyTrip/Cleartrip failures have classified evidence; supported flows either work or return explicit partial results. |
| 4 | Alternative journeys and broader coverage | Whole-journey constraints hold; fees, baggage, airport changes and unknown transfer costs remain visible. Add websites individually after validation. |
| 5 | Red Room reliability and real dataset collection | Restart/resume recovery, bounded jobs, fresh-evidence alerts and a reproducible point-in-time dataset. |
| 6 | Forecast comparison and calibration | A model earns release against chronological baselines and decision outcomes; insufficient evidence continues to produce no percentage. |

Start dataset collection alongside the first repairs because history takes elapsed time. Useful search, savings and budget alerts do not need to wait for a predictive model.

## 1. Quote contract and independent checker

Extend the existing normalized quote rather than build a second pricing system. Record directed airports, full dated segments, marketing/operating flight identifiers when available, passenger types/counts, cabin, fare family, baggage, currency, total-versus-per-person basis, source, collection time and any provider expiry.

Keep different concepts separate:

- Listing total: the provider's displayed fare for the requested party.
- Payment total: the currently observed amount payable for a selected cart/payment scenario.
- Deferred reward: cashback, points or vouchers received later; never subtract from today's payment.
- Journey cost: comparable airfare plus known required baggage/transfer costs. Unknown costs prevent a guaranteed net-saving claim.

Use explicit evidence states: listed, independently corroborated, payment verified, conditional, unavailable and quarantined. A missing field stays unknown. Missing flight numbers or fare conditions lower comparability rather than silently matching.

Two paths to Google Flights remain one source. Even different websites can share upstream inventory, so agreement is supporting evidence, not absolute truth. Replace broad universal price-ratio acceptance with comparable-fare checks and targeted rechecks; a low price alone is not an error. Conflicting observations stay quarantined from training.

Bind coupon trials, rankings and notifications to a quote/cart version. Any itinerary, fare, party, add-on, payment or session change invalidates the old verification. Recheck before presenting a purchase candidate; an observed price is not a price lock.

## 2. Coupon discovery, rules and final-price comparison

Create a small proposed offer_rules.py module with **eligible / ineligible / unknown** outcomes and source-linked reasons. Represent AND/OR/NOT conditions explicitly: booking date and weekday, travel dates, minimum eligible spend, carrier/route, passenger count, bank, product/network, payment method, app/site channel, account eligibility, redemption limits and stacking.

Parse supported first-party templates deterministically. Unsupported clauses remain unknown. An optional language model can propose structured fields, but validators must require matching source evidence before those fields affect results. Do not infer card ownership or account redemption history.

Research illustrates why this is necessary. An official ICICI/EaseMyTrip offer required net banking on Thursdays, excluded cards and UPI, and ended on 31 March 2026. A currently reachable official page can therefore be expired and contain payment names only as exclusions. **This is a historical parser example, not a current recommended coupon.** [ICICI terms](https://www.icici.bank.in/offers/easymytrip-domestic-flight-offer).

Discover candidates from the selected merchant's own offer panels/pages and official bank offer pages first. Retain merchant-scoped GrabOn as a secondary discovery source. Inspect CouponDunia and other directories individually; add an adapter only if current merchant attribution, dates and reproducible checkout outcomes justify it. No directory is automatically a source of working coupons.

Keep offer versions and booking-validity dates separate from collection dates. Expired promotions enter a historical archive, not the live coupon pool. A new crawl does not renew an old offer. Record native-only/app-only/account-only offers as such.

Create a proposed payment_scenarios.py coordinator around the existing coupon applier. Compare the no-code baseline, fee-waiver option and each eligible discount under the same itinerary, add-ons and payment method. Test stacking only where explicitly supported. Observe all taxes/fees, restore the baseline, reapply the winner and verify the stable payable amount again.

EaseMyTrip's own terms say using another discount code makes convenience fees applicable, whereas a relevant code/voucher can waive them. This makes payment-scenario comparison essential: ranking by headline discount can choose the wrong winner. [EaseMyTrip agreement, section 6](https://www.easemytrip.com/pdf/free-full-refund-tnc.pdf).

An application result needs distinct states: accepted with verified payable saving, accepted without payable saving, rejected, eligibility unknown, interrupted and not tested. A changed cart baseline invalidates the earlier trials; do not attribute a simultaneous fare change to a coupon.

Maintain the requested interaction: show conditional deals, then allow “I don't have HDFC” or “UPI only” in the results text box and rerank across providers. Do not restore upfront card questioning. Ask only for a missing fact necessary to verify a chosen deal; never collect card numbers or automate a purchase.

Reduce wasted trials by deduplicating codes, caching known rules, prioritizing native offers and using a hard request/time budget. A previous success is a prioritization hint, not proof for another cart. Show tested/eligible/unknown/not-tested coverage, with a resumable next batch rather than an exhaustive claim.

## 3. Fix provider access through evidence

Retain Playwright as the browser engine. Add proposed provider_health.py records with recent successful checks, failure stage, reason and bounded backoff. Distinguish confirmed no inventory from blocked access, incomplete loading, failed criteria, parser drift, expired fare and checkout server failure.

For MakeMyTrip, inspect whether the exact-request response contains usable itinerary data before rewriting selectors. For Cleartrip, trace the transition from a fresh listing to the failure page and distinguish an expired offer from server, form or session errors. Try one controlled refresh for a recoverable failure; stop repeating an identical failed action.

Playwright already exposes browser request/response events and diagnostic traces. Use responses generated by the actual public search session when their criteria and displayed results can be checked. Save limited diagnostic evidence; avoid retaining passenger/payment contents or cookies. [Network documentation](https://playwright.dev/python/docs/network), [trace viewer](https://playwright.dev/python/docs/trace-viewer).

If a normal user session works while automated access fails, prototype an optional locally installed browser companion. A user clicks it on an allowed provider page; it reads only flight/cart facts through a provider-specific adapter. Pair it with the local app, validate sender/request identity and exclude arbitrary page instructions and personal/payment fields. This is a proposed assisted mode, not an unattended CAPTCHA bypass. Chrome's activeTab permission supports temporary access after a user gesture. [Chrome documentation](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab).

### Repository decisions

| Candidate | Decision |
|---|---|
| Fli | Retain the already integrated, pinned public Google reader only where validated. Its current upstream documentation describes limited returned results, unsupported baggage filters, unavailable booking-options retrieval and gated multi-city access. It cannot replace checkout or establish exhaustive Google coverage. [Upstream README](https://github.com/punitarani/fli/blob/main/README.md). |
| Scrapling | Benchmark adaptive element-location ideas on captured public layout changes. A recovered selector must still pass exact quote checks. Do not accept a similar-looking price automatically or replace the browser stack on anti-blocking claims. No new benchmark/adoption was performed in this planning pass. [Repository](https://github.com/D4Vinci/Scrapling). |
| StatsForecast | Borrow rolling-origin evaluation; adopt individual local models only if they beat simple baselines on this dataset. A large forecasting framework is optional. [Cross-validation guide](https://nixtlaverse.nixtla.io/statsforecast/docs/tutorials/crossvalidation.html). |
| scikit-learn | Use existing/local statistical tools for calibration and modest models when there is enough data. More model complexity does not replace valid history. [Calibration guide](https://scikit-learn.org/stable/modules/calibration.html). |

Benchmark any replacement against the retained implementation on the same supported request matrix: identity errors, usable coverage, completion/failure rate, latency, memory and maintenance/dependencies. Adopt only the useful component if the whole tool regresses another requirement. Pin revisions and keep rollback paths; no finite benchmark proves a tool will never fail.

Paid aggregators are outside the budget. Amadeus's official self-service developer guide is now marked deprecated and its repository was archived on 17 July 2026. Old free-quota tutorials are not evidence of a currently available integration; exclude it from this design. Skyscanner's commercial access criteria also make it an unsuitable mandatory dependency for this personal app. [Amadeus deprecation notice](https://github.com/amadeus4dev/developer-guides), [Skyscanner eligibility](https://www.partners.skyscanner.net/contact/travel-api).

SerpAPI currently advertises a 250-search monthly free plan, but that is too limited to make it the foundation of broad monitoring. It is excluded from the required design; any future optional experiment must verify current signup/billing conditions and stop at the free quota. No signup was performed. [Published plans](https://serpapi.com/pricing).

## 4. Alternatives that respect the user's actual journey

Repair the comparator bug first. Compare listing with listing, or verified complete scenario with verified complete scenario. Preserve the original listing when checkout verification is added. An unverified alternative can be a lead, not a guaranteed final saving.

Extend the existing planner as a bounded itinerary graph rather than brute-force every airport/date combination:

1. Search the requested trip and flexible dates the user allows.
2. Compare protected connections and airport alternatives.
3. Explore a small set of plausible self-transfer hubs only when permitted.
4. Validate whole-journey stops, initial departure preference, arrival deadline, elapsed time, overnight dates and baggage requirements.
5. Recheck the best candidates and compare complete costs where available.

Apply the user's journey-start time window to the first leg; derive feasible second-leg times from arrival and transfer constraints. Count all segments when enforcing maximum stops. Never silently relax constraints: name the proposed change and its evidenced benefit.

Keep conservative self-transfer buffers, but do not describe a fixed four/five-hour buffer as a guarantee. Same airport and same terminal need explicit current evidence. Reclaim/recheck baggage, check-in deadlines and separate-ticket disruption risk affect feasibility. IndiGo distinguishes genuine sold connections from self-created connections, including separately booked flights. [IndiGo connection/baggage policy](https://www.goindigo.in/baggage/baggage-transfer.html).

For GOI/GOX, use the user's actual destination and an explicit sourced or user-entered incremental ground cost. Airport-to-airport distance alone does not establish their cab fare. Unknown road cost stays unknown. Combined return carts, baggage-inclusive pricing and international/transit rules need their own adapters and release gates before expanding supported scope.

## 5. Real data and a trustworthy suggestion brain

Create a proposed fare_dataset.py layer over SQLite. Collect a small, bounded panel of directed routes and actual departure dates at roughly 7/30/60/120/180-day lead times, alongside saved user trips. Track the same departure cohorts as time passes. One daily run plus extra runs for actionable changes is more useful initially than thousands of same-day duplicates.

Record as-of time, lead time, flight/fare identity, eligibility/evidence quality, provider coverage, unavailable inventory and search failures. Missing/blocked results are missing data, not zero fares or evidence of demand. Keep native listing history separate from checkout/payment history. Standardize provider panels or account for coverage changes before declaring a fare trend.

Use layered advice:

- Immediately: target-budget alerts, observed price drops, exact-date alternatives, verified coupon savings and factual departure deadlines.
- Once supported: route/lead-time patterns learned across comparable departure cohorts. Keep route direction explicit. Learning a statistical pattern across departures does not copy BOM–HYD prices into HYD–BOM or reuse another trip's facts.
- Only after validation: probabilistic seven-day fare direction or waiting benefit. Show “not calibrated” for unsupported routes/regimes.

The current exact-date model is conservative but needs months of observations for each individual departure. A pooled model within directed routes, with explicit lead time and cohort validation, can use data more efficiently. Broader shared priors may be evaluated separately, but must never masquerade as route-specific history. Start with persistence, rolling median and simple regularized models before adding complex ML.

Evaluate chronologically with outcome-window gaps and held-out departure cohorts. Prevent repeated scrapes, shared itineraries and future news revisions from leaking into evaluation. Compare price error, interval coverage, alert precision and realized waiting regret, including lost inventory. Evaluate several decision dates; remove outcomes extending past departure and track unavailable flights separately.

Separate three statements in the UI: quote evidence quality, historical forecast performance and the specific booking recommendation. A percentage must have a defined event/horizon, sample size, interval and evaluation period. Historical directional accuracy is not automatically the probability that this trip rises or that a headline causes an increase. Calibration needs separate chronological evaluation. [scikit-learn calibration](https://scikit-learn.org/stable/modules/calibration.html).

Do not use a larger language model to manufacture these probabilities. News can supply dated risk context; an announced future offer is a conditional opportunity. Neither should independently trigger a confident “wait a month” decision without supported eligibility, savings and inventory-risk evidence.

### Free evidence sources to investigate/retain

| Evidence | Source and treatment |
|---|---|
| Indian jet fuel | IndianOil publishes ATF tables/history, a closer cost-context source than crude. During this review its visible price table was dated 1 April 2026 despite an October footer. Parse the table's effective date, units and city; treat stale data as stale. [Table](https://iocl.com/aviation-fuel), [history](https://iocl.com/atf-domestic-airlines). |
| Brent and USD/INR | Retain existing dated public feeds as cost context. Neither provides an Indian airline's actual fuel cost or a route-level fare forecast. |
| Airport traffic | AAI publishes monthly traffic reports. These are lagged airport-level demand proxies, not live seat inventory or exact route load factors. Access and report parsing need validation before ingestion. [AAI reports](https://www.aai.aero/en/business-opportunities/aai-traffic-news). |
| Offers and sale history | Merchant/bank pages with explicit booking/travel dates and terms. Archived sales can support future research; a previous birthday sale is not an announced future coupon. |
| Disruption/news | Retain dated primary aviation/energy announcements and clearly labelled reported headlines. Deduplicate syndicated stories and link evidence; do not count copies as independent events. |
| Holidays, schedules, competition | Add sourced regional holidays and observed schedule changes with effective dates. Treat them as candidate features, not automatic price-hike rules. |

Store publication time, effective time, retrieval time and revisions separately. Source-specific freshness rules matter: monthly reports are not daily market feeds. Drop a candidate feature if chronological tests show no benefit.

I did not establish a trustworthy, free, comprehensive multi-year Indian booking-price snapshot dataset in this research. US ticket surveys and undated “flight price” CSVs are not substitutes for Indian advance-booking histories. Own dated collection is the reliable path.

Keep SQLite plus FTS5 for structured facts and source retrieval. Graph RAG or a hosted vector database adds no necessary capability for arithmetic, date eligibility and route isolation. Consider a local columnar archive only if measured data volume warrants it.

## 6. Red Room and operational efficiency

Extend the existing monitor with durable due jobs, a single-run lease, retry backoff and a saved alert outbox. Recover due watches after restart/resume; avoid starting a burst of browsers for every missed interval. Show last attempt, last successful exact-trip search, provider coverage and stale status separately.

Deduplicate equivalent searches across watches, retain bounded browser concurrency and prioritize trips near departure or target prices. Refresh public offers independently of user-assisted checkout. Never claim that background coupon discovery has applied a code to a future user's payment session.

Before an actionable alert, refresh the quote or explicitly label its timestamp and evidence level. Deduplicate repeated unchanged alerts while still surfacing meaningful failures. A notification-delivery failure must not erase the saved alert.

Add missed-run recovery first. Optional Windows wake timers can be evaluated for supported sleep states; they do not make a powered-off computer run. Actual wake scheduling requires due-time triggers as well as settings. [Microsoft task settings](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasksettingsset?view=windowsserver2025-ps).

Default to local saved/desktop notifications. Optional ntfy has a free public service, but public topics should not carry sensitive itinerary or payment information; it is not required. [ntfy FAQ](https://docs.ntfy.sh/faq/), [publishing guidance](https://docs.ntfy.sh/publish/).

As a separate backup, the user can enable Google Flights price tracking, which can email price changes without this PC running. It does not execute our coupon checks or our prediction logic. [Google tracking instructions](https://support.google.com/travel/answer/6235879?hl=en).

## Acceptance and regression plan

All test artifacts must use disposable databases/settings. Fabricated adversarial fixtures are acceptable inside isolated tests; they must never become product fares, offers, news, alerts or training observations.

**Public search matrix:** start with six new directed routes, each at approximately 7/30/60/120/180 days from the execution date. Include reverse directions, one/two adults, economy/business, nonstop, departure windows, connecting itineraries and sold-out/blocked cases across the supported sources. Use two staggered passes to expose repricing and intermittency. Reconcile accepted observations against the contemporaneous provider page rather than old report prices.

**Checkout matrix:** on every claimed supported provider, cover baseline, native coupon, bank-specific coupon, fee waiver, invalid/expired code, unsupported payment, unknown account eligibility and cart repricing. Use legitimate user-assisted details only. Stop before payment. Review-stage acceptance alone does not pass a final-payable gate. Inaccessible flows remain explicitly unsupported.

**Alternatives:** cover original-checkout versus alternative-listing mismatch, second-leg departure window, total stop count, overnight arrival, same/different/unknown terminal, two booking fees, checked baggage, missing cab costs and an airport change whose ground cost erases the airfare saving.

**Integrity/learning:** inject wrong direction/date/party/currency, per-person ambiguity, missing identity, fare-family mismatch, source duplication, stale prices, provider dropout and suspicious disagreement. Assert that none enters accepted training history. Validate quarantine review and rechecks.

**Forecast:** use only genuine accepted history for reported model performance. Chronological baselines, non-overlapping outcomes, cohort holdouts, drift checks and calibration must pass before enabling numeric probability. A short coding/test session cannot prove months or years of predictive accuracy.

**Operations:** interrupt network/backend/browser during a run, restart mid-job, resume after a missed interval, expire a session and interrupt notification delivery. Verify no duplicate concurrent run, no duplicate unchanged alert, bounded resources and retained failure evidence.

Release gates are zero known false-valid outputs in the tested matrix, explicit incomplete coverage, reliable state recovery and documented supported scope. Passing a finite matrix reduces risk; it does not establish that external websites never break.

## What stays unavailable under this budget

No guaranteed access through every provider's restrictions, guaranteed global cheapest final fare, unrestricted checking of every coupon, future unannounced offer knowledge, instant multi-year Indian fare history or local monitoring while powered off.

The achievable result is useful: real comparable fares, systematically verified savings where checkout is accessible, transparent failures, cheaper permitted alternatives, durable alerts and predictions that are withheld until supported. Custom code should concentrate on these correctness and recovery gaps, using open-source components only where measured benefits justify them.

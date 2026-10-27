# Follow-up repairs and validation — 8 October 2026

This reports implemented changes following [ZERO_COST_REPAIR_PLAN.md](ZERO_COST_REPAIR_PLAN.md). It supplements the earlier [baseline report](VALIDATION_REPORT.md). The app has usable partial listing searches and stricter verification boundaries. It does **not** have proven end-to-end final-payment coverage across all providers, or a calibrated real future-fare forecast.

## What changed and why

| Earlier problem | Implemented replacement | Practical effect |
|---|---|---|
| A checkout total could replace the original listing in comparisons. | Explicit listing price/time snapshot and shared quote contract. | Dates, airport alternatives, separate tickets and return-leg sums compare listing evidence on the same basis. Missing/stale originals require a fresh search. |
| Loose identity and broad price bands could corroborate different offers. | Matching flight numbers or complete segments, matching known baggage/fare family, tighter price agreement. | Missing identity and unexplained price disagreements cannot teach the brain. Agreement still does not prove full fare-condition equivalence. |
| Old accepted observations remained trusted after stronger checks. | Versioned persisted evidence; active history/export requires version 2. | Older observations are retained but excluded, not retrospectively declared valid. Old Red Room reports are also withheld pending a fresh check. |
| Keyword-only eligibility confused required and excluded payment methods. | Deterministic eligible/ineligible/unknown predicates with AND/OR/NOT, scoped bank/payment alternatives and exclusions. | Net banking need not require a credit card; an excluded bank's credit card does not exclude every credit card. Unknown eligibility stays conditional. |
| Freshly crawled expired offers could look current. | Parse explicit published booking windows, weekdays, account limits and minimum spend. | Crawling a March offer in October does not renew it. Unparsed windows/conditions remain unknown. |
| Coupon acceptance could be confused with a saving or an unrestricted existing coupon. | Separate accepted-no-saving outcome, preserve original terms, reject unreadable applied codes, check actual stable totals and cart/payment identity. | Winner selection uses measured payable amount, including a fee waiver if it wins. Cancellation/restoration and coverage limits stay explicit. |
| Provider failures were poorly distinguished. | Classified errors, exact manual search links, provider-run records and retained booking browser. | HTTP refusal, service failure and explicit no inventory are different outcomes. Failure cannot become a zero fare. |
| Cleartrip could render nearby promotions before exact-airport flights. | A bounded four-second parse retry when no valid requested itinerary has appeared. | Gives exact results a chance to arrive while continuing to reject substitutions. It does not promise exhaustive virtual-list coverage. |
| Each self-transfer leg inherited journey-start preferences. | First-leg time constraints and whole-journey stop counting. | A later departure for the second leg can qualify without exceeding the user's total stops. |
| Provider dropout could look like rising fares; a checkout could be compared to a listing forecast. | Common-provider daily series and separate market-listing comparator. | Missing sources are not interpreted as a price increase. Unverified future offers cannot trigger waiting. |
| Reopening an expired checkout could retain the previous cart's verification. | Reset a new cart to its freshly re-searched listing, discard old coupon/payment state and require verification again. | A prior payment total cannot certify a new cart, even for the same flight. |
| Restored stale quotes could cause new buy recommendations. | Freshness check at the brain boundary. | Old/invalid/future timestamps cannot create a current buying candidate. |
| Monitor jobs and notifications could duplicate across instances. | Atomic SQLite lease, ten-minute check bound, cancellation cleanup, unique saved-alert keys, separate attempt/success times and faster error retry. | Durable deduplication and failure visibility; desktop-delivery failure keeps the saved alert. |

Old illustrative airport transport costs are no longer seeded at startup. Active planning uses real fares and an explicitly entered ground-cost estimate. No new paid API, proxy, hosting service or database was introduced. Gemini is still optional and does not decide prices or eligibility.

## Fresh public application searches

All cases below are new relative to the earlier baseline matrix. Tests used public searches without passenger identity, payment details or purchases. Counts are displayed/accepted parser output, not exhaustive provider inventory. Each quote is **listed**, with checkout fees pending. “Corroborated” means a matching source fare under the stricter checks, not independent purchase proof. Failure on some sites makes these partial searches.

| Trip and date | Requirements | Google / EMT / Cleartrip / MMT rows | Corroborated rows | Outcome |
|---|---|---|---:|---|
| BLR–DEL, 2026-11-09 | 1 adult, economy | 12 / 12 / 11 / 0 | 20 | Lowest corroborated listing ₹9,278 on Cleartrip, Akasa 05:00; 17.78 s. |
| HYD–MAA, 2027-02-12 | 2 adults, economy, nonstop | 0 / 9 / 0 / 0 | 0 | Nine EMT listings; no accepted learning or buy-price comparator. Google had no readable priced nonstop fare; Cleartrip group units were unconfirmed. 45.42 s. |
| PNQ–CCU, 2026-11-19 | 1 adult, economy, morning | 0 / 12 / 0 / 0 | 0 | Twelve EMT listings remain uncorroborated; 10.55 s. |
| GOX–BLR, 2027-02-19 | 1 adult, economy | 3 / 12 / 0 / 0 | 4 | Lowest corroborated listing ₹7,018 on Google, IndiGo 17:25; 42.09 s. Later public Cleartrip probe found exact-airport ₹7,074 after loading, motivating the bounded retry. |
| DEL–CCU, 2026-11-23 | 1 adult, economy | 12 / 12 / 0 / 0 | 2 | Lowest corroborated listing ₹8,841 on EMT, Akasa 20:55; 11.77 s. Ran after restarting the actual app with repaired code. |
| MAA–HYD, 2027-02-23 | 1 adult, economy | 12 / 12 / 0 / 0 | 0 | Twenty-four uncorroborated listings; no invented forecast or cross-route learning. 11.19 s. Ran after restarting the actual app. |

These prices were observed on 8 October and can change. Raw evidence is under ignored sessions/validation/repair-*.json. The first four runs used isolated database/config and port 8766; the last two used the restarted normal app. Exact directed reverse journeys do not share fare histories, even when their dates or preferences differ.

After the delayed-card repair, a GOX–BLR recheck returned 3 Google, 12 EMT and 1 exact-airport Cleartrip listing, with 5 corroborated rows. The lowest corroborated listing remained ₹7,018; this partial search took 46.11 seconds. MakeMyTrip still failed. This proves recovery in that case, not universal Cleartrip coverage.

## Coupons and provider checkout diagnostics

PNQ–CCU, 19 November: the real EaseMyTrip booking-review page exposed **30 published codes**. Three read-only coupon trials produced:

| Code | Review baseline | Review amount after acceptance | Observed reduction |
|---|---:|---:|---:|
| BOOKNOW | ₹8,395 | ₹8,175 | ₹220 |
| EMTUPI | ₹8,395 | ₹7,995 | ₹400 |
| EMTNCF | ₹8,395 | ₹8,395 | ₹0 |

The baseline was restored between trials and the coupon cleared at the end. Payment was not selected. **These are review-stage results, not verified final prices or proof of UPI eligibility.** The remaining codes were collected but not all tested in a real payment cart. Automated local fixtures separately verify fee-waiver selection, eligibility filtering, baseline restoration, cancellation, winner reapplication and changed-cart rejection.

Six public source inspections found HTTP 200 on GrabOn's Cleartrip/EMT pages, CouponDunia Cleartrip, CouponZeta Cleartrip and Cleartrip's offers page. The tested EMT offers URL returned 404. Matching markup counts do not prove working coupons; no new directory was promoted to a trusted source from those checks. Native provider evidence plus merchant-scoped GrabOn remains the implemented collection path. “All good coupon websites” and every coupon's applicability are not established.

Cleartrip itinerary creation `/itin/v7/itinerary/create` returned **HTTP 403** and opened its failure page in fresh Chromium and Edge sessions. MakeMyTrip displayed a network/system error, failed HTTP/2 navigation, or returned an empty/`200-OK` placeholder. Warming its homepage, using Chrome and disabling HTTP/2 did not recover reliable listings. Those workarounds were not adopted. The precise remote refusal policy is unknown. An AI navigation library cannot establish that the provider permits access.

The merchant-displayed payment total is the scope of the app's checkout verification. Later issuer/gateway charges are unconfirmed. Unsupported layouts or missing directed airports, full year/date, flight number, adult/cabin or selected payment evidence fail verification. Connecting checkout layouts without an exact segment reader remain unsupported. No claim of successful payment-gateway traversal is made.

The app-level Cleartrip handoff check ran BLR–DEL, 9 November, through the actual WebSocket search/prepare/verify commands. It opened a browser, persisted ACCESS_DENIED on the listed result, refused verification without a payment total, and retained the session as HANDED_OFF for manual recovery. The reusable public check is backend/tools/validate_booking_handoff.py. No passenger/payment data was supplied.

The same app-level check on EaseMyTrip PNQ–CCU, 19 November, returned 12 listings, opened booking review and refused final-price verification without user-supplied passenger/payment entry. That session also remained HANDED_OFF; no booking error was detected. The handoff message now asks the user to review the itinerary and verify the amount rather than telling them to complete payment on a potentially failed page.

## Validation, data and runtime

The complete backend suite passes **112 tests** in a disposable project copy. One warning remains in an inactive legacy XGBoost model-loading test; that research model is not used by the live brain. Frontend production build/TypeScript and ESLint pass. New adversarial tests cover mixed price bases, missing identity, fare-condition mismatch, bank/method pairs, expired windows, unknown account conditions, stale quotes, provider dropout, whole-journey stops, cart changes, durable monitor leases, notification deduplication, old evidence/report exclusion and delayed exact-airport cards. Fixtures never enter the live database.

The app was restarted after an SQLite backup under ignored sessions/repair-validation/pre-migration.db. Changes are additive; historical rows and saved requests are preserved. The Windows login task is Running with StartWhenAvailable enabled. It needs an awake, logged-in computer. Browser inspection confirmed backend connection, the absence of an upfront card-ownership question, and the Red Room interface.

The post-recheck export recorded 17 version-2 accepted fares, 15 provider runs, 111 live offer-evidence records and 125 offer observations. Red Room successfully replaced its old report with version-2 evidence: GOI–HYD, 15 December, a listed ₹5,684 target-price candidate. This still requires payment verification; certainty remains uncalibrated. Other run evidence remains in isolated validation storage. More repeated scrapes in one day do not create independent forecasting history. The real forecast remains **Not calibrated**. No multi-year demand, future coupon or causal fuel/news model has been validated. Broader models/feeds in the plan remain proposals.

## Navigation tools considered

[Browser Use](https://github.com/browser-use/browser-use) and [Stagehand](https://github.com/browserbase/stagehand) provide AI-assisted browser navigation and extraction. Open-source code and local browser control can be free; model/hosted-browser services have separate requirements and possible costs. Neither was benchmarked as a superior replacement in this pass. Playwright remains the precise local browser controller; a future optional AI helper would need bounded navigation, exact evidence checks and the same no-purchase boundary. It would not be trusted to invent fares, infer successful coupon application or override access refusals.

The remaining release blockers are external provider access, exhaustive final-payment scenario validation, broader itinerary/website coverage, complete source-specific offer restrictions and enough comparable multi-day data to earn a forecast. Explicit partial results are the implemented behavior while those remain unresolved.

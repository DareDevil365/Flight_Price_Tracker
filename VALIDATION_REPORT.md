# Repair and validation report

Validated locally on 8 October 2026. Prices below are observations from that run, not current booking guarantees. No passenger/card/payment information was supplied and no ticket was purchased.

## What changed and why

| Previous behavior/problem | Implemented replacement | Reason |
|---|---|---|
| Default/estimated fares and LLM money extraction | Provider-visible INR fares, exact criteria, explicit errors | A generated number is not a real offer. |
| Synthetic ML prices, unsourced wiki claims and invented certainty in live advice | Accepted observations, dated evidence, deterministic decision rules and a gated local trend model | Predictions must earn trust against chronological holdouts. |
| Broad flight containers could combine fare/time/airline from different rows | Leaf-card parsing; reject multiple flight numbers without structured segments | Prevent mismatched itineraries from contaminating history. |
| Fixed adult/cabin/date URLs; nearby airport substitutions | Correct provider URLs, provider-criteria checks and independent output checks | A cheap fare for another trip cannot satisfy the request. |
| Bank/card ownership asked before search | Conditional offers first, then a restriction text box and cross-site comparison | Users can reject an unavailable deal without supplying a card inventory. |
| Advertised coupon savings subtracted across flights | Per-selected-flight checkout testing, observed payment totals and winner restoration | Coupons and fees depend on the actual cart/payment method. |
| Eight-code coupon cap; silent incomplete tests | All eligible unique codes attempted within seven minutes, with tested/eligible coverage and explicit not_tested results | Be useful without claiming exhaustive testing when time runs out. |
| Coupon radio counted as selected payment | Payment-specific evidence, exact applied-code checks and post-trial identity/payment recheck | Coupon selection cannot prove payment eligibility. |
| Crude/news context presented as fare predictions | Dated sources, stale/failure indicators and explicit context-only interpretation | Fuel costs/headlines do not establish route-specific causation. |
| Manually asking when to book | Persistent Red Room requests, scheduled checks and deduplicated saved alerts | Continue collecting and advising without repeated prompts. |
| Unbounded work and browsers held after listing | Global three-browser cap, lazy booking, cancellation, timeouts and expiring sessions | Bound local resource use and recover from provider failures. |
| Large initial frontend bundle | Lazy-loaded monitor/settings/history/chart pages | Initial JS is 251.29 KB (76.48 KB gzip); chart code loads separately. |
| Legacy tests could modify actual settings/models | Disposable-copy full-suite runner | Test evidence must not corrupt the real app or research artifacts. |

The active implementation is explained in [.gemini/context.md](.gemini/context.md), linked by [PROJECT_GUIDE.md](PROJECT_GUIDE.md). Existing model/scratch changes were preserved. Legacy experimental modules remain inactive rather than being treated as trustworthy data.

## Backend and frontend checks

The complete existing-plus-new suite passed **86 tests**, with one warning from a retained legacy XGBoost pickle compatibility test. That legacy ensemble is not used for live prices or booking advice. TypeScript/production build and ESLint passed.

Adversarial coverage includes missing/ambiguous/non-INR/negative/nonfinite prices, false coupon acceptance, stable totals and restoration, partial coverage, selected bank/product/network restrictions, coupon-versus-payment radios, conflicting fee totals, adult/cabin/date identity, direction isolation, per-request response IDs, stop/time preferences, connecting segment identity, quarantine, failed/stale searches, cancellations, Red Room persistence/removal/deduplication, negative forecasts, regime changes, stale series and baseline comparisons.

A final UI history check showed HYD–BOM on 8 February 2027 at ₹6,450, then reversing to BOM–HYD on the same date cleared the price and reported no observations. This checks direction isolation in the rendered app as well as the database.

Synthetic test fixtures are confined to temporary/local test pages and disposable databases. Passing them proves the implemented boundaries, not forecast accuracy or universal provider compatibility.

## Fresh live searches after repairs

These used the running application's WebSocket flow and real public provider searches, with new routes/dates about one or four months ahead. All amounts are **listed totals, fees/coupons pending**. Only corroborated healthy results supply the table's minimum. Group fares are explicitly for the stated adult count.

| Route | Departure | Criteria | Lowest accepted listed fare | Observed coverage |
|---|---|---|---|---|
| PNQ–JAI | 21 February 2027 | 1 adult, economy | Cleartrip ₹7,162 | Google 3, EaseMyTrip 12, Cleartrip 11; MakeMyTrip unavailable |
| BLR–HYD | 25 November 2026 | 2 adults, economy | Google ₹10,356 total for both | Google 10, EaseMyTrip 12; Cleartrip ambiguous units rejected; MakeMyTrip unavailable |
| CCU–BOM | 20 February 2027 | 1 adult, business, morning | Cleartrip ₹29,415 | Google 5, EaseMyTrip 12, Cleartrip 4; MakeMyTrip unavailable |
| GOX–HYD | 28 November 2026 | 1 adult, economy | EaseMyTrip ₹4,599 | Google 4, EaseMyTrip 12, Cleartrip 3; MakeMyTrip unavailable |
| CCU–HYD | 29 November 2026 | 1 adult, economy, morning, nonstop | Cleartrip/EaseMyTrip ₹8,491 | 4 quotes, all matching time/stops and corroborated; Google/MakeMyTrip unavailable |
| MAA–HYD | 23 February 2027 | 1 adult, economy, nonstop | Cleartrip ₹6,073 | 18 corroborated quotes across EaseMyTrip/Cleartrip; Google/MakeMyTrip unavailable |

The first four cases completed in roughly 10–14 seconds. The constrained MAA–HYD case took 20.64 seconds including the unsuccessful optional-reader/fallback attempts; subsequent stop-constrained searches bypass that optional reader. Network/provider performance varies.

Earlier tests covered GOI–HYD, DEL–MAA, GOX–JAI, reverse BOM–HYD/HYD–BOM, JAI–BLR, MAA–DEL, PNQ–GOX, BLR–JAI, business/morning, two-adult and separate return-leg requests. They exposed the MakeMyTrip container bug. Five rows produced by our own validation were backed up and quarantined, and two contaminated historical observations were flagged. Do not treat those old MakeMyTrip rows or their corroboration counts as successful provider validation.

Local evidence: sessions/validation/final-new-*.json, fresh-months.json and quarantined-mmt-container-test-data.json. The UI CCU–HYD search is persisted as eeb7e4b7-5e87-452b-8b3c-0378c321d6f9. A screenshot is saved as sessions/validation/final-deal-feedback.png.

## Coupon collection and real application tests

Six source/page inspections were saved under sessions/coupon-sources. GrabOn yielded explicit merchant flight codes but also related-merchant widgets; the parser now rejects those widgets and keeps the merchant's full terms. CouponZeta contained unrelated/expired/nonflight entries in the inspected page, so no adapter was adopted. CouponDunia did not expose usable static codes in that HTTP check. The inspected Cleartrip offer landing page did not expose static codes; native browser offer cards are used instead. An EaseMyTrip guessed offer URL returned 404 and was not integrated.

A refresh collected **72 candidate flight codes** across the three travel platforms; native browser codes add further candidates. This is collection coverage, not a claim that all codes work. EaseMyTrip's real booking review exposed **30 native codes** through View All Coupons. Unknown expiry remains unknown. International, financing, traveller/account/product/network and passenger restrictions remain conditional or are rejected as appropriate. Optional extra card cashback does not restrict an otherwise universal base coupon.

The real JAI–BLR, 8 February 2027, Air India Express IX-2069 booking review showed ₹9,294 before coupons:

| Code | Site acceptance | Observed review total | Interpretation |
|---|---|---|---|
| BOOKNOW | Accepted | ₹8,844 | ₹450 review-stage reduction |
| EMTUPI | Accepted | ₹8,744 | ₹550 review-stage reduction; UPI eligibility still needs actual payment confirmation |
| EMTNCF | Accepted | ₹9,294 | No review-stage reduction; a fee waiver cannot be claimed without payment-stage evidence |

Removing each code restored ₹9,294. The production verifier intentionally refuses to promote review-only totals to final payable prices. Final payment fees, the user's selected method and eligibility were not exercised end to end. Local evidence is in sessions/booking-probe/easemytrip-trials.json and corresponding HTML snapshots. Cleartrip's actual booking continuation returned its server-error page; this is reported as a failure, not a successful booking handoff.

There is no credible “all good coupon websites always work” guarantee: external coupon directories advertise terms that can be stale or inapplicable. Native offers plus an observed accepted code and a stable lower payment total are the final test. The app discloses failures and incomplete trial coverage.

## Fli: partial adoption only

[Fli](https://github.com/punitarani/fli) was benchmarked separately, without writing its results to the app database. Published 0.9.0's RPC implementation returned 7/8 cases and many unpriced/unknown-currency rows; it was not adopted. Upstream commit **881aee5ff4321e81ea2157cb44be94ce6a21dc1b**, reporting package version 0.10.0 when installed, uses a public-page reader and returned 8/8 isolated route/date/count/cabin cases. Raw calls took about 0.69–1.70 seconds, excluding child-process startup and app validation. All 41 overlapping itinerary/time/stops fares across five saved Google browser comparisons matched exactly. Unpriced/ambiguous rows were discarded.

Only that listing source was integrated, pinned in backend/requirements-google.txt. It runs in a hidden bounded child process, validates currency/route/date/segments and falls back to the existing Google browser worker. It does not apply coupons or verify payment. Google via Fli and Google via browser count as one source. Existing Playwright workers and booking flow remain.

Fresh nonstop cases showed a limitation: the public reader did not return validated priced nonstop rows, and an isolated upstream stop/time/cheapest-filter experiment did not solve it. That experiment was not retained. Stop-constrained searches therefore use the browser directly. The fresh constrained browser searches also failed on Google; other providers supplied results. **Fli is not better in every way**, and the integration claims only a useful optional fast path for the tested scope.

The upstream benchmark was executed with PYTHONPATH pointing at the cloned commit; its old JSON `version` field reflected the separately installed 0.9.0 distribution metadata, not the imported source revision. The exact commit above is the authoritative source identity. The benchmark tool now records installed distribution version and explicit source revision separately. Research artifacts are under sessions/fli-benchmark. Scrapling and StatsForecast were researched but not added because there was no demonstrated improvement for this app's current data/flows.

## Brain, data and Red Room

Actual accepted observations are isolated by directed route, travel date, adult count and cabin, with time/stops filtering. Only listed market fares train the trend series. Checkout totals remain separate because payment methods/add-ons vary. News uses dated source links; FRED Brent is a crude proxy, not Indian aviation turbine fuel. Feed failure/staleness stays visible. Multi-year seasonality, seat demand and unannounced bank anniversaries are listed as missing evidence.

The seven-day slope estimate needs seven nonoverlapping weekly holdouts after at least twenty training days, fresh observations and MAE at least 10% lower than last-price persistence. Twenty independent weekly outcomes and a passed gate are needed for a percentage, displayed as historical direction accuracy with a 95% interval. This is not a probability that a war/news item causes a price change. Current live history covers only one day: **Not calibrated** is the correct result. Deterministic rising/falling/flat/stale/regime-shift tests validate gating behavior, not real-world predictive skill.

Red Room's real saved validation request is GOI–HYD on 15 December 2026, one adult/economy, target ₹6,000, checking every 24 hours. After a backend restart, a manual recheck at 20:18 IST retained ₹5,684 without a duplicate alert. A real ₹5,684 listed fare met its target and produced a persisted BUY_CANDIDATE alert with verification pending and Not calibrated certainty. A limited-user Windows login task named Flight Finder Red Room was registered and observed running. It runs while the logged-in computer is awake; saved notifications are authoritative because desktop balloon visibility was not independently confirmed. Remove the test watch in Red Room if unwanted; disable startup with ./Enable-RedRoom.ps1 -Disable.

Explore's live DEL–GOI comparison found 14 October ₹7,216 versus 15 October ₹7,559, a ₹343 listed saving. A GOX alternative's ₹214 airfare saving lost ₹1,786 after the entered ₹2,000 transfer estimate, so it was not recommended. No qualifying cheaper self-transfer was found in that test; none was invented. Terminal and road/cab details remain unknown unless sourced; separate tickets require four/five-hour buffers and disclose baggage/fee/missed-connection risks.

Accepted evidence can be exported with backend/tools/export_brain_dataset.py. sessions/brain-data/manifest.json contains the latest exact counts and policy. The final export has 392 accepted fare observations, six feed-cache records, 25 linked headline sources, 111 current public-offer evidence records and 123 offer snapshots. These are observations/candidates, not 392 independent days or 111 verified discounts. Repeated same-day searches cannot manufacture observation days or bypass forecast gates.

## Remaining practical limits

- Complete final-payable coverage is not validated across all providers. Real passenger/payment entry remains user-assisted; blocked pages, ambiguous eligibility and server errors fail closed. No purchase is automated.
- MakeMyTrip remains unreliable in these live checks. Yatra, Ixigo, Paytm and newly added sites are manual links until provider-specific adapters are validated. A homepage loading does not establish an integration.
- General international, fare-family, baggage, mixed-cabin, account eligibility and protected-connection coverage needs more live evidence. Return trips are separate one-way searches, not a combined return cart.
- Forecast accuracy needs months of comparable real observations and independent evaluation. No claim of a mature predictor, universal lowest fare or break-proof external websites is made.
- Monitoring requires the local machine/backend to run. Browser sessions do not survive a backend restart.
- The initial legacy test run may have removed an existing saved profile. Tests are now isolated; review saved financing/payment exclusions. Existing research model and scratch changes were preserved.

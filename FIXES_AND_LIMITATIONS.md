# Fixes and practical limitations

The latest [fresh concept/code audit](FRESH_CONCEPT_AUDIT_2026-10-10.md) records additional reproduced checkout, budget, financial-instruction, coupon, alert and UI defects and their repairs. The earlier [source/runtime audit](DATA_AND_MMT_REPAIR_2026-10-10.md) records MakeMyTrip login recovery, data provenance and remaining merchant/payment limits.

The repair replaced fabricated/default prices, synthetic live predictions and inferred coupon savings with sourced observations and explicit verification states. See [REPAIR_VALIDATION_2026-10-08.md](REPAIR_VALIDATION_2026-10-08.md) for the latest comparison, coupon-rule, provider and monitoring repairs. [VALIDATION_REPORT.md](VALIDATION_REPORT.md) retains the earlier baseline. [PROJECT_GUIDE.md](PROJECT_GUIDE.md) links the architecture and setup.

## Working in the active application

- Real provider listing searches with exact directed route/date/adults/cabin and time/stops checks; ambiguous group units and incorrect route substitutions are rejected.
- Listed fares are separate from verified payment totals. Coupons require actual acceptance, a stable payable reduction, baseline restoration and winner reapplication on the selected itinerary/payment.
- Native offer discovery plus merchant-scoped GrabOn collection; source URLs/terms/unknown expiry stay explicit. All eligible unique codes are attempted within a bounded budget, with incomplete coverage reported.
- Conditional deals first, followed by a text box for unavailable banks/cards/payment methods. Remaining options are compared across searched sites without inventing coupon-adjusted prices.
- Independent output checker, cross-site exact-itinerary corroboration, suspicious-result quarantine and accepted-only learning. Reverse routes/count/cabin/time/stops do not silently overlap; connecting flights require full segment evidence.
- Dated fuel/FX/news evidence, deterministic buying/waiting rules, gated trend estimates and measured certainty only after enough independent outcomes. Cold starts say Not calibrated.
- Persistent Red Room future-trip requests, periodic checks, saved deduplicated alerts and optional Windows login startup.
- Fresh-date, GOI/GOX and conservative separate-ticket exploration with explicit transfer costs, unknown terminals and baggage/protection limitations.
- Bounded concurrency, lazy booking sessions, timeouts/cancellation, isolated tests and frontend code splitting.
- Partial Fli adoption for a tested optional Google listing path; Playwright remains the browser/booking engine. Stop-constrained searches bypass the optional reader after live failures.

## Remaining work and limits

1. Final-payable/coupon flows need broader real payment-page validation on every provider and fare family. Review-stage savings are not final-price proof. The app requires user passenger/payment entry and never purchases tickets.
2. MakeMyTrip is unreliable/empty in current live checks; Chrome and disabling HTTP/2 did not recover usable listings. Cleartrip's itinerary creation returned HTTP 403 in Chromium and Edge. These remote failures are classified and disclosed; local selector changes cannot establish that access is fixed. Other saved sites such as Yatra/Ixigo/Paytm are manual links until validated adapters exist.
3. Coupon directories cannot guarantee current applicability. Account, traveller, card product/network, app, fare, carrier, weekday and stacking conditions can remain unknown. Unconfirmed restrictions cannot establish a verified saving; bounded trials disclose omissions.
4. A forecast needs longitudinal comparable real observations. Most exact-trip cohorts currently cover one observation day, despite many scrapes; one earlier cohort has two. No real predictive accuracy, multi-year seasonality, seat demand or unannounced bank-anniversary offer is claimed.
5. International, mixed-cabin, baggage and protected-connection coverage needs more evidence. Round trips are separate one-way searches rather than combined-return carts. Unknown terminal/road/cab details remain unknown.
6. Red Room runs only while the local backend/computer is awake. Windows notification visibility depends on settings; saved alerts are authoritative. Sessions expire and cannot survive backend restarts.
7. Public page formats/endpoints change. Fli's benchmark success did not extend to every constrained request; it is a bounded optional source with browser fallback, not a universal replacement.
8. The initial legacy test run may have removed an existing saved profile. Tests now run in a disposable copy; review saved financing/payment exclusions. Existing research models and scratch changes were preserved and are not trusted by the live brain.

## Verification

The latest complete isolated suite and fresh live outcomes are recorded in [the follow-up report](REPAIR_VALIDATION_2026-10-08.md); the earlier baseline passed 86 tests. Frontend production build/TypeScript and ESLint passed. New regressions cover price bases, ambiguous eligibility, scoped bank/payment conditions, stale evidence, changing cart options, provider dropout, duplicate monitor jobs and old evidence exclusion. No real passenger/card/payment data was entered. Passing tests does not make external websites break-proof or establish a universal cheapest final fare.

## 9 October: in-memory page inspection and scoped coupon evidence

Rendered-DOM coupon control resolution, strict monetary-row inspection and optional cropped RAM-only images are implemented. Public probe tools no longer write page dumps. A new visible additive coupon ledger preserves filtered/conditional/rejected/inconclusive/error/untested outcomes, source terms, context and time. Unknown profession/account/payment requirements cannot win, newly displayed terms are checked again, and sign-in overlays abort without a forced click or fabricated total. Legacy global coupon success statistics are no longer updated by these trials. Final isolated backend validation: 374 passed; frontend build/lint passed. Four real runs preserve 152 trial records. A fresh review run tested all six eligible collected codes and restored EASEFLY at ₹7,598 from ₹7,998, while eighteen conditional offers remained unconfirmed. Final payment charges, exhaustive coupon discovery, MakeMyTrip/Cleartrip checkout recovery and calibrated forecasting are still unproven. [Detailed evidence](PAGE_INSPECTION_AND_COUPONS_2026-10-09.md).


## Research follow-up — 9 October 2026

See [research, changes and fresh validation](RESEARCH_AND_REPAIRS_2026-10-09.md). Added public EMT flight/bank feeds alongside GrabOn; protected an existing cheaper coupon/cart; separated optional cashback from base discounts; withheld conflicting route-scope terms; withdrew old checkout verification before a recheck; added progress and automatic ledger refresh; removed unused API-body collection; and blocked stale/discontinuous forecast evidence. Final validation: 446 isolated backend tests, frontend build/lint and forecast skill validation pass.

A real ordinary browser reached Cleartrip review and accepted CTBBD (BLR–LKO, 23 February 2027, INR 6,785 to 6,344). The automated fresh browsers still failed its booking continuation. The companion now has a tested partial review reader but is neither installed nor integrated. EMT AMD–IXC, 17 November review tested all four eligible collected codes and restored BOOKNOW at INR 6,499 from 6,719. Both are review-only; final payment/convenience fees, all-coupon coverage, stable MMT access and calibrated predictions remain unproven. Six ledger runs/223 trial facts and 132 accepted fares are real recorded evidence, not proof of longitudinal calibration.

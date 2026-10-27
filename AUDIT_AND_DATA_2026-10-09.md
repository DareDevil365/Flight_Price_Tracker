# Audit repairs and real initial data — 9 October 2026

Three separate agents audited public navigation/checkout, scraping/efficiency, and booking reasoning. The scope is Indian domestic flights; global oil and currency remain upstream context. The app still uses free local SQLite and Playwright. No paid API, synthetic live seed or new LLM navigation dependency was introduced.

Read the detailed [navigation audit](NAVIGATION_AUDIT_2026-10-09.md), [scraping audit](SCRAPING_AUDIT_2026-10-09.md) and [brain audit](BRAIN_AUDIT_2026-10-09.md). Their observations distinguish repairs from external access failures and proposals.

## What changed and why

| Flaw | Implemented repair |
| --- | --- |
| Closing Google could close an already-open merchant popup | Session lifecycle follows remaining tabs; only closing the last tab ends the session. Expiry comparisons normalize UTC. |
| Money readers could turn malformed/scientific/per-person text into a plausible low total | Validate complete INR tokens, grouping, precision and group-total scope; unreadable fees remain unknown. |
| Native coupon input skipped validation; an insurance-combo offer looked unconditional | Apply the same code guard and require explicit add-on eligibility evidence. Optional insurance does not become mandatory. |
| Hidden price-unit text, deposit prices and unusual floated containers affected fare extraction | Use visible evidence, recognize supported current-fare variants, exclude lock/deposit amounts, and preserve valid painted children. Ambiguous unsupported cards still fail. |
| Requested cabin and domestic timezone could disagree with known flight evidence | Reject conflicting leg cabins and non-IST offset clocks; check group totals for overflow. |
| Partial public pages looked like complete inventory | Preserve observed/parsed/rejected source counts and show partial coverage. At most twelve cheapest valid rows per website/leg are ranked; this cannot prove the cheapest ticket across every website. |
| Advice verdict, urgency and confidence could come from different decisions | Use the same brain decision for the displayed advice fields. Explicit budget misses stay visible. A qualified declining forecast takes precedence over an unvalidated percentile bargain when no target is met. |
| Global headlines could veto domestic waiting; loose words matched irrelevant news | Tighten disruption matching and keep unmeasured global fuel/news effects as caveats, rather than causal fare predictions or certainty boosts. |
| Learning/export trusted database filters alone | Recheck supported source, accepted version-2 integrity, directed domestic route, exact trip, timestamps, valid schedule/stops and price basis. The exporter records excluded candidate reasons. |
| An asynchronous advice failure only appeared in server logs | Bound requests to ninety seconds and return a request-scoped error displayed in Price Intelligence. No recommendation is fabricated on failure. |

Google selected-itinerary context also rejects an explicit conflicting year and malformed typical-range amounts. UI wording no longer calls every historical listing verified or equates every buy candidate with imminent departure.

## Real initial context loaded into SQLite

These are actual published records, separate from fare learning. Reviewed source excerpts and hashes are stored under ignored `sessions/source-audit-2026-10-09/`; SQLite backups, provenance and manifests are under `sessions/source-bootstrap/`.

| Source | Loaded records | Latest published observation | Use and limitation |
| --- | ---: | --- | --- |
| [FRED Brent](https://fred.stlouisfed.org/series/DCOILBRENTEU) | 951 daily records since January 2023 | 6 October 2026 | Global crude proxy; not Indian airline contracted jet-fuel cost. |
| [FRED USD/INR](https://fred.stlouisfed.org/series/DEXINUS) | 940 daily records since January 2023 | 2 October 2026 | Currency context, with no invented route-fare coefficient. |
| [AAI traffic reports](https://www.aai.aero/en/business-opportunities/aai-traffic-news) | 136 airport-month rows from eight reports, seventeen airports | August 2026 | Domestic arrivals plus departures, with same-month previous-year comparators; not directed route demand or seat inventory. |
| [IOCL historical ATF](https://iocl.com/atf-domestic-airlines) and [dated current-page domestic block](https://iocl.com/prices-of-petroleum-products) | 100 city-month observations | **1 April 2026; stale** | Delhi, Kolkata, Mumbai and Chennai, INR/kilolitre. The current-page table still has an April date; October LPG/footer dates cannot refresh it. Ordinary HTTP access failures remain visible. |
| [IndiGo domestic operational statistics](https://www.goindigo.in/information/investor-relations/operational-statistics/domestic.html) | 96 validated carrier-month rows, April 2015–July 2026 | **July 2026; stale** | Actual passengers, passenger kilometres, available seat kilometres and load factor. Carrier-wide domestic scope only. Two truncated December/January source rows were excluded; missing months remain missing. |
| EIA / PIB / reported news feeds | 4 / 0 / 23 currently matched dated headlines | Individual article dates | Primary and reported sources labelled separately; no headline manufactures a flight price. Zero matched PIB items means no relevant items from that feed, not no aviation developments. |

The new `backend/carrier_context.py` validates domestic fiscal-year columns, units, dates and the printed load-factor calculation. It rejects inconsistent rows. Failed runtime refreshes preserve cached observation dates instead of calling old records fresh. Reviewed imports are explicitly identified as reviewed primary-page extractions, not successful automatic HTTP retrieval.

Offer refresh found 106 published candidate codes: EaseMyTrip 9, ixigo 16, Yatra 18, MakeMyTrip 26 and Cleartrip 37. Paytm's configured source returned HTTP 404. Discovery does not establish eligibility or redemption success; ixigo/Yatra offer collection does not imply a working fare/checkout adapter for them.

## Fresh functioning checks

Agent probes used PNQ–JAI on 18 November 2026, ATQ–DEL Business on 23 February 2027, BBI–HYD for two adults on 20 February 2027, GOX–HYD on 21 February and IXC–CCU on 27 November 2026. See each agent report for exact results, rejected rows and timings.

Additional complete application searches used new routes/dates:

| Requested trip | Google / EMT / Cleartrip / MMT rows | Integrity and reasoning | Elapsed |
| --- | --- | --- | ---: |
| AMD–COK, 28 November 2026, one adult | 8 / 12 / 11 / 0 | 31 uncorroborated listings; no learning or buy advice | 12.69 s |
| COK–AMD, 23 February 2027, two adults, nonstop | 0 / 1 / 0 / 0 | One uncorroborated group listing; other sources explicitly unavailable; separate reverse-route history | 11.53 s |
| DEL–JDH, 26 November 2026, morning, nonstop | 1 / 4 / 4 / 0 | Eight corroborated rows, one uncorroborated; cheapest corroborated listed fare ₹7,711, Cleartrip Air India Express at 11:10 | 11.89 s |
| MAA–GAU, 25 February 2027, nonstop; final restarted code | 0 / 2 / 2 / 0 | Four corroborated rows; cheapest corroborated listed fare ₹7,718, Cleartrip IndiGo at 21:00; Google/MMT unavailable | 12.83 s |

The first two correctly produced MONITOR with zero accepted history days. DEL–JDH produced MONITOR with one observation day. All three had no numeric certainty. Timings describe these observed runs, not a guarantee or controlled performance comparison.

A real EaseMyTrip GOX–HYD review coupon trial reduced ₹7,188 to ₹6,968 using BOOKNOW and restored the baseline. This is **review-stage evidence**, with no selected payment method. It is not proof of a final fee-inclusive total. Cleartrip's actual continuation returned HTTP 403, and MakeMyTrip returned an empty page. Their final-payment coverage remains unproven.

## Validation and remaining work

Final shared validation passed **344 backend tests**, with one existing legacy XGBoost serialization warning, in **114.08 seconds**. Frontend production build/TypeScript and lint passed after all UI changes. Test fixtures stay in a disposable project copy and never become live fares or forecast training data. Logs are `logs/audit-20261009-backend-full.log`, `logs/audit-20261009-frontend-build.log` and `logs/audit-20261009-frontend-lint.log`.

The final export contains **126 accepted fares**, nine context caches, 31 linked knowledge records, 145 offer-evidence records, 293 offer-observation snapshots and 69 provider runs. The stricter validator excluded zero of the accepted version-2 candidates; older/unaccepted rows remain outside the export. There are thirteen directed route/date/adult/cabin cohorts, each with one observation day. The manifest is `sessions/source-bootstrap/brain-data/manifest.json`.

Read-only live `brain:get` checks on DEL–JDH at ₹7,711 returned MONITOR for a ₹5,000 target and BUY_CANDIDATE for an ₹8,000 target, explicitly on a listed-fare basis with payment fees pending. JDH–DEL returned no accepted price/history. An invalid negative target returned `brain:error`, rather than leaving the request pending. Every valid report retained null certainty and displayed stale carrier context. Artifacts are `sessions/source-audit-2026-10-09/live-brain-checks.json`. A fresh frontend reload displayed MONITOR, Not calibrated and the evidence-readiness explanation. The locally running backend is healthy; browser sessions from before its restart cannot be reused.

No real directed route/date cohort has enough longitudinal evidence for a calibrated forecast. Repeated same-day scans, years of aggregate carrier capacity and news do not fill that gap. Numeric certainty still requires independent chronological weekly outcomes and a model that beats the last-price baseline. Provider-coverage changes conservatively withhold the aggregate model; fixed-provider cohort calibration is a possible future improvement, not implemented recovery.

The remaining material gaps are full merchant/payment access, exact connecting-segment evidence on unsupported layouts, standardized baggage/fare families, route-level demand/seat inventory, and longitudinal comparable fares. The app returns partial evidence and failure explanations where these are missing.

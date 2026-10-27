# Agent audit and real-data bootstrap, 8 October 2026

Scope: domestic Indian flight prices. Global oil, currency and disruption context remains relevant. All services used here are free; SQLite remains local and no cloud database or paid navigation/model service was added. Three agents audited scraping, browser/coupon navigation and prediction/advice, with root reviewing integration and gathering sources.

## Confirmed flaws and replacements

| Area | Flaw | Implemented repair and reason |
| --- | --- | --- |
| Public Google/Fli rows | A malformed row could discard other valid inventory; QP airline enum incorrectly said Air Kenya Aviation | Normalize each row independently. Use Google's displayed Akasa Air name when codes match, otherwise preserve the actual airline code without guessing. A fresh COK–BLR probe exposed and verified this repair. |
| Scope and money | Foreign currency, missing nearby-origin evidence, repeated group conversion, ambiguous/struck prices and fare-family deduplication | Require explicit INR and matching airport evidence, retain group units after conversion, reject ambiguous money, and preserve distinct fare families. Structured domestic itineraries reject foreign hubs. |
| Card parsing | Identical clocks lost an arrival; invalid AM/PM accepted; wrappers checked against every card | Validate clocks and preserve repeated times. Mark wrappers by walking ancestors, reducing quadratic card comparisons to card-count times DOM depth. |
| EMT readiness | A valid visible current fare lacked the old price attribute; the readiness selector matched a hidden original-price element and wasted up to 35 seconds | Wait for a lightweight visible INR fare-card predicate, excluding hidden/struck/coupon/foreign amounts. Remove the fixed 1.5-second sleep. A read-only single-provider recheck returned 23 rows and the same ₹4,703 itinerary in 7.78 seconds total, 5.56 seconds in search readiness. |
| Coupons | Clearing the field did not prove removal of an applied discount; cancellation/winner failure could leave a different cart | Prove baseline restoration and restore the original code/total on cancellation or failure. Acceptance without a reduction is not a saving. |
| Coupon terms | Stale database duplicates could replace current native restrictions; multiline and long terms lost uncertainty | Current native terms take precedence. Preserve line boundaries and unsupported/truncated eligibility uncertainty, including after SQLite reload. Check supported passenger/account/payment restrictions. |
| Browser actions | Generic Apply fallback could click a nearby Submit button; text entry repeated unnecessarily | Require an explicit scoped coupon Apply control. Fill once with Playwright arguments and reject malformed codes before interaction. |
| Checkout trust | New unrelated popup could look like a payment page; expired sessions sometimes survived until cleanup | Require the adapter's expected HTTPS provider host throughout verification. Reject expired sessions immediately; active coupon sessions cannot be evicted by new bookings. External gateways remain outside merchant proof. |
| Advice | Future/malformed/stale observations, reverse routes, party/cabin mismatches or unsupported date savings could influence advice | Shared `advisor_evidence.py` validates exact scope and freshness at the advice boundary. Date alternatives carry quote/reference evidence; unavailable evidence yields an unverified comparison, not a saving. |
| Forecast validation | Later provider coverage selected the historical cohort; accuracy and MAE could describe different periods | Withhold calibration when provider coverage changes. Use calendar-spaced weekly outcomes and the same recent twenty outcomes for accuracy and MAE. Specific-flight requests do not use pooled itinerary history. |
| Airports | Old hand-maintained country list included invalid/foreign entries and omitted Jodhpur | Use a sourced, hashed OurAirports India reference (164 IATA-coded airports). It establishes location, not current bookable service. Validate domestic airport pairs before any provider search. |

`PROJECT_GUIDE.md` links the existing detailed architecture explanation rather than duplicating it. The active app still uses deterministic ranking/evidence checks, Playwright, optional bounded Fli extraction and SQLite. Gemini does not establish fares, eligibility or forecast certainty.

## Real initial evidence

The database was backed up with SQLite's backup API before imports. Parsed observations and manifests live under ignored `sessions/source-bootstrap/` and `sessions/brain-data/`; no illustrative price history or model seeds were imported.

| Feed | Imported evidence | Actual latest observation | Use and limitation |
| --- | --- | --- | --- |
| [FRED/EIA Brent](https://fred.stlouisfed.org/series/DCOILBRENTEU) | 951 daily values from January 2023 | 6 October 2026 | Global crude proxy in USD/barrel; not Indian jet fuel or route fares. |
| [FRED USD/INR](https://fred.stlouisfed.org/series/DEXINUS) | 940 daily values from January 2023 | 2 October 2026 | INR/USD cost context; cannot establish airline pass-through to fares. |
| [IndianOil historical ATF](https://iocl.com/atf-domestic-airlines) | 96 city-month values, April 2024–March 2026 | 1 March 2026 | Delhi, Mumbai, Kolkata, Chennai in INR/kilolitre. **Stale**, excluded from current pressure claims. Primary-page table reviewed through research browsing; ordinary app HTTP/browser access returned a challenge, explicitly recorded as unavailable. |
| [AAI traffic reports](https://www.aai.aero/en/business-opportunities/aai-traffic-news) | Eight January–August 2026 passenger PDFs, 136 rows over 17 airports; each includes the same-month previous-year comparison | 31 August 2026 | Domestic arrivals plus departures, not unique passengers, route bookings, future demand or seat inventory. Counts and printed percentages cross-checked; monthly columns separated from international/cumulative tables. Subject to source revisions. |
| Public news | Four EIA headlines and 21 separately labelled reported headlines | Dates retained per item | No relevant PIB aviation headline returned. News is context and never creates a fare or causal coefficient. |
| GrabOn offer discovery | 106 advertised codes across five merchants | 8 October 2026 collection | 9 EMT, 37 Cleartrip, 26 MMT, 18 Yatra, 16 ixigo. Paytm source returned HTTP 404. These are candidates, not 106 working discounts. |

`evidence_feeds.py` validates finite positive values, dates, currency/units, source hosts, report headers, exact airport rows and printed percentage agreement. Fetches have time/size limits and PDF parsing runs outside the event loop with two-report concurrency. Unsupported documents fail closed and retain dated prior context. FRED begins with 2023 history and thereafter updates an overlapping fourteen-day window. AAI normally refreshes the latest two published reports; explicit bootstrap collects eight discovered links. Fuel is stale after seven days for Brent/FX and 35 days for posted ATF; airport traffic after sixty days. Calendar/source dates matter, not a refreshed website footer.

Run from the root:

```powershell
backend/.venv/Scripts/python.exe backend/tools/bootstrap_brain_data.py
backend/.venv/Scripts/python.exe backend/tools/export_brain_dataset.py
```

The bootstrap can accept an explicitly reviewed IOCL table with `--atf-text <path>`. This is an optional source import with provenance; it does not synthesize prices or pretend blocked HTTP access succeeded. `pypdf==6.19.0` is the only new runtime dependency: free, local, pure Python PDF extraction. Rendered AAI domestic tables were visually checked with Poppler during validation.

## New live route/date checks

All cases below are one adult, economy, one way, any departure time. Provider inventory is partial. Counts are Google/EMT/Cleartrip/MMT, with a maximum twelve stored quotes per provider. Prices are listing comparisons, **not final amounts including every checkout/payment charge**.

| Directed route | Departure | Provider counts | Corroborated rows | Cheapest corroborated listing | Elapsed |
| --- | --- | --- | --- | --- | --- |
| JAI → BLR | 8 November 2026 | 8 / 12 / 11 / 0 | 0 | No trusted recommendation; 31 uncorroborated listings | 15.03 s |
| BOM → HYD | 15 November 2026 | 9 / 12 / 10 / 0 | 25 | Cleartrip ₹6,535, IndiGo 21:35 | 11.16 s |
| HYD → BOM | 8 February 2027 | 10 / 12 / 10 / 0 | 24 | Cleartrip ₹6,450, IndiGo 17:15 | 10.95 s |
| MAA → DEL | 18 February 2027 | 9 / 12 / 1 / 0 | 6 | Cleartrip ₹10,517, IndiGo 11:00 | 11.22 s |
| PNQ → GOX | 22 November 2026 | 5 / 12 / 8 / 0 | 6 | Cleartrip ₹4,703, IndiGo 05:00 | 43.72 s, exposing EMT readiness wait |
| BLR → JAI | 12 February 2027 | 9 / 12 / 0 / 0 | 4 | EMT ₹8,651, Air India Express 17:10 | 27.41 s |
| COK → HYD, adjacent-date range ±1 | 24 February 2027 | 8 / 12 / 11 / not requested | 10 | Cleartrip ₹5,960, IndiGo 15:10 | 10.67 s |

MakeMyTrip produced no readable listings in all six cases. Cleartrip could not confirm criteria in the last case; that failure was reported. No replacement fare was fabricated. BOM → HYD and HYD → BOM retain separate histories. A separate read-only COK → BLR, 23 November probe returned Google/Fli ₹4,422 and EMT ₹4,072; those observations did not enter the database.

The initial six-case matrix produced 162 listing rows, 65 corroborated, bringing the accepted version-2 export to 82 observations over eight directed route/departure cohorts. The further COK → HYD app check exercised adjacent-date lookup, produced 31 listings and accepted ten more rows: the final export contains **92 fare observations** over nine cohorts, each with **one observation day**. More rows on one day do not provide independent forecast outcomes. The brain correctly reported `INSUFFICIENT_DATA`, `MONITOR` and no numerical certainty; the first matrix case had no trusted current fare. No cheaper-date suggestion was emitted in the additional case. Real fuel/traffic data does not bypass the forecast gate. Final export also has 44 provider runs, 145 live offer-evidence entries, 171 dated offer observations and eight context cache entries.

## Fresh on-site coupon probe

EMT PNQ → GOX, 22 November 2026 reached booking review for 6E-6944, 05:00. Twenty native codes were discovered. Three direct public-control trials returned to the ₹4,703 baseline before each code:

| Code | Review total | Measured review reduction | Outcome |
| --- | --- | --- | --- |
| BOOKNOW | ₹4,483 | ₹220 | Accepted at review |
| EMTUPI | ₹4,303 | ₹400 | Accepted at review; payment eligibility still unverified |
| EMTNCF | ₹4,703 | ₹0 | Accepted without a saving |

The page explicitly said additional charges may apply, and selected payment was absent. These are not verified final prices or evidence that every coupon works. No traveller/contact/payment details were entered, no checkout training rows were added from this probe, and no ticket was purchased.

## Validation and remaining boundaries

Baseline: 112 isolated backend tests. Final integrated audit: **204 isolated backend tests passed**, including 92 additional cases; frontend production build and lint passed after the new domestic scope text and traffic comparator display. Isolated copies protect the live database, profile and model files. One existing inactive research-model serialization warning remains. Adversarial tests cover invalid currency/identity/timestamps, coverage lookahead, airline/itinerary leakage, coupon cancellation/restore, uncertain terms after database reload, provider origin, submission controls, feed headers, context-only cold starts and EMT readiness. Logs and public snapshots are retained in ignored runtime folders. The backend was restarted with all repairs and its health endpoint returned service flight-finder/status ok.

Remote MakeMyTrip/Cleartrip access and full live final-payment verification remain limitations. Merchant totals cannot prove later issuer/gateway charges. Full-site/all-coupon coverage, route-specific demand, multi-year fare seasonality and calibrated future certainty remain unproven. Red Room can collect real comparable evidence over time while the local backend and awake computer run; it must not invent historical outcomes to look ready.

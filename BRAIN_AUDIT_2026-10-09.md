# Indian domestic flight brain audit — 9 October 2026

This audit rechecked the active deterministic brain, evidence boundaries, advice wording, model readiness and source context. It implemented the repairs below. It did not purchase tickets, mutate the live database, import invented prices or promote legacy synthetic models into the app. Test histories are deliberately artificial fixtures in disposable databases; they test software behavior and establish no live forecast accuracy.

## Confirmed flaws and implemented repairs

| Finding | Repair and reason |
|---|---|
| A near-departure rule could approve a fare above the user's explicit target. | An unmet target now remains a monitoring/review result with high deadline urgency. The explanation explicitly states the target was missed. A listed fare meeting a target is qualified as being before unverified checkout charges. |
| A steadily falling, validated series was classified as a historical bargain before its downward forecast was considered. | An eligible passed downward model now precedes the percentile bargain rule. Target thresholds and departure deadlines have explicit separate rule identities. A target candidate with a lower qualified forecast explains that tension rather than claiming today's fare is the minimum. |
| Top-level verdict came from the brain while confidence, urgency and book-by came from a different fallback advisor. | Those fields now come from the same brain decision. The conservative fallback remains available when no brain is supplied. |
| History relied on database filtering without independently rechecking schedule, stops or quality. | `advisor_evidence.history_row_problem` and `accepted_history_row` validate real supported providers, version/quality, directed Indian airports, date, adult/cabin types, known schedule/stops, finite prices, timestamps, price basis and stored integrity evidence. Exact-trip filtering then independently checks time, stops, airline and flight number. |
| Malformed cached feeds could crash advice, or missing links/units could appear as grounded context. | Readers reject malformed payloads/rows and unsupported source URLs. The report exposes `context_problems`. Macro factors retain observation dates and units. FRED's nominal 30-day comparison accepts only an actual 30–37-day reference and exposes the reference date/span. |
| The disruption expression matched words such as “award”, “forward” and “software”. | Word boundaries prevent those false matches. A legitimate headline is described as mentioning disruption; its geography and relevance to an Indian domestic journey remain unconfirmed. |
| Any recent global conflict headline or arbitrary fuel threshold could veto a domestic waiting recommendation. | Those observations are descriptive caveats. Without a measured route-level relationship they do not override the passed fare model, create a purchase signal, or change its certainty. This is a modeling decision, not a claim that disruption cannot affect aviation. |
| Future offer evidence was checked by lexical timestamp comparison, allowing future crawl times. | Aware, nonfuture seven-day freshness is checked in Python. Published future booking windows are assessed on their actual opening date and remain explicitly unverified for eligibility/savings. They never create predicted anniversary discounts or justify waiting. |
| Two observation dates crossing New Year could be called two historical years. | Full observed span determines `historical_years`; calendar labels are retained separately. Two days cannot establish multi-year seasonality. |
| A verified option could obscure cheaper unverified listings. | The reasoning identifies the scope as verified merchant totals and mentions lower listings still needing their own fees/coupon checks. It does not claim exhaustive cheapest-price coverage. |

Structured `decision_basis` now identifies the actual rule, target comparison, accepted/verified quote counts, lower unverified options, whether a forecast was used, and that news was not used as a causal prediction. SmartAdvisor also filters explicit payment exclusions before constructing layover suggestions.

## Real data available at the read-only audit snapshot

At **08:12 IST on 9 October 2026**, the live SQLite snapshot contained **122 accepted version-2 fare rows across 12 directed route/date/adult/cabin cohorts**. The generic evidence validator rejected none of those rows. **Every cohort still had at most one distinct observation day.** More itineraries or repeated searches cannot create independent weekly forecast outcomes. The compact read-only snapshot is saved under ignored `sessions/research/brain-audit-2026-10-09.json`; later collection can change these counts.

The source cache separately contained:

| Context | Validated rows | Actual latest observation | Scope |
|---|---:|---|---|
| Brent crude | 951 | 6 October 2026 | Global crude proxy, USD/barrel; not Indian airline fuel contracts. |
| USD/INR | 940 | 2 October 2026 | INR per USD exchange-rate context. |
| AAI domestic airport traffic | 136 | August 2026 | Eight reporting months, arrivals plus departures; not directed-route demand, unique travellers or seat inventory. |
| IndianOil metro ATF | 100 | 1 April 2026 | Four-city dated INR/kilolitre prices; stale on the audit date. |
| IndiGo domestic capacity/utilisation | 96 | July 2026 | Carrier-wide monthly passengers, RPK, ASK and published passenger load factor; stale, not a route forecast. |

The capacity factor checks RPK/ASK consistency against the published load factor and labels utilisation as a percentage of available seat-kilometres occupied. A same-month prior-year comparison, when present, is in percentage points. Empty, truncated, future or unsupported rows do not supply a factor. These context records **never become fare training rows, route prices or calibrated outcomes**. A fresh import time does not make an old observation current.

## Primary sources checked and their useful limits

- [AAI traffic publications](https://www.aai.aero/en/business-opportunities/aai-traffic-news) provide airport passenger and aircraft-movement reports. Their domestic monthly tables and prior-year columns are useful background; adding up two airports is not a measure of their connecting route's demand.
- [IndiGo domestic operational statistics](https://www.goindigo.in/information/investor-relations/operational-statistics/domestic.html) publish dated carrier-wide passenger/RPK/ASK/load-factor tables. Their published load-factor definition is based on passenger-kilometres divided by available seat-kilometres, so it must not be presented as a count of unoccupied seats on a particular flight.
- [IndianOil petroleum-product prices](https://iocl.com/prices-of-petroleum-products) and [domestic ATF history](https://iocl.com/atf-domestic-airlines) supply dated fuel tables. Product sections have separate dates; footer updates or an LPG date cannot refresh the ATF date.
- [FRED Brent](https://fred.stlouisfed.org/series/DCOILBRENTEU) and [FRED USD/INR](https://fred.stlouisfed.org/series/DEXINUS) provide dated numerical context. They supply no route fare, coupon, passenger or fare-family history.

No verified free longitudinal Indian route-fare dataset was adopted in this audit. Travel-date cross-sections, broad carrier statistics and today's price graph snapshots are not interchangeable with timestamped observations for the exact directed fare cohort. Public Google guidance remains separately attributed external context, with no imported local certainty percentage.

## Accuracy and readiness that can honestly be reported

The live fare forecast remains **Not calibrated**. The source snapshot cannot measure live model MAE, directional accuracy or the truth of a purchase prediction: no cohort has even a second observation day, much less independent seven-day outcomes.

The retained model is a simple median-slope trend of listed fares. It is intentionally understandable and locally free. A chronological persistence baseline and minimum 10% MAE improvement remain required; checkout totals cannot train it. Seven nonoverlapping weekly outcomes after 21 distinct training observation days are required to publish a projection; at least 20 outcomes plus a passed gate are required for a historical directional-accuracy percentage and Wilson interval. That percentage is not a causal fuel/news probability or a guarantee for this journey.

Readiness reports actual missing training days/outcomes and conditional evidence milestones. With one valid observation today and successful same-cohort daily collection, the earliest seven-window evidence milestone needs roughly 69 further daily collections; 20 windows need roughly 160. Missing/invalid observations, provider changes, accuracy failures or departure before the milestone can prevent qualification. The program withholds projections reaching or passing departure. These calendar calculations contain no fabricated prices.

Provider coverage changes still withhold the aggregate cohort forecast. A separately calibrated fixed-provider model is a future option; it was not silently adopted or used to erase past evidence. More primary macro data cannot solve this route-fare cold start. Existing authorized Red Room requests continue real collection while the local backend/computer remains running.

## Validation

Focused validation runs use `backend/tools/run_isolated_tests.py`, protecting the live database, profiles and old research artifacts. The reasoning suite covers target/deadline conflicts, declining-series rule precedence, unsupported causal vetoes, false disruption words, malformed context, calendar-year overclaiming, future coupon crawl times, carrier context separation, synchronized verdict fields, preference/quality leakage and malformed stored evidence.

Final focused validation passed **65 tests**, with 279 unrelated tests deselected, in the disposable copy. Its log is `logs/brain-reasoning-audit.log`. The root task performs the full backend suite and frontend checks after all agents' edits are complete. No test pass is presented as successful live fare prediction or provider payment verification.

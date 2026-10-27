# Free alternatives for provider access and forecast cold starts

This follow-up implements useful alternatives to two independent limitations: unreliable OTA navigation and insufficient longitudinal fare history. It does not certify unattended MakeMyTrip/Cleartrip payment access, all-site coverage or forecast accuracy.

## Implemented in the active app

Each current result now has **Google price guidance & booking options**. The fast search path remains unchanged. This optional request opens an isolated public Google browser, rechecks the requested dated one-way adult/cabin search, uniquely matches the real itinerary, selects it and validates the selected directed airports, day, airline, schedule, stops and group-price scope before reading guidance. A Google rerender can remove the temporary card marker, so the reader reparses and rematches once rather than clicking an arbitrary replacement card.

The response separates Google's low/typical/high comparison and usual range for similar trips from actual named partner offers. Explicit convenience fees remain attached to their partner offer. Missing fee information remains unknown. Nothing is promoted to a verified payable total or inserted into fare history/calibration. Results retain provenance, timestamp, exact scope and a limitation message. Missing/changed/unsupported evidence returns an unavailable or partial result without guessing. The selected itinerary can be opened in the retained browser for the user to choose an actual merchant Continue control.

The endpoint is `search:booking-context:get`, returning `search:booking-context`. It accepts active search/result identity, not a supplied URL or pasted HTML. Work is bounded to 75 seconds and existing browser concurrency. One guidance request runs at a time, at most two guidance sessions are retained, and sessions expire under the existing 15-minute rule. Quarantined results are rejected even if guidance was previously cached. Failure/cancellation closes owned resources. Guidance-only sessions cannot enter merchant checkout verification.

This supplements current comparisons with a free source of historical context while local calibration is immature. It also supplies legitimate additional merchant handoffs where Google actually offers them. No signed partner URL is invented and no challenge, login, payment or access restriction is bypassed. Google's page is an external comparison source, not a historical fare database we can quietly import.

The brain also reports **forecast readiness**: distinct accepted observation days, initial training days remaining, measured non-overlapping weekly outcomes, remaining forecast/certainty outcomes, coverage/freshness/performance blockers, and conditional evidence milestones. Counts alone cannot qualify a model. A cold start with one observation day would require at least 69 further successful comparable daily collections to reach seven weekly holdout outcomes, and 160 to reach twenty, under the stated assumptions. Sparse collection may take longer; invalid projections or coverage changes can prevent qualification. The model must still beat the last-price baseline by at least 10%. These are evidence requirements, not promised prediction dates.

Readiness flags milestones reaching/passing departure. A projected seven-day price whose target reaches/passes departure is withheld, along with its certainty percentage. Fresh target-price and booking-deadline advice remains available. Red Room already persists trip requests and collects real observations while the backend runs; repeated scans today cannot create independent weeks of outcomes.

## Investigated alternative: ordinary-browser companion

The separate [browser-companion prototype](browser-companion/README.md) uses Chrome MV3 `activeTab` and `scripting` permissions after an explicit user gesture. It reads the browser the user navigates, without copying cookies/profiles or requiring an automation-created session. It has no persistent host access, network transport, backend integration, automatic coupon clicks or purchases. It previews only bounded canonical checkout evidence and omits personal fields/form values, card digits and URL queries. Unknown layouts and gateway frames remain unverified. Every output forbids final-price promotion and learning.

This is an experimental proof of concept. Seventeen fixture tests pass, but actual toolbar permissions and real payment-page layouts have not been validated. It is not enabled in the active app. Production integration needs actual supported layout evidence plus expiring trip-bound pairing, authenticated local transport and separate manual-evidence trust handling. An ordinary browser may avoid automation-session differences; it cannot force access or establish unseen gateway/issuer charges. Local SQLite is retained: paying for a database or changing browser libraries would not fix these evidence gaps.

## Real public probes

All observations below were read during 8–9 October 2026 local time; prices can change. No passenger or payment details were filled and no purchase occurred.

| Trip | Evidence observed | Result |
|---|---|---|
| DEL–GOI, 16 Dec 2026, one adult, nonstop | Air India Express 18:35–21:15; Google comparison ₹14,745, typical range ₹7,800–21,000; airline partner ₹14,994 explicitly including ₹249 convenience fee | New strict reader succeeded |
| BOM–HYD, 18 Nov 2026 | Air India 21:30, ₹6,693; typical range ₹4,200–6,700; Air India, FlightsMojo, Wego, Travomint controls | Actual Continue reached Air India's matching booking landing; review/payment not established |
| DEL–MAA, 16 Feb 2027 | Air India 08:45, ₹10,520; high comparison, range ₹6,300–7,700; same named partners | Readable Google options; no MMT/Cleartrip control offered |
| GOI–HYD, 14 Nov 2026, via BLR | IndiGo 07:10–11:35, ₹5,881 including ₹98 convenience fee; only IndiGo offered | Actual Continue reached matching airline search, then “No flights found”; payment not established |
| BOM–HYD, 19 Nov 2026, one adult, nonstop | App search 10.42s: Google 7 / EMT 12 / CT 1 rows; two corroborated quotes. Google guidance ₹6,693 typical ₹4,200–6,700 | WebSocket guidance and window handoff succeeded; verification correctly rejected guidance-only session |
| PNQ–HYD, 19 Feb 2027, two adults, nonstop | App search 11.42s: Google 1 / EMT 7 / CT 0; no corroborated quote. Google group guidance ₹13,826 high ₹8,700–11,000 | Exact two-adult scope and handoff succeeded; CT failure explicit, no invented prediction |

The first app probes exposed another layout variation: partner buttons with no fee annotation omit the period after “Indian rupees.” The parser now accepts both observed forms, retains unknown fees as unknown, and has a regression test. It also waits for a visible partner control before accepting an empty offer list. The original app probes' empty lists are retained in diagnostics as partial results, not rewritten as if the repaired reader had run then. Further UI validation exercises the repaired reader.

Diagnostics are in ignored `sessions/new-approaches/`; reproducible public tools are `backend/tools/probe_google_guidance.py`, `probe_google_partners.py` and `validate_google_context.py`. The latter creates normal app searches, so its accepted real observations follow the normal integrity gate.

## Research basis and tradeoffs

- [Google Flights help](https://support.google.com/travel/answer/7664728?hl=en) describes partner booking options and price comparisons for similar trips; its future advice remains uncertain and coverage is not universal. We use these descriptions as external context, with no invented probability or generic US booking-day rule applied to India.
- [Google price tracking](https://support.google.com/travel/answer/6235879?hl=en) is a free user-controlled supplementary option; no Google account or subscription was created. Local Red Room remains the app's collector.
- [Chrome activeTab](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab) and [scripting](https://developer.chrome.com/docs/extensions/reference/api/scripting) support temporary, user-invoked ordinary-tab inspection. This avoids broad persistent permissions but does not support unattended access or automatic payment-frame proof.
- [Chrome extension network requests](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests) explains the transport/permission boundary; the prototype deliberately has no network transport yet.

Cross-sectional “India flight price” datasets do not supply repeated point-in-time observations of our exact directed trip. They are not imported as longitudinal training history. Fuel, FX, airport traffic and news remain sourced context rather than fabricated fare outcomes.

## Validation and remaining limits

The latest complete disposable backend suite passes **249 tests** with one existing legacy XGBoost serialization warning. Frontend production build/TypeScript and lint pass. Tests cover trip reversal/date/adult/cabin/schedule/stops changes, invalid ranges/currency, optional fee label variants, explicit zero versus unknown fee, guidance cache/quarantine/expiry/cancellation, no quote/learning mutation, readiness/coverage/sparse history, departure guards and companion privacy boundaries. Fixtures remain outside live history.

MMT/Cleartrip final-payment coverage remains unproven. No universal scraper or browser replacement can establish charges the merchant has not yet displayed. The active app therefore offers verified comparisons where possible, explicit partial results, optional Google context and real merchant handoffs; it withholds unsupported final totals and forecast certainty.

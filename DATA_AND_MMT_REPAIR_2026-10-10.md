# Source audit and MakeMyTrip navigation repair, 10 October 2026

This report distinguishes implemented safeguards, observed public website behavior and experiments. Indian domestic flights remain the supported market. No paid service, passenger identity, card entry or purchase was used. Raw source pages and screenshots were held in memory; ignored audit files contain derived evidence and local database backups.

## Concept audit

| Concept | What is actually usable | Main limit or needed evidence |
| --- | --- | --- |
| Multi-site listing search | Google, EaseMyTrip and Cleartrip yielded current listings on some tested Indian trips; failed sites show a reason and exact manual link. | Coverage is partial and site dependent. Group-fare basis and missing prices are withheld. MakeMyTrip remains unreliable even after login repair. |
| Cheapest price ranking | Exact route, full date, adults, cabin, time/stops and source agreement are checked. Suspicious or contradictory rows are quarantined; listed and checkout amounts stay separate. | A ranked listed fare is not the final amount payable. Different fare families, baggage and seat inventory can still make two listings incomparable. |
| Coupon discovery | Public merchant/GrabOn advertisements and codes visible on the selected merchant page are collected with source and terms. | No free method proves all current offers across every merchant/account/app. Collection success does not prove eligibility or saving. |
| Coupon application | Eligible codes are tried serially against one cart; payable-total changes, newly shown terms, removal and best-code reapplication are checked and recorded. | Existing trials are at review or failed stage; zero accepted trial currently proves final selected-payment coverage across every merchant. Site sign-in, payment and coupon UI can block testing. |
| Checkout fees | A payment total can be labelled verified only when selected itinerary, adult count, cabin, method and stable total remain readable. Reopening a cart withdraws its former claim. | Merchant payment screens were not reached reliably on MakeMyTrip/Cleartrip; later issuer/gateway charges remain unknown. |
| Timing brain | Exact directed history, current eligible quotes, dated context, nearby options and explicit targets generate explanations. Withheld data cannot train it. | No exact-trip longitudinal holdouts or measured route response to fuel/news. Numerical certainty and speculative future discounts remain unavailable. |
| Red Room alerts | Saved requests run on a live local backend with leases, failure state, deduplication and cancellation. | Machine sleep/offline periods prevent checks. It cannot guarantee observing the eventual cheapest moment or buy automatically. |
| Alternate dates/airports/self-transfer | Fresh comparison searches and a user-entered ground-cost estimate can suggest tradeoffs. | Unknown terminals, cab fares, baggage, separate-ticket protection and live inventory remain explicitly unverified. |
| Learning/source storage | SQLite separates accepted fare outcomes from market context; source receipts and backups preserve provenance. | Macro/carrier/airport series are not route fare labels. A few repeated same-day fares cannot calibrate a future-price model. |
| User interface and failure states | Failed asynchronous operations now clear pending controls; the dashboard uses active evidence and marks unknown accuracy. | External website failures still require manual review and may change without warning. |

## Login navigation finding

Normal searches call `MakeMyTripWorker.input_search_criteria()` with a direct search URL. The older homepage `navigate_to_search()` contained an Escape/close-button attempt but was not called by that path. Consequently that attempt did not protect the actual search from a login dialog. The user's report of a login overlay is consistent with this code-path defect.

Fresh isolated browser checks separately returned HTTP/2 connection errors, a six-character access response, or a network-problem page before flight selection. These observations do not prove that the user's login overlay is the only cause, or that bot detection is responsible. Neither scenario establishes booking/payment access.

The active direct-search worker now observes the optional dialog after navigation and again while waiting for listings. It closes one identified login X normally, verifies that the dialog disappeared, and reports `LOGIN_BLOCKED` if the dialog cannot be closed. It reports a bounded search timeout or the provider's network error separately. Local regression fixtures passed, but fresh isolated Chromium probes did not display the login dialog; live success after dismissal remains unproven. Homepage airport/date navigation remains diagnostic: it checks exact IATA selection and full redirected criteria, but has not proved more reliable than a direct search.

## Review of real starter data

The primary-source recheck on 9 October compared the following saved data with fresh source responses or independently read source tables:

| Source | Checked observations | Result and scope |
| --- | ---: | --- |
| [FRED Brent](https://fred.stlouisfed.org/series/DCOILBRENTEU) | 951 | All saved values matched the fresh CSV. USD/barrel crude proxy, not Indian ATF. |
| [FRED USD/INR](https://fred.stlouisfed.org/series/DEXINUS) | 940 | All saved values matched the fresh CSV. INR per USD. |
| [AAI traffic reports](https://www.aai.aero/en/business-opportunities/aai-traffic-news) | 136 | Eight PDF hashes matched; the existing strict parser reproduced all saved rows. This is source/stored consistency verification, not an independent transcription of every PDF. Airport domestic movements are not directed-route demand. |
| [IndianOil ATF](https://iocl.com/atf-domestic-airlines) and [historical tables](https://iocl.com/prices-of-petroleum-products) | 100 | Independently compared dates, cities and values. Latest observation remains 1 April 2026; a newer website footer is not a newer fuel price. INR/kilolitre. |
| [IndiGo domestic operational statistics](https://www.goindigo.in/information/investor-relations/operational-statistics/domestic.html) | 96 existing, 37 additional | Existing values matched. Imported 37 additional valid published monthly rows, now 133. Latest month remains July 2026. Carrier-wide passengers/RPK/ASK/load factor cannot establish route fares or seat inventory. |

Incomplete and blank reporting months were omitted. Passenger counts, fiscal-year dates, positive RPK/ASK and load-factor arithmetic were checked. Automatic HTTP retrieval of the carrier/ATF source had failed; the reviewed import preserves those failures and does not claim a successful automatic refresh. News remains linked context: one EIA article was independently checked, not every headline or alleged causal effect on Indian ticket prices.

## Evidence defects repaired

One retained Google/Fli DEL–CCU record for 23 November 2026 identified QP-1260 as Akasa Air in its summary but used the known erroneous Air Kenya Aviation label in its segment. The price was not rewritten to make it agree. The record was flagged, its original search result quarantined, and its sole EaseMyTrip peer lost corroborated status. Database backups and original derived records were preserved before these scoped changes.

`segment_evidence.py` now checks present segment endpoints, full local dates/times, connections, stop count, duration, cabin and nonstop flight identity before a row can corroborate another source, enter fare history or reach advice. The specific corrupt QP label is rejected. Marketing and operating carrier names are not blindly equated, since codeshares can legitimately differ. Missing connection evidence remains uncorroborated; contradictory evidence is flagged.

`source_document_metadata()` hashes the exact received source document, attaches the parsed date range/count and distinguishes HTTP fetching from reviewed imports. `merge_source_documents()` preserves bounded per-document receipts across incremental refreshes and revisions. A hash of a recent CSV is no longer implied to cover the entire merged historical series. Unknown old coverage stays explicitly unknown. Existing AAI report hashes and failed-source state remain available.

The post-repair export at 14:59 UTC contained 132 accepted fares across 14 exact route/date/adult/cabin cohorts. After fresh live searches, the 15:34 UTC export contains 134 accepted fares. Thirteen earlier cohorts had one observation day and GOI–HYD for 15 December had two; repeated observations within a day do not create independent outcomes. The two new accepted fares are another route/date cohort, not a longitudinal accuracy test. Counts change with further live searches. Synthetic legacy records remain excluded. Calibration still lacks comparable ticket-price outcomes over time; fuel, traffic and carrier context do not replace those labels. The active brain correctly withholds a percentage and future-price forecast.

## Alternative MakeMyTrip source experiment

The merchant's [public MCP endpoint](https://www.makemytrip.com/ai/mcp?src=cm) answered ordinary unauthenticated read-only protocol calls in isolated tests. `backend/mmt_source.py` validates exact directed airports/full date, one adult, Economy, one-way nonstops, positive prices and the merchant widget's INR/per-adult display. Bodies, timeouts and supported schemas are bounded. Merchant session/booking IDs are discarded; handoff uses a canonical public search URL.

| Isolated request | Supported references | First displayed amount |
| --- | ---: | ---: |
| AMD–IXC, 17 November 2026 | 2 nonstops | ₹6,719 |
| IXC–AMD, 17 February 2027 | 1 nonstop | ₹7,602 |
| GOI–HYD, 19 November 2026 | 4 nonstops | ₹5,054 |

The merchant warns that this inventory may be cached. Quote age, final convenience/payment fees, complete inventory and coupon eligibility are unavailable. There is no identified permanent free third-party API contract. [Myra service terms](https://www.makemytrip.com/legal/mya/terms-conditions.html) concern a named chatbot service; applicability to MCP is unspecified. Observed access is not described as permanent authorization or a price guarantee.

**This adapter remains an isolated experiment, not the normal-search replacement.** The user requested adoption only where better; unknown freshness cannot replace live exact evidence. Defense-in-depth guards prevent these references from voting for a live quote, entering history or driving advice even if a caller incorrectly assigns accepted status. Optional UI metadata distinguishes retrieval time from observation time if such references are exposed in a future explicit integration.

## Fresh whole-app defects and repairs

- Opening a new booking now withdraws an old checkout claim before browser navigation. The newly observed listing is saved before the fallible selection click. If either step fails, the old coupon and payment amount cannot remain the current price. Expired browser sessions trigger a fresh handoff attempt instead of a stale success notification.
- Flight selection rereads the present result cards and requires one exact matching itinerary; a previous card-position selector cannot silently select a reordered flight. Provider failure metadata now accepts only the provider's exact host or its subdomain, and listener ownership is bounded to live page/context objects.
- A cancelled search propagates cancellation to Red Room/watchlist callers while still saving and emitting its cancelled state. Red Room monitor creation validates without adding a phantom unfinished search. Malformed/naive stored monitor and watch timestamps no longer stop subsequent scheduled checks; monitor leases release after a failed initial list update.
- Frontend requests now clear pending search, coupon, advice and exploration states when the corresponding server reply fails or the socket disconnects. A coupon is shown as saved only after the server acknowledges it. Late result updates do not force a tab switch; refreshed history updates the selected record. The search form validates round-trip return dates.
- The dashboard reads active provider-run and scoped coupon-trial ledgers. It no longer presents unused research-cycle counts, a made-up 0% forecast error, or a website-wide coupon success rate as operational facts. Its forecast display says “Not calibrated” until the exact-trip evidence gate supports measured performance.

The browser search still cannot guarantee access to all merchants. The actual LKO–PNQ 21 November search returned Google 3, EaseMyTrip 12 and Cleartrip 1 listing; MakeMyTrip returned zero and timed out after 33 seconds. A reverse PNQ–LKO 21 February two-adult nonstop search returned two uncorroborated EaseMyTrip listings. Google’s monetary cards were connecting flights and failed the nonstop request; a visible nonstop card lacked a readable price. Cleartrip's two cards did not establish whether the displayed amount was per adult or the group total, so the app withheld them. This is an evidence gap; no amount was multiplied without a clear basis.

## Validation and remaining limits

An added read-only runtime script checks the running app's platform, history, watch, Red Room, notification, scoped coupon and directed-route history contracts plus an explicit invalid-advice error. All eleven checks passed against the restarted backend. Targeted browser/recovery tests passed, as did the final frontend production build and lint. The disposable full backend suite passed **607 tests** in 180.84 seconds. Its one warning concerns an older serialized XGBoost model outside the live booking decision path.

Local dialog fixtures are regression tests, not evidence of live merchant access. No final-payment success or exhaustive coupon coverage is claimed. Existing real coupon trials establish only their recorded review-stage outcomes and restrictions. Cleartrip itinerary creation, unknown later gateway charges and insufficient forecasting outcomes remain independent limitations.

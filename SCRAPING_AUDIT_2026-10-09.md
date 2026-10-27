# Public scraping audit — 9 October 2026

This audit covers Indian domestic listing prices, Google/Fli normalization, and parser efficiency. It used public searches without passenger details, purchases, challenge bypass, or database writes. These are observed listing fares; they do not establish the final amount at a merchant's payment page. The architecture and broader integration are explained in [PROJECT_GUIDE.md](PROJECT_GUIDE.md).

## Confirmed problems and implemented repairs

**EaseMyTrip could display valid flights while the program returned none.** Some current fares use a visible `spnPrice<number>` element without a `price` attribute, alongside a hidden duplicate with that attribute. Business-class fares exposed this problem. The parser now accepts the visible numbered element, rejects hidden duplicates, and excludes `spnPriceLock<number>` deposits. A broad prefix would otherwise confuse a ₹1,001 price-lock deposit with the ₹20,003 fare. Regression fixtures preserve that exact distinction.

**A stricter visibility check introduced during this audit also rejected painted fares inside zero-size parents.** Floated children and `display: contents` can be visible even when their parent has no rectangle. The corrected check requires painted bounds on the card and price themselves, while ancestors are checked for CSS hiding rather than size. This correction was verified on the live GOX–HYD page as well as a fixture. Hidden or zero-opacity old fares remain excluded.

**Hidden markup could incorrectly prove that a fare was a group total.** Group-total evidence now comes from visible card text. Unsupported or conflicting units remain rejected. Per-person multiplication is checked again for finite, positive output, preventing overflow from becoming a quote. Two-adult searches retain the displayed total rather than doubling it again.

**Identity and schedule checks had gaps.** Known Fli segment cabins must match the requested cabin; domestic offset-bearing timestamps must use Indian Standard Time; known leg and layover durations must match the actual timeline. These augment the existing directed route, full date, airport, currency, and domestic connection checks. Unknown cabin information is still unknown. Displayed quote duration is checked against clocks, with supported overnight/24-hour handling. Duplicate flight-number spellings are normalized, contradictory stop labels are rejected, and minute-only durations are accepted. Layover parsing now matches individual layover lines instead of accidentally treating the route origin after a duration as a connection airport.

**Google date proof and provider links could be misleading.** The Google worker now requires the requested full date in its departing-date tracking text; an unrelated date elsewhere on the page cannot establish the active search. Google itself never qualifies as a merchant checkout. An unknown provider's URL adapter raises an explicit error instead of quietly linking to Google. The parent integration guards the four supported adapters.

## Fresh public observations

Prices below were observed on 9 October and can change. Counts are supported parsed rows before user preference filtering, not complete market inventory. The timed three-case run is in [the detailed log](logs/scraping-audit-2026-10-09-final.log). The Business repair was subsequently confirmed in [a separate live log](logs/scraping-business-confirmation.log).

| Search | Fli public page | Google DOM | EaseMyTrip |
|---|---|---|---|
| PNQ → JAI, 18 Nov 2026, one adult, Economy | 3 validated rows from 5 returned; ₹10,276; 1.77 s | 3 parsed rows from 5 candidate cards; ₹10,276; 3.98 s | 35 parsed rows; ₹10,009; 8.59 s |
| BBI → HYD, 20 Feb 2027, two adults, Economy | No validated priced rows; 1.38 s | No priced rows; 3.67 s. Eight visible schedules said “Price unavailable.” | 51 parsed rows; ₹16,080 total for two adults; 8.65 s |
| ATQ → DEL, 23 Feb 2027, one adult, Business | 7 validated rows; ₹20,004; 1.36 s | 7 parsed rows; ₹20,004; 3.50 s | Initially zero despite visible fares. After the final repair: 21 parsed/validated rows; AI-492 at 13:45–14:55, ₹20,003. Post-repair timing was not separately measured. |

Browser timings include launch, navigation, readiness, parsing, a deliberate one-second recheck, and cleanup. Fli timings include the separate reader process. This is a small sample, not a universal benchmark. The first and second parsed counts were unchanged in the timed searches; that does not prove later pagination or lazy loading is complete.

The navigation audit independently rechecked **GOX → HYD, 21 Feb 2027** after the visibility repair: 80 parsed rows from 82 visible candidate cards, six matching nonstop flights, and IndiGo 6E-6973 at ₹7,188. Search took 8.67 seconds. Its public evidence is in [the navigation artifact](sessions/navigation-audit-20261009/easemytrip-GOX-HYD-2027-02-21.json). Review and coupon evidence belongs to that audit; it does not establish a final payment total.

The machine-readable [three-case report](sessions/scraping-audit-2026-10-09/report.json) preserves an intermediate run, including failures before the final deposit guard. It must not be presented as an all-green final run. The targeted Business log and navigation recheck document the final live confirmations.

## Coverage and efficiency

Successful rows now carry `source_inventory.complete=false`. DOM metadata contains `scope=visible_dom_cards`, `candidate_cards`, `parsed_rows`, and `rejected_cards`. Fli metadata contains `scope=google_public_page`, `returned_rows`, `normalized_rows`, and `rejected_rows`. Each includes a limitation message. These counts expose rejected or partial inventory; they do not imply that missing flights do not exist. With zero rows, source failure/unavailability reporting remains necessary because no row can carry that metadata.

The optional Fli reader remains pinned to revision `881aee5ff4321e81ea2157cb44be94ce6a21dc1b`. Its current transport reads a public Google page; it is not a comprehensive Google booking API. Upstream documents partial results and missing booking-option, baggage, emissions, and multicity support. Premium/child searches can also be sparse. These limits explain why it remains an optional source with browser comparison rather than replacing the working app. See the [upstream README](https://github.com/punitarani/fli/blob/881aee5ff4321e81ea2157cb44be94ce6a21dc1b/README.md).

The reader retains a killable 20-second outer bound, an 8-second upstream timeout, and a 500-row input limit. DOM extraction performs one bounded browser evaluation, with ancestor checks bounded by card depth. In the measured searches, parsing took roughly 0.01–0.11 seconds; provider readiness, browser launch, and navigation dominate. Further blind retries would add traffic and latency without establishing correctness. No paid service or new repository was adopted.

Remaining limits are explicit: unsupported layouts, pagination, mixed/unknown cabins, fare families, bags, terminals, and merchant fees need their own evidence. Connecting DOM cards without complete segment identity cannot prove a protected connection or a safe self-transfer. A listed minimum across observed sources cannot establish the cheapest ticket across every travel website. Final convenience/payment fees and coupon eligibility require merchant checkout proof; these parser changes do not substitute for it.

## Validation and files

The final focused disposable suite passed **101 tests**, with 243 other tests deselected, in **24.63 seconds**. Command: `backend/.venv/Scripts/python.exe backend/tools/run_isolated_tests.py -k 'scraping or listing_parser or fare_validation or fli'`. Evidence: [final test log](logs/scraping-followup-final-tests.log). Root performs the full integration suite separately.

Implemented changes are in `backend/workers/listing_parser.py`, `backend/workers/google_flights_worker.py`, `backend/google_source.py`, and `backend/quotes.py`. New fixtures are in `backend/tests/test_scraping_followup.py`. The repeatable, bounded, database-free public probe is `backend/tools/audit_public_scraping.py`. No public observations from this audit were inserted into prediction history.

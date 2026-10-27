# Navigation and coupon audit — 9 October 2026

This audit covers Indian domestic public searches, merchant review screens, coupon trials and browser handoff. It used the project's browser factory and actual published controls. No traveller or payment details were entered, no ticket was purchased, no access challenge was bypassed, and no live database was changed. Prices below are observations, not durable offers.

## Repairs

- **Keep merchant tabs alive after Google handoff.** `backend/session_manager.py` previously closed the complete browser context when its original tab closed. A merchant opened by a Google Continue control could therefore disappear when the user closed Google. Sessions now track all context tabs, follow a remaining tab when the active one closes, and clean up when the last tab closes. Closing an unrelated secondary tab preserves the original session.
- **Compare expiry deadlines as UTC instants.** Both status checks and periodic cleanup normalize timezone-aware deadlines; Indian UTC+05:30 deadlines no longer gain or lose several hours.
- **Reject partial or malformed checkout amounts.** `backend/workers/base_worker.py` and the native EaseMyTrip total reader validate the complete numeric token, Indian/Western digit grouping, finite amounts and at most two decimal places. Examples rejected include `₹1e5`, `₹1,000,00`, `₹5,350.505`, `₹1 000`, `₹5350 + taxes`, and per-adult amounts. A valid amount followed by a separate `1 Adult` line remains readable. An unreadable fee is no longer emitted as an observed null/zero fee.
- **Keep required product combinations conditional.** A real EaseMyTrip offer advertised a flight booking plus Acko insurance combo. `backend/offer_rules.py` now treats explicit required add-ons/combinations as unknown until their eligibility is confirmed. A plain optional-insurance mention does not restrict a flight coupon. The program does not purchase or silently select insurance to unlock such a coupon.
- **Validate native EaseMyTrip coupon input.** Its dedicated field implementation now enforces the same coupon-code format check as the generic worker before filling any field.

The shared scraper audit fixed an additional regression found during these probes: a visibility guard incorrectly rejected visibly painted price children whose float/container ancestor had zero layout bounds. Before the repair GOX–HYD returned zero rows despite real cards; the repeated same-route public probe below extracted the fares and reached review. That repair belongs to `backend/listing_parser.py`, not this navigation worker.

## Public evidence and efficiency

All cases used one adult, Economy, one way, exact requested airports and nonstop results. Search timings include browser launch and listing extraction; total timings also include review/coupon work where performed. Different routes and page responses prevent treating these timings as a controlled benchmark.

| Provider / route / departure | Observed result | Search / full elapsed |
| --- | --- | --- |
| EaseMyTrip GOX–HYD, 21 February 2027 | Six matching nonstops. Lowest IndiGo 6E-6973, 14:20–15:40, ₹7,188. Same flight reached public review. | 8.67 s / 25.39 s including two coupon trials and restoration |
| Cleartrip GOX–HYD, 21 February 2027 | Five matching nonstops. Same 6E-6973 listed ₹7,188. Actual booking selection returned HTTP 403 on `/itin/v7/itinerary/create` and `/flight/fetch-interstitial-page`, followed by a server-error screen. No review total was obtained. | 5.23 s / 12.14 s |
| MakeMyTrip IXC–CCU, 27 November 2026 | Empty public page; worker reported unavailable rather than inventing a fare. | 5.83 s full elapsed |
| EaseMyTrip IXC–CCU, 27 November 2026 | No supported matching nonstop result before the scraper guard repair. Connecting cards were present; this probe does not establish complete nonstop availability. | 13.69 s / 13.72 s |

The repaired GOX–HYD EaseMyTrip extraction parsed 80 of 82 candidate visible cards and explicitly reported partial inventory. Nearby Sindhudurg/GOI alternatives and connecting flights were not promoted into exact GOX nonstop results.

### Actual EaseMyTrip coupon trial

The review screen exposed 27 distinct native offer candidates, including bank/EMI/UPI/wallet conditions. The bounded public trial attempted two candidates with no payment method selected:

| Code | Provider feedback and visible review total |
| --- | --- |
| BOOKNOW | Accepted; ₹7,188 decreased to ₹6,968, an observed ₹220 review-stage saving. |
| EMTSECURE | Not accepted; total remained ₹7,188. Its insurance-combo wording exposed the eligibility flaw now repaired above. |

The audit removed each coupon between trials and restored the coupon-free ₹7,188 total afterward. The review showed ₹4,750 airfare plus ₹2,438 taxes. It had no selected payment method and no readable payment-stage convenience-fee breakdown. **₹6,968 is an observed coupon-adjusted review amount, not a verified final payable price.** Later gateway/convenience charges remain unknown until the actual selected payment screen is accessible and checked. The 27 candidates were scraped; they were not all applied, and bank eligibility was not assumed.

Detailed observed DOM/HTTP diagnostics, screenshots and HTML are in ignored `sessions/navigation-audit-20261009/`. The GOX–HYD `-before.json`/`-before.html` preserve the zero-row regression; the ordinary filenames hold the repaired public review trial. The reproducible bounded tool is `backend/tools/probe_navigation_20261009.py`; it does not import the live database.

## Verification

- `backend/tests/test_session_navigation_20261009.py`: **20 passing** isolated cases cover real Playwright tab events, timezone deadlines, malformed/valid totals, unknown fees, required versus optional insurance eligibility, and native input refusal. These are local fixtures, not live payment proof.
- Navigation, verified-pricing and offer-rule regression snapshot: **69 passing**, followed by the final 20-case run after the native input guard was added.
- An earlier full disposable snapshot returned 290 passing / 3 failures in older forecast/storage fixtures while another agent was updating scoped evidence requirements. That agent corrected those fixtures; the parent runs the final shared full suite after all agents finish. This report does not claim that earlier snapshot was green.
- Logs: `logs/navigation-session-20261009-final.log`, `logs/navigation-session-20261009-complete.log`, `logs/navigation-live-gox-hyd-postfix-20261009.log`, `logs/navigation-live-cleartrip-20261009.log`, and `logs/navigation-live-mmt-20261009.log`.

## Remaining limits

Cleartrip's HTTP 403 and MakeMyTrip's empty page remain provider-side public navigation blocks. Selector changes do not establish that those booking flows work. Google partner controls can offer a legitimate handoff, but availability of a partner listing does not prove its merchant cart, coupons or final fee-inclusive price. The root-owned Google booking helper now rejects explicit selected-year mismatches identified during this audit.

Payment totals, terminal transfer costs and coupons with unavailable account/payment/add-on conditions must remain unverified. No fixture should be presented as proof of a real gateway transaction. The search must continue to disclose partial source coverage rather than claim it checked every travel website or every published coupon. See `PROJECT_GUIDE.md` for the integrated architecture and final shared validation.

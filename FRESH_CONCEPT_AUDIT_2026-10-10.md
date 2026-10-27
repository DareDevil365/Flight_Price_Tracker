# Fresh concept and code audit — 10 October 2026

This follow-up examines the active Indian domestic application after the earlier repair round. Three separate reviewers checked pricing/checkout, the brain/alerts, and frontend request lifecycles. Findings were reproduced with temporary databases, local pages or actual React rendering before repair. This is a bounded audit, not a guarantee that every defect or merchant layout has been found.

## Newly reproduced defects and repairs

| Problem | Repair and reason |
| --- | --- |
| First checkout verification was inaccessible: its button required an already verified receipt. | Offer verification when a supported booking session has opened successfully. Receipt freshness remains a separate condition. |
| Expired booking IDs bypassed the backend's preparation recovery. | Merchant Open booking always uses `session:prepare`, which reuses a live cart or prepares a fresh one. |
| A stored payment receipt could be selected as a current eligible price by history prediction. | History prediction reports archived receipts without treating them as live carts. The active brain/advisor require a callback tied to the actual session and pending cart. |
| Stored checkout evidence lost its payment/add-on/fee conditions. | Preserve selected payment facts, cart options, fee scope/breakdown and coupon coverage with the receipt. These are separate from listed market history. |
| A budget removed raw listings before coupons could be tested. | Retain above-budget listings with an annotation. A higher listing may become affordable after an eligible coupon; no discount is assumed. |
| A departure-deadline rule could ignore the search budget. | Use the financial maximum as the target when no explicit separate target is supplied; over-budget candidates stay MONITOR. |
| Round-trip timing could approve the request from outbound fares alone. | Explicitly report outbound-only evidence and withhold a whole-trip buy/wait verdict and return-inclusive budget approval. Separate-leg listed comparisons remain available. |
| Generic checkout identity omitted airline/arrival/stops and accepted morning `08:30` from `08:30 PM`. | Require airline, explicit nonstop, both times, date, route and number; normalize AM/PM. Connecting bookings and published fare/baggage entitlements require a provider-specific selected-summary reader and are withheld by the generic reader. |
| Global page text could confirm the original flight from a recommendation while another flight was selected. | Require one visible, bounded semantic selected-itinerary region; exclude recommendations and reject missing/duplicate scopes, conflicting flight IDs, dates, stops or clocks. A next-day arrival requires an overnight schedule. Unsupported merchant layouts stay unverified. |
| “Don't have HDFC” became HDFC ownership; mixed sentences could exclude every bank. | Share a small deterministic financial grammar with clause-local ownership/exclusion. Recognized card products remain distinct from all cards at that bank. Unsupported instruction fragments fail explicitly. |
| New restrictions did not reach an already prepared cart; changes could race ongoing coupon trials. | Synchronize pending cart rules with feedback, and reject changes during a running trial before mutating either task. |
| Receipt eligibility was rechecked without its actual payment selection. | Evaluate its coupon against the recorded selected method/bank and reject explicitly excluded cards or methods. |
| Invalid time preferences and malformed financial settings could silently change behavior. | Validate enums, booleans, lists, budgets and concurrency before database access. Empty optional flight numbers remain valid. |
| NLP changed unsupported 12-adult/infant/multi-city requests into a simpler trip. | Reject these cases; use the full Indian airport reference and recognize explicit supported stop counts. The editable form still exposes the parsed request. |
| Native `Use Code` headings were missed due to case sensitivity. | Parse explicitly labelled headings case-insensitively; exclude visually hidden offer cards. Advertised codes remain unverified candidates. |
| Refreshing a coupon did not update its discount cap. | Update `max_discount` in the database conflict path. Actual savings still require payable-total trials. |
| SQLite's UTC date could suppress newly started Indian offers after midnight IST. | Use the Indian booking date for active offer start/expiry filtering. UTC observation timestamps remain unchanged. |
| A same-price deal returning after MONITOR was permanently suppressed by alert deduplication. | Deduplicate within a decision episode; a returning actionable deal can alert again. |
| Alternative searches each created their own semaphore, exceeding their intended concurrency. | Share one two-worker semaphore across all planned alternative routes. Acquire a search's local limit before the global browser slot to avoid occupying capacity while waiting locally. |
| The frontend accepted only 32 hardcoded airports. | Read the backend's sourced Indian airport JSON directly, avoiding a second manually maintained list. Airport membership does not guarantee service. |
| Coupon refresh could remain pending after failure or disconnection, including on another tab. | Reset state in the global WebSocket handler and mounted result controls. |
| Old checkout prices retained preferential ranking and stale badges without new messages. | Prioritize current receipts, label historical totals/savings as recorded, and refresh freshness checks every 30 seconds. |
| Enter/image-drop paths could submit overlapping extractions or an old image read after retry. | Guard both handlers synchronously and discard superseded FileReader callbacks. |
| Selected payment labels could store masked account/card identifiers or merge different payment selections. | Persist only recognized method, bank, card product and EMI/BNPL facts; reject conflicting selected labels instead of inventing a multi-bank card. |

## Concepts retained and limits

The active flow remains React/Zustand → local WebSocket server → validated task → bounded Playwright/Fli workers → itinerary/price gates → SQLite facts → deterministic advice and local monitoring. Playwright supports rendered page navigation and short-lived DOM inspection; SQLite makes evidence and failures inspectable without a hosted bill. No paid dependency, new hosted database or lower-model price inference was introduced. The optional Gemini path assists form extraction; it cannot establish a fare, coupon saving or calibration percentage.

A listed fare, a review-page coupon reduction and a merchant payment total are distinct evidence. A final merchant amount cannot prove a later issuer/gateway charge. The new semantic itinerary reader requires an identifiable selected summary, rather than collecting matching tokens anywhere on the page; local regression pages do not establish that each provider's actual payment layout supplies this evidence. Generic connecting/fare-entitlement verification is deliberately unavailable until that evidence exists. Merchant final-payment and exhaustive coupon coverage remain unproven.

Inventory is partial: four current adapters, at most twelve cheapest valid rows per source/leg, with unsupported/manual sites outside automated coverage. Thus “cheapest among usable observed options” is supportable; “cheapest possible across every site/coupon/account” is not. Hidden app-only/account offers, pagination, fare-family differences and incomplete baggage/terminal evidence remain gaps.

The source-audited fuel/FX/airport/carrier series remain context. They cannot substitute for independently observed exact-trip fare outcomes, establish a causal war/fuel coefficient or justify a certainty percentage. Forecast calibration still needs longitudinal, comparable, independently checked outcomes. Current actual price comparisons, explicit targets and deadline caveats remain usable while confidence says Not calibrated.

Red Room runs while the local backend is awake. It cannot observe prices while the computer is asleep or guarantee that its sampling catches a transient minimum. It never buys automatically. Nearby airports/separate tickets disclose uncertain ground costs, baggage, terminals and missed-connection protection.

## Validation

Backend checks use `backend/.venv/Scripts/python.exe backend/tools/run_isolated_tests.py`, which copies the project into a temporary workspace to protect the live database/profiles/models. New audit regressions cover checkout identity, inputs, financial grammar, history/live-cart separation, budgets, round trips, alert episodes and concurrency. Frontend checks use the installed React/TypeScript without a new dependency:

```
node frontend/tools/audit_checkout_ui.cjs
node frontend/tools/audit_request_ui.cjs
```

The final isolated backend suite passed **669 tests in 168.20 seconds**. One legacy XGBoost pickle-version warning remains in the retained research-model test; this does not establish forecast calibration. The frontend's 22 rendering/action/lifecycle checks, production build and lint passed. Eleven read-only runtime contracts passed again after restarting the backend with the final changes.

Fresh COK–BLR, 26–29 November 2026 round trip returned 18 Google, 24 EaseMyTrip, 12 Cleartrip and zero MakeMyTrip rows in 23.47 seconds; 43 rows were corroborated, 11 uncorroborated. The brain returned MONITOR with `OUTBOUND_ONLY_ROUND_TRIP`. The lowest outbound accepted listing was INR 4,230; the overall lowest row was a separate return leg, so it is not described as the round-trip price. CCU–BBI, 24 February 2027, two adults/nonstop returned four uncorroborated EaseMyTrip listings in 12.70 seconds and no readable matching listings from the other three sources. The app withheld a cheapest-accepted claim rather than inventing agreement or a group-price basis. These live cases validate listing/error behavior, not the new payment-summary reader on actual merchant checkouts.

No passenger/payment details were entered and no purchase was made. Only derived search/audit records were retained; no raw merchant page dump was created.

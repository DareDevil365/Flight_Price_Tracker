# Flight Finder — Technical Bug Fixes & Maximum Savings Upgrade

This plan addresses several critical bugs causing ₹0 flights, incorrect coupon application (face-value matching), bot detection failures on booking sites, and non-functional AI Vision/NLP inputs. It transforms the system into a reliable, robust flight booking assistant.

---

## Background & Diagnosis

After analyzing the codebase, logs, and database, here is the diagnosis of the core issues:

### 1. The ₹0 Flight and Cleartrip Base Price Bug
- **Root Cause 1 (DFS Key Traversal Bug)**: Cleartrip, MMT, and EMT workers intercept JSON responses and use a depth-first search (DFS) traversal helper `find_value_by_keys` to look for keys like `price`, `amount`, or `value`. However, this traverses sub-dictionaries in depth-first order without checking higher-priority keys at the sibling level first. For example, if a dictionary has `"taxDetails": {"amount": 549}` and `"fareDetails": {"basePrice": 5400}`, it matches `"amount": 549` first because `taxDetails` appears first in `items()`.
- **Root Cause 2 (Low Price Floor)**: The minimum price floor in workers is set to `500.0`. Convenience fees/taxes (like ₹549) pass this check and are treated as the base price of the flight.
- **Root Cause 3 (Coupon DB Pollution)**: When `CouponInstinctsEngine` corrects a coupon discount, it updates the `discount_value` of the coupon in the database. But if the base price was incorrectly parsed as ₹549 and a coupon gave a discount of ₹549 (capped), it overwrote the coupon's general value (e.g. ₹5,000) with the capped ₹549. This corrupted the coupon for all future flights.
- **Root Cause 4 (No Price Clamping)**: In `dispatcher.py` (real path), `f_final = f_base - f_savings` is not clamped, letting the checkout price go to 0 or negative.

### 2. Website Navigation Failures (Anti-Bot Blocks)
- **Root Cause 1**: The browser is launched with `--disable-http2`. Disabling HTTP/2 makes Playwright instances look highly suspicious to CDNs (like Akamai on MMT).
- **Root Cause 2**: Outdated user agents (Chrome 123-126) trigger bot indicators.
- **Root Cause 3**: `HumanSimulator` is never imported or used in the scraper navigation pipeline.

### 3. Non-Functional AI Vision & NLP
- **Vision Intake**: `VisionIntake.extract_trip_details` is a stub that always returns mock DEL→BOM flight data.
- **Conversational NLP Search**: The frontend uses a static `setTimeout` mock to auto-populate "DEL → GOI on next Friday", and the backend has no NLP endpoint.

---

## Proposed Changes

### Component 1: Core Navigation & Anti-Bot Stealth [MODIFY]

#### [MODIFY] [browser_factory.py](file:///c:/Users/yasha/Desktop/Flight%20Finder/backend/stealth/browser_factory.py)
- Remove `--disable-http2` from the `launch_args` list to match real user HTTP/2 negotiation signatures.

#### [MODIFY] [fingerprint.py](file:///c:/Users/yasha/Desktop/Flight%20Finder/backend/stealth/fingerprint.py)
- Update `USER_AGENTS` list to include modern Chrome user agent strings (Chrome 130-134).

---

### Component 2: JSON Key Traversal & Price Parsing [MODIFY]

#### [MODIFY] [cleartrip_worker.py](file:///c:/Users/yasha/Desktop/Flight%20Finder/backend/workers/cleartrip_worker.py)
#### [MODIFY] [makemytrip_worker.py](file:///c:/Users/yasha/Desktop/Flight%20Finder/backend/workers/makemytrip_worker.py)
#### [MODIFY] [easemytrip_worker.py](file:///c:/Users/yasha/Desktop/Flight%20Finder/backend/workers/easemytrip_worker.py)
- Rewrite `find_value_by_keys(self, d, keys, default=None)` to search for keys *in priority order globally* instead of doing deep DFS. It will check the entire dictionary for key[0], then key[1], etc., using a recursive helper.
- Update `parse_single_flight(self, d)`: Increase price threshold from `500` to `1200` to prevent convenience fees/taxes from being parsed as flight base prices.
- Update `_parse_via_dom`: Increase price check filters to ignore any price under `1200` for domestic flights.

---

### Component 3: Coupon Verification & Clamping [MODIFY]

#### [MODIFY] [dispatcher.py](file:///c:/Users/yasha/Desktop/Flight%20Finder/backend/dispatcher.py)
- Clamp `f_final` to be at least `1200.0` (or `max(1200.0, f_base - f_savings)`) for domestic flights, or `max(1.0, f_base - f_savings)` as an absolute minimum to prevent ₹0 checkout prices.
- Filter coupons by airline: if the coupon description contains a specific airline name (e.g. "IndiGo"), verify it matches `f["airline"]`.

#### [MODIFY] [coupon_instincts.py](file:///c:/Users/yasha/Desktop/Flight%20Finder/backend/coupon_instincts.py)
- Update `analyze_coupon_with_ai` prompt to return BOTH `applicable_discount_value` (flight-specific capped savings) and `general_*` parameters (`general_discount_type`, `general_discount_value`, `general_max_discount`, `general_min_booking_value`).
- In `audit_and_correct`, save only the **general** coupon parameters to the database (so we don't overwrite the global discount value with a flight-specific capped value).
- If the AI call fails (rate limits), log a warning and return the calculated discount (fallback to original calculations) rather than zeroing it out to `0.0`.

---

### Component 4: Real Conversational NLP Search [MODIFY]

#### [MODIFY] [text_ai.py](file:///c:/Users/yasha/Desktop/Flight%20Finder/backend/text_ai.py)
- Implement `parse_trip_nlp(self, query_text: str)`: Use Gemini to extract trip parameters (`origin`, `destination`, `departureDate`, `cabinClass`, `passengerCount`) as a JSON payload, using the current date `2026-06-21` to resolve relative dates like "next Friday".

#### [MODIFY] [main.py](file:///c:/Users/yasha/Desktop/Flight%20Finder/backend/main.py)
- Add WebSocket handler for `search:nlp_parse`.
- Call `text_ai.parse_trip_nlp` and send back `search:nlp_parsed` event containing the structured results.

#### [MODIFY] [SearchCockpit.tsx](file:///c:/Users/yasha/Desktop/Flight%20Finder/frontend/src/components/SearchCockpit.tsx)
- Rewrite `handleNlpSearch` to send the query text to the backend via WebSocket: `sendMessage("search:nlp_parse", { text: nlpQuery })` instead of using the local mock.

#### [MODIFY] [useWebSocket.ts](file:///c:/Users/yasha/Desktop/Flight%20Finder/frontend/src/hooks/useWebSocket.ts)
- Add handler for `search:nlp_parsed`: update the trip store with parsed inputs, add success logs to the bot console, and stop the spinner.

---

### Component 5: AI Vision Intake Integration [MODIFY]

#### [MODIFY] [vision_intake.py](file:///c:/Users/yasha/Desktop/Flight%20Finder/backend/vision_intake.py)
- Implement `extract_trip_details(self, image_b64: str)`: Query Gemini-2.5-flash with the base64 screenshot. Ask it to extract origin/destination city/codes, departure/return dates, passenger counts, and cabin class as JSON. Parse it and return it to `main.py`.

---

### Component 6: AI Worker Bugfixes [MODIFY]

#### [MODIFY] [ai_worker.py](file:///c:/Users/yasha/Desktop/Flight%20Finder/backend/workers/ai_worker.py)
- Line 294: Fix the double-escaped f-string typo in Javascript regex: change `\\d{{2}}` to `\\d{2}`.
- Remove the fallback mock flight returning fake ₹5,400 flight data when parsing fails (raise a `ValueError` instead to trigger resilience retries).

---

### Component 7: Self-Learning Database Schema & Retrying (Additive) [NEW]

- Create new SQL tables (`coupon_test_results`, `coupon_learnings`, `pipeline_metrics`, `process_journal`, `airport_alternatives`) in `schema.sql`.
- Add `SelfLearningEngine` in `learning_engine.py` to calculate coupon success rates and pipeline errors.
- Implement adaptive retry strategies (CAPTCHA, TIMEOUT, NETWORK) in `dispatcher.py`.

---

## Verification Plan

### Automated Tests
- Run backend pytest:
```bash
cd backend && .\venv\Scripts\python.exe -m pytest tests/ -v
```

### Manual Verification
1. **DFS Bug Verification**:
   - Query Cleartrip / MakeMyTrip.
   - Verify the parsed base prices are correct (e.g. ₹4,000–₹8,000) and no longer ₹549.
2. **Coupon Clamping & Database Pollution**:
   - Apply coupon `CTUPI`.
   - Verify the checkout price is correctly calculated and does not go to ₹0.
   - Verify the `coupons` table is not polluted with flight-specific capped values.
3. **Conversational Search (NLP)**:
   - Type "Fly from Delhi to Bangalore on next Tuesday" in the NLP input.
   - Verify the origin, destination, and departure date fields are parsed by Gemini and auto-populated.
4. **AI Vision (Itinerary Screenshot)**:
   - Upload a flight itinerary screenshot.
   - Verify the vision model extracts the correct origin, destination, and date.

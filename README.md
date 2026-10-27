# Flight Finder & Savings Optimizer

A local domestic Indian flight comparison app with real listings, user-assisted checkout verification, coupon testing and saved price watches. **Listed fares are separate from verified final payable totals.** Future cashback and card points do not reduce the amount due.

Read [PROJECT_GUIDE.md](PROJECT_GUIDE.md) for the architecture and [FIXES_AND_LIMITATIONS.md](FIXES_AND_LIMITATIONS.md) for the review and remaining work.

Latest audit and repairs: [10 October fresh concept and code findings](FRESH_CONCEPT_AUDIT_2026-10-10.md), following the [source/navigation audit](DATA_AND_MMT_REPAIR_2026-10-10.md). The latest repairs cover first checkout verification, expired sessions, financial exclusions, budgets, round-trip advice, coupons, alerts and request failures. Forecast calibration and final-payment coverage remain incomplete.

## Start on Windows

Use Python 3.12 or 3.13, Node.js/npm and internet access. Playwright Chromium is installed by setup.

```powershell
# Once; specify a supported Python if the default differs.
./setup.ps1 -Python 'C:\path\to\python.exe'
# Start using the installed backend/.venv environment.
./start.ps1
```

Open http://127.0.0.1:5173. Backend health: http://127.0.0.1:8765/health. Logs: logs/. This checkout already has the prepared backend/.venv environment. The older backend/venv is not used.

Manual startup in separate terminals:

```powershell
cd backend
./.venv/Scripts/python.exe main.py
```

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Avoid backend --reload on Windows so Playwright subprocesses work. No synthetic seeding or AI key is required for normal searches. Optional text/image AI intake uses configured external services when invoked.

## Find and verify a price

1. Choose exact airports/date, adults, cabin, departure time/stops and providers. No card ownership is required before searching.
2. Compare listed fares. Google Flights, EaseMyTrip and Cleartrip returned live listings in current checks. MakeMyTrip can currently fail; other saved websites are manual links.
3. Select **Open booking**. Continue on the provider page with passenger details and intended payment method; keep the selected itinerary visible.
4. Click **Verify total & coupons**. The app reads payable total, tests eligible discovered or supplied codes, restores the best successful code and updates only that flight. Platform/payment charges remain included. Reverify after changing fare, baggage or payment.
5. Use **Can’t use a deal?** on Results to enter “I don't have HDFC”, “exclude Flipkart Axis”, “only UPI”, “no EMI” or “no BNPL”. It excludes those deals and compares remaining options across sites. Conditional offers stay conditional until verified. Settings can save your exclusions for later.

The app does not buy tickets or guarantee the best final price from every website. Sessions expire after fifteen minutes. Round trips are separate one-way bookings. MakeMyTrip can return blocked/empty pages. Cleartrip's itinerary-creation request returned HTTP 403 in Chromium and Edge during testing. Provider failures have manual search links; an opened booking browser is retained for assisted recovery. Neither an error page nor booking review establishes a final payment total. A verified total covers the merchant's displayed payable amount for the selected payment method; later gateway/issuer charges are not confirmed.

**Explore dates, airports & separate tickets** performs additional live searches. GOI/GOX comparisons subtract your ground-transfer estimate; separate tickets require conservative connection buffers and disclose unknown terminals/extra fees. Nonstop-only searches skip self-transfer options.

**Red Room** saves a future trip, adult/cabin/time/stops preferences, exclusions, target budget and check interval. It checks prices/offers/context while the backend runs, saves advice/alerts and avoids duplicate unchanged recommendations. Optional Windows login startup:

```powershell
./Enable-RedRoom.ps1
# Remove login startup later:
./Enable-RedRoom.ps1 -Disable
```

The startup task is enabled in this checkout. Monitoring pauses when your computer is off/asleep. Saved alerts are authoritative; Windows notification display depends on system settings. A GOI–HYD, 15 December 2026 validation watch is present and can be removed in Red Room.

## History and timing advice

Use **Google price guidance & booking options** on a current result to check Google's low/typical/high comparison for similar trips, named merchant offers and any explicitly displayed convenience fee. **Open selected Google itinerary** opens that exact selection for merchant handoff. These are external guidance and listed offers; missing fees stay unknown, and they do not alter our model certainty or become verified checkout totals. Failed reads leave your comparison unchanged. See [the access/cold-start follow-up](ACCESS_AND_COLD_START_2026-10-09.md) for actual probes and limits.

**What our forecast still needs** shows accepted training days, completed weekly outcomes and coverage/accuracy/departure blockers. Conditional collection dates are evidence milestones, not promised predictions. Predictions reaching/passing departure are withheld. Red Room collects real history while the backend runs; repeated scans in one day cannot accelerate independent outcome validation.

History separates accepted listed fares and verified checkout totals for the same directed route, flight date, adults, cabin and time/stops preferences. Reverse routes stay separate. Suspicious prices are quarantined before learning; connecting flights need matching segment evidence. Older observations remain stored but are excluded from the active brain until they satisfy the current evidence contract. Losing a cheaper provider does not count as a market price rise.

The brain gathers global FRED crude-oil/FX context, Indian ATF history, AAI airport passenger reports, primary EIA/PIB feeds and separately labelled reported news. Dated stale feeds remain visibly stale. Airport movements are not directed route demand, and a headline cannot establish a future fare hike. Forecasts require chronological testing against last-price persistence; a certainty percentage requires enough independent weekly outcomes and stable provider coverage. Current real fare data covers one observation day, so it says **Not calibrated**. No multi-year fare trends or unannounced anniversary discounts are assumed. Retained synthetic ML/RAG experiments are inactive in booking decisions.

Refresh initial free evidence from the project root with `backend/.venv/Scripts/python.exe backend/tools/bootstrap_brain_data.py`. It backs up SQLite, fetches validated feeds and advertised coupons, and exports dated provenance under ignored `sessions/source-bootstrap/`. A failed source keeps its dated prior evidence and reports the failure. Advertised coupons still require actual eligibility and checkout testing.

Only the tested public Google listing reader from [Fli](https://github.com/punitarani/fli) was adopted as an optional source. Playwright handles browser fallback and booking. Stop-constrained searches use the browser because the isolated Fli constraint experiment did not return validated priced rows. Install is pinned in backend/requirements-google.txt and attempted by setup; failure leaves the browser path available.

## Validate changes

```powershell
cd backend
./.venv/Scripts/python.exe tools/run_isolated_tests.py
./.venv/Scripts/python.exe tools/probe_live.py google_flights easemytrip cleartrip
```

Public probes never supply passenger/payment data. For full legacy model tests install requirements-research.txt. The isolated runner copies the project to a disposable location so old tests cannot mutate your profiles/models. Fixtures stay outside the live database. Server-level isolated runs can set FLIGHT_FINDER_DB and FLIGHT_FINDER_CONFIG_DIR to temporary locations.

See [AUDIT_AND_DATA_2026-10-09.md](AUDIT_AND_DATA_2026-10-09.md) for the latest three-agent audits, implemented fixes, real initial data, 344 passing backend tests and fresh one/four-month searches. [AGENT_AUDIT_2026-10-08.md](AGENT_AUDIT_2026-10-08.md) and [REPAIR_VALIDATION_2026-10-08.md](REPAIR_VALIDATION_2026-10-08.md) cover preceding repairs; [VALIDATION_REPORT.md](VALIDATION_REPORT.md) retains the earlier baseline and Fli benchmark. Export accepted evidence with backend/.venv/Scripts/python.exe backend/tools/export_brain_dataset.py from the root; the manifest under sessions/brain-data records actual counts and excluded candidate reasons. The latest bootstrap export is under sessions/source-bootstrap/brain-data. Isolated servers may also set FLIGHT_FINDER_PORT (default 8765); validate_live_routes.py accepts --url ws://127.0.0.1:8766/ws.

```powershell
cd frontend
npm run build
npm run lint
```

Do not commit local settings, databases, logs, credentials, passenger or payment data.

Coupon trial history is available in Results Ranker → Published coupons & bank offers → Coupon track record. Select the website in Coupon website and refresh after testing. Each run keeps its directed trip, conditions, observed saving and review/payment status; a failed or review-only run never certifies final fees. See [the latest inspection and coupon report](PAGE_INSPECTION_AND_COUPONS_2026-10-09.md).


Latest follow-up: [Honey/browser/forecast research and repairs](RESEARCH_AND_REPAIRS_2026-10-09.md) — 446 isolated backend tests plus build/lint; public EMT offer feeds, original-cart protection, fresh verification status, forecast continuity gates, real EMT coupon trial and ordinary-browser Cleartrip review success. The companion remains read-only/unintegrated; final payment fees and calibrated forecasts remain unproven. Published candidates are expandable and the website selector is above them; completed verification automatically refreshes the ledger.

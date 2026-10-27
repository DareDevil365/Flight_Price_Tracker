# Forecast research and collection continuity repair — 9 October 2026

The active brain needs trustworthy repeated observations of the same directed Indian domestic route, travel date, adults, cabin and preferences. More macroeconomic rows or a different forecasting library cannot substitute for those observations. Existing accepted history and cached source data were preserved; this work did not backfill fares or change the live database.

## Concrete defects repaired

`backend/intelligence.py` previously allowed a fresh last quote to satisfy its freshness check even when the successful validation windows were old. The last fourteen training points could also bridge a long monitoring interruption. Historical accuracy could consequently reappear as though it described current collection.

Forecast-only training and validation now restart after the most recent collection gap longer than the seven-day forecast horizon. The original accepted observations remain available for descriptive comparisons. Readiness reports the restart date, older days excluded and remaining observations for the resumed cohort. A separate freshness gate withholds the model if its latest completed seven-day validation outcome is over fourteen days old, even if recent sparse quotes have no long gap. Readiness then reports a pending future outcome rather than suggesting that existing outcome counts enable a forecast immediately.

The seven/fourteen-day limits are explicit conservative product policies, not parameters learned from Indian fares or thresholds prescribed by the cited research. They can withhold a useful model; the preferred failure is an honest current comparison with no unsupported future price. These changes do not prove that a recent model will remain accurate.

The certainty explanation also makes the independence assumption of its Wilson interval explicit. Non-overlapping weekly outcomes can still be serially dependent; the interval can be too narrow. This meter describes measured historical direction accuracy, not a probability that a headline will raise this trip's fare.

## Primary research and practical decisions

- [Hyndman and Athanasopoulos: rolling-origin time-series evaluation](https://otexts.com/fpp3/tscv.html): training must precede the actual forecast target; evaluate the horizon the product uses. The existing chronological seven-day/persistence comparison remains appropriate. Monitoring interruptions and stale validation need additional operational gates, implemented above.
- [The same authors: point forecast accuracy](https://otexts.com/fpp3/accuracy.html): training fit is insufficient; held-out observations and simple comparison methods matter. Retained the last-price baseline and withheld predictions rather than fitting the retained legacy synthetic dataset.
- [StatsForecast repository](https://github.com/Nixtla/statsforecast) and [its cross-validation tutorial](https://nixtlaverse.nixtla.io/statsforecast/docs/tutorials/crossvalidation.html): a potential later source of statistical challengers and rolling validation. It does not supply Indian route fares. No new runtime dependency or paid TimeGPT service was adopted; there is no representative local history on which to establish an improvement. Its [license is Apache 2.0](https://github.com/Nixtla/statsforecast/blob/main/LICENSE).
- [River ADWIN documentation](https://riverml.xyz/dev/api/drift/ADWIN/): adaptive drift detection is a possible later diagnostic for observed prediction errors. A detector on raw flight prices could confuse normal booking-horizon movement with a problem, and the current data cannot validate it. No untested drift alarm or confidence adjustment was introduced.

## Primary data rechecked

- [FRED Brent, DCOILBRENTEU](https://fred.stlouisfed.org/series/DCOILBRENTEU): page's latest actual observation is 6 October 2026, USD 125.44/barrel, published 7 October. This is global crude context, not Indian ATF or route fare causation.
- [FRED USD/INR, DEXINUS](https://fred.stlouisfed.org/series/DEXINUS): latest actual observation is 2 October 2026, INR 96.3100/USD, updated 5 October. Publication and observation dates remain different.
- [IndianOil aviation fuel](https://www.iocl.com/aviation-fuel): domestic metro block still explicitly says 1 April 2026: Delhi 104927, Kolkata 109450, Mumbai 98247 and Chennai 109873 INR/kilolitre. An October site footer does not refresh these observations. Existing stale labelling is correct; no new current ATF data was claimed.
- [IndiGo official domestic operational statistics](https://www.goindigo.in/information/investor-relations/operational-statistics/domestic.html): current FY 2026–27 table still contains April through July. Published carrier-wide passenger-kilometres and seat-kilometres are capacity/utilisation context, never directed-route demand, remaining bookable seats or fare-history labels.
- [Google's price-tracking documentation](https://support.google.com/travel/answer/6235879?hl=en): independently useful consumer price alerts and externally supplied guidance remain distinct from this app's model. No external low/high price label becomes a local training outcome or numerical certainty.

The currently collected source observations were already present. No genuinely newer source rows were found to justify duplicating imports. Failed feeds must keep their own failure status, and stale cached primary data must retain its actual date.

## Validation

Six new adversarial tests in `backend/tests/test_forecast_collection_gaps.py` cover a fresh quote after a long gap, protection against borrowing old percentage certainty, independence of resumed forecasts from old prices, multiple interruptions without mutating stored history, exact weekly collection, and stale outcome accuracy despite recent sparse quotes. Test fare values are isolated timeline fixtures and are never inserted into the application's evidence database.

Targeted isolated command: `backend/.venv/Scripts/python.exe backend/tools/run_isolated_tests.py -k 'forecast or prediction_audit or chronological_holdout'` — **35 passed**, 368 deselected in the final targeted run. Python compilation passed. The parent integration run must supply the final full-suite/build result; these targeted checks do not establish live prediction accuracy.

## Remaining limits

The accepted real exact-trip histories still span one observation day. No calibrated future fare or certainty percentage is available from them. A chronological collection period cannot be replaced by importing today's alternate travel dates, reversing a route, using an airport passenger total, applying a fuel coefficient without validation, or forecasting an unannounced coupon. Current accepted fares, actually tested coupons, cheaper real alternatives, target-price monitoring and labelled external guidance remain the useful cold-start outputs.

---
name: forecast-dataset-refresher
description: "Use when gathering market feeds or compiling the live brain dataset."
---

# Live forecast evidence

Do not trust existing CSVs, models, wiki claims or seed data as real observations. The previous pipeline mixed research/synthetic data; it is excluded from the live app.

MarketContext in backend/intelligence.py retrieves dated FRED Brent and USD/INR series (initially from 2023, then incremental), EIA/PIB primary news and separately labelled reported headlines. backend/evidence_feeds.py also validates discovered AAI passenger PDFs and IOCL metro ATF tables. Failed feeds retain dated cached data and expose failure status. News is context, never proof of route-level price causation.

The product searches domestic Indian fares; global oil/currency/disruption context is still relevant. The Indian airport country reference in backend/data/indian_airports.json is sourced, not proof of current bookable service. AAI arrivals-plus-departures must never be described as directed route demand, available seats or unique travellers. Keep monthly and same-month prior-year columns separate from cumulative/international tables. ATF units are INR/kilolitre, not INR/litre; stale source rows do not become current because the footer or import date changed.

Bootstrap with backend/tools/bootstrap_brain_data.py; it backs up SQLite, collects eight discovered AAI reports, refreshes free feeds/offers and exports a provenance manifest under ignored sessions/source-bootstrap. An optional --atf-text accepts an explicitly reviewed dated primary-page table; record its transport and actual observation dates, and retain a failed HTTP/challenge status. Never present imported historical rows as successful current scraping.

Prices enter live history only after backend/quote_integrity.py corroborates the exact directed route/date/adults/cabin/itinerary, or checkout verification succeeds. Connecting flights need matching segment evidence. Time/stops preferences filter the series. Uncorroborated and flagged quotes cannot train the brain. Reverse routes do not share observations. Fli and the Google browser worker are the same website, never two independent corroborators.

Export accepted live data with backend/.venv/Scripts/python.exe backend/tools/export_brain_dataset.py from the root. Output is ignored sessions/brain-data; do not overwrite legacy CSVs or model files. Source URLs, observation dates, offer snapshots and feed statuses are included.

Forecast only listed market fares; payment/add-on dependent checkout totals are not a comparable training series. The active trend gate requires at least seven nonoverlapping weekly holdouts after twenty training days, fresh data and MAE at least 10% better than last-price persistence. Percent certainty requires at least twenty independent weekly outcomes, a passed holdout gate and a displayed interval. Until sufficient data exists, show not calibrated. Never seed observations to bypass this gate. Multi-year seasonality and future anniversary coupons require dated real evidence.

Forecast-only cohorts restart after the most recent collection gap longer than seven days; older accepted observations remain descriptive history. Completed validation outcomes older than fourteen days cannot support a current prediction just because a fresh quote arrived. These are conservative product policies, not learned thresholds. Readiness must show the resumed cohort and actual future outcome dates. Nonoverlapping outcomes can still be correlated; a Wilson interval does not guarantee independent fare changes.

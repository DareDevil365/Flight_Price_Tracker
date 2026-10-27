---
name: db-seeder-manager
description: "Use when initializing or validating the local database."
---

# Database integrity

Initialize the additive schema with CouponDB.initialize(); the default database is backend/db/flight_agent.db. Tests must use temporary database paths and FLIGHT_FINDER_CONFIG_DIR. Never run seed_history.py or seed_coupons.py against live user data. Their hardcoded/sample observations are research fixtures, not current fares or published offers.

Live evidence lives in fare_quotes with quality_status, live_offer_evidence, offer_observations, intelligence_cache and knowledge_sources. Legacy rows remain preserved but excluded from active learning. Quarantined quotes live in quote_quarantine and cannot train models. Red Room requests/alerts are persistent.

Validate with the pytest suites using backend/.venv/Scripts/python.exe; inspect source/date/route/count/cabin and quality fields. Before any cleanup, identify exact owned test IDs, back them up, and avoid changing user records or saved preferences.

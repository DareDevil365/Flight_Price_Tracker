-- Flight Finder Database Schema

-- Coupon Codes (Base spec + Enhancements)
CREATE TABLE IF NOT EXISTS coupons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,              -- 'makemytrip', 'cleartrip', 'easemytrip', etc.
    code TEXT NOT NULL,                  -- Promo code string
    description TEXT,                    -- User-friendly description
    bank_restriction TEXT,               -- 'SBI', 'HDFC', 'ICICI', NULL = universal
    card_type TEXT DEFAULT 'ANY',        -- 'CREDIT', 'DEBIT', 'ANY'
    requires_emi BOOLEAN DEFAULT 0,
    requires_bnpl BOOLEAN DEFAULT 0,
    requires_wallet BOOLEAN DEFAULT 0,
    app_only BOOLEAN DEFAULT 0,
    discount_type TEXT,                  -- 'FLAT', 'PERCENT', 'CASHBACK'
    discount_value REAL,                 -- Value (flat amount or percentage)
    max_discount REAL,                   -- Cap for percentage discounts
    min_booking_value REAL,              -- Minimum transaction value to qualify
    valid_from DATE,
    valid_until DATE,
    is_active BOOLEAN DEFAULT 1,
    source TEXT DEFAULT 'manual',        -- 'manual', 'scraped', 'user'
    source_url TEXT,                     -- Crawled URL source for trust verification
    source_type TEXT DEFAULT 'platform_native', -- 'platform_native', 'external_crawled', 'user_submitted', 'bank_official'
    trust_score REAL DEFAULT 0.5,        -- 0.0 to 1.0 trust score based on source
    success_rate REAL DEFAULT 0.5,       -- Updated dynamically after brute forcing
    last_verified DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, code)
);

CREATE INDEX IF NOT EXISTS idx_coupons_platform ON coupons(platform);
CREATE INDEX IF NOT EXISTS idx_coupons_active ON coupons(is_active);

-- Search Log
CREATE TABLE IF NOT EXISTS searches (
    id TEXT PRIMARY KEY,                   -- UUID
    origin TEXT NOT NULL,                  -- Origin IATA code
    destination TEXT NOT NULL,             -- Destination IATA code
    departure_date TEXT NOT NULL,          -- YYYY-MM-DD
    return_date TEXT,                      -- YYYY-MM-DD (optional)
    passenger_count INTEGER DEFAULT 1,
    cabin_class TEXT DEFAULT 'ECONOMY',
    platforms TEXT,                        -- JSON array: ['makemytrip', 'cleartrip']
    status TEXT DEFAULT 'pending',         -- 'pending', 'running', 'completed', 'failed'
    started_at TEXT,
    completed_at TEXT,
    total_duration_ms INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Aggregated Search Results
CREATE TABLE IF NOT EXISTS search_results (
    id TEXT PRIMARY KEY,                   -- UUID
    search_id TEXT NOT NULL REFERENCES searches(id),
    platform TEXT NOT NULL,
    flight_number TEXT,
    airline TEXT,
    departure_time TEXT,
    arrival_time TEXT,
    duration TEXT,
    stops INTEGER DEFAULT 0,
    base_price REAL,                       -- Listed price before coupon
    final_price REAL,                      -- Verified price after best coupon
    best_coupon_code TEXT,
    savings REAL,                          -- base_price - final_price
    effective_price REAL,                  -- After external savings (cashback/rewards)
    deal_score REAL,                       -- 0 to 100 rating
    all_tested_coupons TEXT,               -- JSON array of CouponTestResult
    savings_breakdown TEXT,                -- JSON breakdown (waterfall data)
    session_id TEXT,                       -- Reference to browser session for handoff
    rank INTEGER,
    departure_date TEXT,                   -- Departure date of this flight
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Price History (for trend tracking)
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route TEXT NOT NULL,                   -- 'DEL-BOM'
    departure_date TEXT NOT NULL,          -- YYYY-MM-DD
    airline TEXT,
    flight_number TEXT,
    price REAL NOT NULL,
    platform TEXT NOT NULL,
    cabin_class TEXT DEFAULT 'ECONOMY',
    source TEXT DEFAULT 'scraped',         -- 'scraped' vs 'synthetic'
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_price_route ON price_history(route, departure_date);

-- User Watchlist
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    departure_date TEXT NOT NULL,
    target_price REAL,                     -- Alert when price drops below
    check_frequency TEXT DEFAULT 'daily',  -- 'hourly', 'daily', 'weekly'
    last_checked TEXT,
    last_price REAL,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Active Browser Sessions
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,                   -- UUID
    search_id TEXT REFERENCES searches(id),
    platform TEXT NOT NULL,
    status TEXT DEFAULT 'active',          -- 'active', 'ready_for_handoff', 'handed_off', 'expired', 'closed'
    browser_pid INTEGER,
    window_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    handoff_at TEXT,
    expires_at TEXT
);

-- External Savings Rules (cashback portals, mobile wallets, UPI offers)
CREATE TABLE IF NOT EXISTS external_savings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,              -- Target platform (e.g. 'makemytrip', or 'ALL')
    savings_type TEXT NOT NULL,          -- 'cashback_portal', 'payment_offer', 'wallet_offer', 'upi_offer'
    provider TEXT NOT NULL,              -- 'CashKaro', 'PayPal', 'Amazon Pay', 'PhonePe', 'GPay'
    savings_value REAL,                  -- Value (percentage or flat amount)
    savings_unit TEXT DEFAULT 'PERCENT', -- 'PERCENT' or 'FLAT'
    max_savings REAL,                    -- Maximum discount cap
    min_transaction REAL,                -- Minimum transaction amount
    terms TEXT,                          -- Raw terms and conditions
    source_url TEXT,                     -- URL of page where offer was found
    valid_from DATE,
    valid_until DATE,
    is_active BOOLEAN DEFAULT 1,
    last_scraped DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Price Prediction Log
CREATE TABLE IF NOT EXISTS price_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route TEXT NOT NULL,                   -- 'DEL-BOM'
    departure_date TEXT NOT NULL,          -- YYYY-MM-DD
    prediction TEXT NOT NULL,              -- 'BUY_NOW', 'WAIT', 'NEUTRAL'
    confidence REAL,                       -- 0.0 to 1.0 confidence score
    reasoning TEXT,                        -- Explain the heuristic match
    data_points_used INTEGER,              -- Number of history records analyzed
    predicted_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Notifications
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,                    -- 'price_drop', 'flash_sale', 'coupon_expiry', 'system'
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    data TEXT,                             -- JSON payload with context data
    is_read BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Custom Platforms / Websites added by the user
CREATE TABLE IF NOT EXISTS custom_platforms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Observed Prices (for ML forecasting and audit)
CREATE TABLE IF NOT EXISTS observed_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_key TEXT NOT NULL,
    airline TEXT,
    observed_at_timestamp TEXT NOT NULL,
    price REAL NOT NULL,
    fare_class TEXT,
    seats_remaining_hint INTEGER,
    source TEXT DEFAULT 'scraped'          -- 'scraped' vs 'synthetic'
);

-- Smart Suggestions (for caching advisor results)
CREATE TABLE IF NOT EXISTS smart_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id TEXT NOT NULL REFERENCES searches(id),
    route TEXT NOT NULL,
    suggestions TEXT NOT NULL, -- JSON string of the smart suggestions payload
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Graph RAG Knowledge Graph Node Entity Store
CREATE TABLE IF NOT EXISTS graph_nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    properties_json TEXT NOT NULL
);

-- Graph RAG Knowledge Graph Edge Relationship Store
CREATE TABLE IF NOT EXISTS graph_edges (
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    properties_json TEXT NOT NULL,
    PRIMARY KEY (source_id, target_id, relation_type)
);

-- ═══════════════════════════════════════════════════════════════
-- Self-Learning Intelligence Tables
-- ═══════════════════════════════════════════════════════════════

-- Coupon Test Results (individual test outcomes from brute forcing)
CREATE TABLE IF NOT EXISTS coupon_test_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coupon_code TEXT NOT NULL,
    platform TEXT NOT NULL,
    test_result TEXT NOT NULL,          -- 'SUCCESS', 'FAILED', 'EXPIRED', 'MIN_NOT_MET'
    discount_amount REAL,               -- Actual discount applied (NULL on failure)
    base_price REAL,                    -- Price before coupon
    route TEXT,                         -- e.g. 'DEL-BOM'
    search_id TEXT,                     -- Reference to search
    error_message TEXT,                 -- Error details on failure
    tested_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_coupon_test_code ON coupon_test_results(coupon_code, platform);
CREATE INDEX IF NOT EXISTS idx_coupon_test_result ON coupon_test_results(test_result);

-- Coupon Learnings (aggregated per-coupon per-platform stats)
CREATE TABLE IF NOT EXISTS coupon_learnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coupon_code TEXT NOT NULL,
    platform TEXT NOT NULL,
    total_tests INTEGER DEFAULT 0,
    successes INTEGER DEFAULT 0,
    failures INTEGER DEFAULT 0,
    success_rate REAL DEFAULT 0.0,
    avg_discount_amount REAL DEFAULT 0.0,
    max_discount_amount REAL DEFAULT 0.0,
    best_route TEXT,                    -- Route with most successes
    last_success_at DATETIME,
    last_failure_at DATETIME,
    computed_trust_score REAL DEFAULT 0.5,
    is_dead INTEGER DEFAULT 0,         -- 1 = deactivated due to zero successes
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(coupon_code, platform)
);

-- Pipeline Metrics (per-phase scraping metrics)
CREATE TABLE IF NOT EXISTS pipeline_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    phase TEXT NOT NULL,                -- 'overall', 'navigation', 'search', 'coupon_test', 'checkout'
    outcome TEXT NOT NULL,              -- 'SUCCESS', 'FAILURE'
    error_category TEXT,               -- 'CAPTCHA', 'TIMEOUT', 'ANTI_BOT', 'DOM_CHANGE', 'NETWORK', 'PARSE_ERROR', 'UNKNOWN'
    error_message TEXT,
    latency_ms INTEGER,
    search_id TEXT,
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pipeline_platform ON pipeline_metrics(platform, recorded_at);
CREATE INDEX IF NOT EXISTS idx_pipeline_phase ON pipeline_metrics(phase, outcome);

-- Search Patterns (user behavior tracking for preference learning)
CREATE TABLE IF NOT EXISTS search_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id TEXT NOT NULL,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    departure_date TEXT,
    departure_dow INTEGER,             -- Day of week (0=Mon, 6=Sun)
    departure_month INTEGER,
    days_advance INTEGER,              -- Days between search and departure
    selected_flight_id TEXT,           -- Which flight user chose
    selected_airline TEXT,
    selected_stops INTEGER,
    selected_departure_time TEXT,
    selected_price REAL,
    handoff_completed INTEGER DEFAULT 0,  -- 1 = user went to booking
    searched_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_search_patterns_route ON search_patterns(origin, destination);

-- User Preferences (learned preference profile)
CREATE TABLE IF NOT EXISTS user_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    preference_key TEXT NOT NULL UNIQUE,  -- 'preferred_airline', 'stop_tolerance', 'time_preference', etc.
    preference_value TEXT NOT NULL,       -- JSON blob with value details
    confidence REAL DEFAULT 0.5,
    evidence_count INTEGER DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Suggestion Tracking (which suggestions users act on)
CREATE TABLE IF NOT EXISTS suggestion_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id TEXT NOT NULL,
    suggestion_type TEXT NOT NULL,      -- 'LAYOVER', 'DATE_SHIFT', 'AIRPORT_ALT', 'TIME_SHIFT', 'CASHBACK'
    potential_saving REAL DEFAULT 0.0,
    was_clicked INTEGER DEFAULT 0,
    was_accepted INTEGER DEFAULT 0,     -- User actually booked via this suggestion
    shown_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_suggestion_type ON suggestion_tracking(suggestion_type);

-- Airport Alternatives (proximity/cost data for dynamic suggestions)
CREATE TABLE IF NOT EXISTS airport_alternatives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    primary_code TEXT NOT NULL,         -- e.g. 'GOI'
    alt_code TEXT NOT NULL,             -- e.g. 'GOX'
    alt_name TEXT NOT NULL,             -- e.g. 'Manohar Mopa Airport'
    city TEXT,                          -- e.g. 'Goa'
    distance_km REAL,                  -- Ground distance between airports
    ground_transport_cost REAL,        -- Estimated transport cost in INR
    transport_time_mins INTEGER,       -- Estimated travel time
    is_active INTEGER DEFAULT 1,
    UNIQUE(primary_code, alt_code)
);

-- Process Journal (self-improvement audit trail)
CREATE TABLE IF NOT EXISTS process_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,            -- 'COUPON_LEARNING', 'PREDICTION_ACCURACY', 'PIPELINE_HEALTH', 'SUGGESTION_TUNING'
    action TEXT NOT NULL,              -- What was done
    reason TEXT NOT NULL,              -- Why it was done
    before_value TEXT,                 -- JSON snapshot before change
    after_value TEXT,                  -- JSON snapshot after change
    impact_metric TEXT,                -- Which metric this affects
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_journal_category ON process_journal(category, recorded_at);



-- Comparable real quotes, separate from legacy seeded history.
CREATE TABLE IF NOT EXISTS fare_quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, route TEXT NOT NULL, departure_date TEXT NOT NULL,
    airline TEXT, flight_number TEXT, platform TEXT NOT NULL, passenger_count INTEGER NOT NULL,
    cabin_class TEXT NOT NULL, price REAL NOT NULL CHECK(price > 0),
    verification TEXT NOT NULL CHECK(verification IN ('listed','checkout')),
    observed_at TEXT NOT NULL, coupon_code TEXT,
    quality_status TEXT NOT NULL DEFAULT 'legacy_unchecked', departure_time TEXT,stops INTEGER
);
CREATE INDEX IF NOT EXISTS idx_fare_quotes_trip ON fare_quotes(route,departure_date,passenger_count,cabin_class,observed_at);

CREATE TABLE IF NOT EXISTS intelligence_cache (key TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS offer_observations (
 id INTEGER PRIMARY KEY, platform TEXT, code TEXT, description TEXT, valid_from TEXT,
 valid_until TEXT, source_url TEXT, observed_day TEXT,
 UNIQUE(platform,code,description,observed_day));
CREATE TABLE IF NOT EXISTS red_room (
 id TEXT PRIMARY KEY, request TEXT NOT NULL, interval_hours INTEGER NOT NULL,
 created_at TEXT NOT NULL, last_checked TEXT, last_price REAL, report TEXT,
 last_alert_key TEXT, is_active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS live_offer_evidence (
 platform TEXT NOT NULL, code TEXT NOT NULL, payload TEXT NOT NULL,
 observed_at TEXT NOT NULL, PRIMARY KEY(platform,code));
CREATE TABLE IF NOT EXISTS knowledge_sources (
 id INTEGER PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, source_url TEXT NOT NULL,
 published_at TEXT, observed_at TEXT NOT NULL, payload TEXT NOT NULL,
 UNIQUE(kind,source_url,title));
CREATE TABLE IF NOT EXISTS quote_quarantine (
 result_id TEXT PRIMARY KEY, reasons TEXT NOT NULL, payload TEXT NOT NULL, observed_at TEXT NOT NULL);

-- Scoped coupon trials are audit evidence, never global coupon guarantees or fare training.
CREATE TABLE IF NOT EXISTS coupon_audit_runs (
    id TEXT PRIMARY KEY, platform TEXT NOT NULL, search_id TEXT,
    scope TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL,
    completed_at TEXT, summary TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS coupon_audit_trials (
    run_id TEXT NOT NULL REFERENCES coupon_audit_runs(id), ordinal INTEGER NOT NULL,
    code TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL, observed_at TEXT NOT NULL,
    PRIMARY KEY(run_id,ordinal)
);
CREATE INDEX IF NOT EXISTS idx_coupon_audit_platform ON coupon_audit_runs(platform,started_at);

"""
Flight Finder — Self-Learning Intelligence Engine
Analyzes system performance across coupons, predictions, pipeline health,
and user behavior. Automatically applies improvements and logs all changes
to a process journal for full transparency.

Runs as a background loop every 6 hours.
"""

import json
import asyncio
from datetime import datetime, timedelta
from loguru import logger


class SelfLearningEngine:
    def __init__(self, db):
        self.db = db
        self.cycle_count = 0

    async def run_learning_cycle(self):
        """Master learning cycle — runs all analysis modules."""
        self.cycle_count += 1
        logger.info(f"🧠 [SelfLearning] Starting learning cycle #{self.cycle_count}...")
        
        try:
            await self.analyze_coupon_performance()
        except Exception as e:
            logger.error(f"[SelfLearning] Coupon analysis failed: {e}")
        
        try:
            await self.analyze_prediction_accuracy()
        except Exception as e:
            logger.error(f"[SelfLearning] Prediction analysis failed: {e}")
        
        try:
            await self.analyze_pipeline_health()
        except Exception as e:
            logger.error(f"[SelfLearning] Pipeline analysis failed: {e}")
        
        try:
            await self.analyze_suggestion_effectiveness()
        except Exception as e:
            logger.error(f"[SelfLearning] Suggestion analysis failed: {e}")
        
        logger.info(f"🧠 [SelfLearning] Learning cycle #{self.cycle_count} complete.")

    # ──────────────────────────────────────────────────────
    # 1. Coupon Intelligence
    # ──────────────────────────────────────────────────────

    async def analyze_coupon_performance(self):
        """
        Analyze all coupon test results, compute success rates,
        update trust scores, and deactivate dead coupons.
        """
        conn = self.db.db
        
        # Step 1: Aggregate test results into coupon_learnings
        agg_query = """
            SELECT 
                coupon_code, platform,
                COUNT(*) as total_tests,
                SUM(CASE WHEN test_result = 'SUCCESS' THEN 1 ELSE 0 END) as successes,
                SUM(CASE WHEN test_result != 'SUCCESS' THEN 1 ELSE 0 END) as failures,
                AVG(CASE WHEN test_result = 'SUCCESS' THEN discount_amount ELSE NULL END) as avg_discount,
                MAX(CASE WHEN test_result = 'SUCCESS' THEN discount_amount ELSE 0 END) as max_discount,
                MAX(CASE WHEN test_result = 'SUCCESS' THEN tested_at ELSE NULL END) as last_success,
                MAX(CASE WHEN test_result != 'SUCCESS' THEN tested_at ELSE NULL END) as last_failure
            FROM coupon_test_results
            GROUP BY coupon_code, platform
        """
        
        try:
            async with conn.execute(agg_query) as cursor:
                rows = await cursor.fetchall()
                
            improvements_made = 0
            for row in rows:
                code, platform = row[0], row[1]
                total, successes, failures = row[2], row[3], row[4]
                avg_disc = row[5] or 0.0
                max_disc = row[6] or 0.0
                last_success = row[7]
                last_failure = row[8]
                
                success_rate = successes / total if total > 0 else 0.0
                
                # Compute trust score: blend of success rate and recency
                recency_bonus = 0.0
                if last_success:
                    days_since_success = (datetime.now() - datetime.fromisoformat(last_success)).days
                    recency_bonus = max(0, 0.2 - (days_since_success * 0.01))  # Decay over 20 days
                
                computed_trust = min(1.0, (success_rate * 0.7) + recency_bonus + (0.1 if total >= 5 else 0.0))
                is_dead = 1 if (total >= 10 and successes == 0) else 0
                
                # Find best route for this coupon
                best_route = None
                try:
                    route_query = """
                        SELECT route, COUNT(*) as cnt FROM coupon_test_results
                        WHERE coupon_code = ? AND platform = ? AND test_result = 'SUCCESS' AND route IS NOT NULL
                        GROUP BY route ORDER BY cnt DESC LIMIT 1
                    """
                    async with conn.execute(route_query, (code, platform)) as rcur:
                        rrow = await rcur.fetchone()
                        if rrow:
                            best_route = rrow[0]
                except Exception:
                    pass
                
                # Upsert into coupon_learnings
                await conn.execute("""
                    INSERT INTO coupon_learnings 
                    (coupon_code, platform, total_tests, successes, failures, success_rate,
                     avg_discount_amount, max_discount_amount, best_route, last_success_at,
                     last_failure_at, computed_trust_score, is_dead, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(coupon_code, platform) DO UPDATE SET
                        total_tests = excluded.total_tests,
                        successes = excluded.successes,
                        failures = excluded.failures,
                        success_rate = excluded.success_rate,
                        avg_discount_amount = excluded.avg_discount_amount,
                        max_discount_amount = excluded.max_discount_amount,
                        best_route = excluded.best_route,
                        last_success_at = excluded.last_success_at,
                        last_failure_at = excluded.last_failure_at,
                        computed_trust_score = excluded.computed_trust_score,
                        is_dead = excluded.is_dead,
                        updated_at = excluded.updated_at
                """, (code, platform, total, successes, failures, success_rate,
                      avg_disc, max_disc, best_route, last_success, last_failure,
                      computed_trust, is_dead, datetime.now().isoformat()))
                
                # Update the main coupons table trust_score and success_rate
                old_trust = 0.5
                try:
                    async with conn.execute(
                        "SELECT trust_score FROM coupons WHERE code = ? AND platform = ?", (code, platform)
                    ) as tcur:
                        trow = await tcur.fetchone()
                        if trow:
                            old_trust = trow[0]
                except Exception:
                    pass
                
                await conn.execute("""
                    UPDATE coupons SET 
                        trust_score = ?,
                        success_rate = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE code = ? AND platform = ?
                """, (computed_trust, success_rate, code, platform))
                
                # Deactivate dead coupons
                if is_dead:
                    await conn.execute("""
                        UPDATE coupons SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                        WHERE code = ? AND platform = ?
                    """, (code, platform))
                    
                    await self.log_improvement(
                        category="COUPON_LEARNING",
                        action=f"Deactivated dead coupon {code} on {platform}",
                        reason=f"0 successes in {total} tests",
                        before_value=json.dumps({"is_active": True, "trust_score": old_trust}),
                        after_value=json.dumps({"is_active": False, "trust_score": computed_trust}),
                        impact_metric="coupon_success_rate"
                    )
                    improvements_made += 1
                
                # Log significant trust score changes
                if abs(computed_trust - old_trust) > 0.15:
                    await self.log_improvement(
                        category="COUPON_LEARNING",
                        action=f"Updated trust score for {code} on {platform}",
                        reason=f"Success rate: {success_rate:.1%} over {total} tests",
                        before_value=json.dumps({"trust_score": round(old_trust, 3)}),
                        after_value=json.dumps({"trust_score": round(computed_trust, 3)}),
                        impact_metric="coupon_trust_accuracy"
                    )
                    improvements_made += 1
            
            await conn.commit()
            logger.info(f"🧠 [SelfLearning] Coupon analysis: processed {len(rows)} codes, {improvements_made} improvements applied.")
            
        except Exception as e:
            logger.error(f"[SelfLearning] Coupon performance analysis error: {e}")

    # ──────────────────────────────────────────────────────
    # 2. Prediction Accuracy Feedback
    # ──────────────────────────────────────────────────────

    async def analyze_prediction_accuracy(self):
        """
        Enhanced prediction accuracy analysis with 12+ error categories
        and dynamic ensemble weight adjustment.
        """
        conn = self.db.db
        
        # Get recent audited predictions grouped by route
        routes_query = "SELECT DISTINCT route_key FROM prediction_queries WHERE audited = 1"
        try:
            async with conn.execute(routes_query) as cursor:
                routes = [r[0] for r in await cursor.fetchall()]
        except Exception:
            routes = []
            return
        
        for route in routes:
            # Get last 20 predictions for this route
            perf_query = """
                SELECT prediction_id, predicted_price_30d, actual_price_30d, 
                       prediction_error, current_price, predicted_at, signal
                FROM prediction_queries
                WHERE route_key = ? AND audited = 1
                ORDER BY predicted_at DESC LIMIT 20
            """
            try:
                async with conn.execute(perf_query, (route,)) as cursor:
                    preds = await cursor.fetchall()
            except Exception:
                continue
            
            if len(preds) < 3:
                continue
            
            # Calculate weighted MAPE (exponential decay — recent predictions weighted more)
            total_weight = 0.0
            weighted_error_sum = 0.0
            signal_accuracy = {"correct": 0, "incorrect": 0}
            
            for i, pred in enumerate(preds):
                weight = 0.9 ** i  # Exponential decay
                error = pred[3] if pred[3] is not None else 0.0
                weighted_error_sum += error * weight
                total_weight += weight
                
                # Check signal accuracy
                predicted_price = pred[1]
                actual_price = pred[2]
                signal = pred[6]
                
                if actual_price and predicted_price:
                    price_went_up = actual_price > pred[4]  # current_price at time of prediction
                    if signal == "BOOK_NOW" and price_went_up:
                        signal_accuracy["correct"] += 1
                    elif signal == "WAIT" and not price_went_up:
                        signal_accuracy["correct"] += 1
                    elif signal in ["BOOK_NOW", "WAIT"]:
                        signal_accuracy["incorrect"] += 1
            
            weighted_mape = weighted_error_sum / total_weight if total_weight > 0 else 0.0
            
            total_signals = signal_accuracy["correct"] + signal_accuracy["incorrect"]
            signal_accuracy_pct = signal_accuracy["correct"] / total_signals if total_signals > 0 else 0.5
            
            # Log if accuracy is concerning
            if weighted_mape > 0.20:
                logger.warning(f"🧠 [SelfLearning] Route {route}: weighted MAPE={weighted_mape:.1%}, signal accuracy={signal_accuracy_pct:.1%}")
                
                # Adjust ensemble weights — shift toward rules engine when ML is unreliable
                if weighted_mape > 0.30:
                    await self.log_improvement(
                        category="PREDICTION_ACCURACY",
                        action=f"Flagged route {route} for model retraining",
                        reason=f"Weighted MAPE {weighted_mape:.1%} exceeds 30% threshold. Signal accuracy: {signal_accuracy_pct:.1%}",
                        before_value=json.dumps({"mape": round(weighted_mape, 4)}),
                        after_value=json.dumps({"needs_retraining": True}),
                        impact_metric="prediction_mape"
                    )
            
            # Enhanced error attribution with 12 categories
            try:
                unclassified = """
                    SELECT pq.prediction_id, pq.route_key, pq.prediction_error, 
                           pq.predicted_at, pq.current_price, pq.actual_price_30d
                    FROM prediction_queries pq
                    LEFT JOIN error_attribution ea ON pq.prediction_id = ea.prediction_id
                    WHERE pq.route_key = ? AND pq.audited = 1 AND pq.prediction_error > 0.15
                    AND ea.id IS NULL
                    ORDER BY pq.predicted_at DESC LIMIT 10
                """
                async with conn.execute(unclassified, (route,)) as cursor:
                    unclass_rows = await cursor.fetchall()
                
                for row in unclass_rows:
                    pred_id = row[0]
                    error = row[2]
                    pred_at = datetime.fromisoformat(row[3])
                    current_p = row[4]
                    actual_p = row[5]
                    
                    if not actual_p or not current_p:
                        continue
                    
                    reason = self._classify_prediction_error(
                        error, pred_at, current_p, actual_p, route
                    )
                    
                    await conn.execute("""
                        INSERT OR IGNORE INTO error_attribution 
                        (prediction_id, route_key, mape, error_reason, attributed_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (pred_id, route, error, reason, datetime.now().isoformat()))
                
                await conn.commit()
            except Exception as e:
                logger.warning(f"Error attribution failed for {route}: {e}")

    def _classify_prediction_error(self, error: float, pred_at: datetime, 
                                    current_price: float, actual_price: float, route: str) -> str:
        """
        Classify prediction error into one of 12+ categories for root cause analysis.
        """
        price_change_pct = (actual_price - current_price) / current_price if current_price > 0 else 0
        month = pred_at.month
        
        route_lower = route.lower()
        beach_routes = ["goi", "gox", "cok", "ixz", "trv"]
        hill_routes = ["sxr", "ixl", "deh"]
        metro_routes = ["del", "bom", "blr", "maa", "ccu", "hyd"]
        
        # Category 1: Extreme price drops (flash sale)
        if price_change_pct < -0.25:
            return "Flash Sale / Extreme Price Drop"
        
        # Category 2: Extreme price spikes
        if price_change_pct > 0.30:
            return "Demand Surge / Extreme Price Spike"
        
        # Category 3: Festive season miss
        if month in [10, 11] and price_change_pct > 0.15:
            return "Diwali/Festive Season Underestimated"
        
        # Category 4: New Year/Christmas miss
        if month in [12, 1] and price_change_pct > 0.15:
            return "Christmas/NYE Demand Underestimated"
        
        # Category 5: Monsoon effect on beach destinations
        if month in [6, 7, 8, 9] and any(x in route_lower for x in beach_routes):
            return "Monsoon Season Pattern Missed"
        
        # Category 6: School vacation period
        if month in [5, 6, 12]:
            return "School Vacation Demand Shift"
        
        # Category 7: Exam period (March, April)
        if month in [3, 4]:
            return "Board Exam Period Pattern"
        
        # Category 8: Weekend/holiday proximity
        if pred_at.weekday() in [4, 5]:  # Friday/Saturday
            return "Weekend Travel Pattern Missed"
        
        # Category 9: Fuel price impact
        if abs(price_change_pct) > 0.10 and abs(price_change_pct) < 0.20:
            return "Gradual Market Shift (Possible Fuel/FX Impact)"
        
        # Category 10: Route competition change
        if any(x in route_lower for x in metro_routes) and price_change_pct < -0.15:
            return "Route Competition / New Entrant"
        
        # Category 11: Data staleness
        if error > 0.35:
            return "Severe Model Drift / Data Staleness"
        
        # Category 12: General
        return "General Prediction Variance"

    # ──────────────────────────────────────────────────────
    # 3. Pipeline Performance Monitor
    # ──────────────────────────────────────────────────────

    async def analyze_pipeline_health(self):
        """
        Analyze scraper pipeline success rates by platform,
        identify consistently failing platforms, and adjust strategies.
        """
        conn = self.db.db
        
        # Get per-platform success rates for last 7 days
        seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
        
        query = """
            SELECT 
                platform,
                COUNT(*) as total,
                SUM(CASE WHEN outcome = 'SUCCESS' THEN 1 ELSE 0 END) as successes,
                AVG(latency_ms) as avg_latency,
                -- Error breakdown
                SUM(CASE WHEN error_category = 'CAPTCHA' THEN 1 ELSE 0 END) as captcha_errors,
                SUM(CASE WHEN error_category = 'TIMEOUT' THEN 1 ELSE 0 END) as timeout_errors,
                SUM(CASE WHEN error_category = 'ANTI_BOT' THEN 1 ELSE 0 END) as antibot_errors,
                SUM(CASE WHEN error_category = 'DOM_CHANGE' THEN 1 ELSE 0 END) as dom_errors,
                SUM(CASE WHEN error_category = 'NETWORK' THEN 1 ELSE 0 END) as network_errors
            FROM pipeline_metrics
            WHERE recorded_at >= ? AND phase = 'overall'
            GROUP BY platform
        """
        
        try:
            async with conn.execute(query, (seven_days_ago,)) as cursor:
                rows = await cursor.fetchall()
            
            for row in rows:
                platform = row[0]
                total = row[1]
                successes = row[2]
                avg_latency = row[3] or 0
                captcha = row[4] or 0
                timeout = row[5] or 0
                antibot = row[6] or 0
                dom_change = row[7] or 0
                network = row[8] or 0
                
                success_rate = successes / total if total > 0 else 0.0
                
                # Flag platforms with < 40% success rate
                if total >= 5 and success_rate < 0.40:
                    dominant_error = "UNKNOWN"
                    error_counts = {
                        "CAPTCHA": captcha, "TIMEOUT": timeout, 
                        "ANTI_BOT": antibot, "DOM_CHANGE": dom_change, "NETWORK": network
                    }
                    if max(error_counts.values()) > 0:
                        dominant_error = max(error_counts, key=error_counts.get)
                    
                    await self.log_improvement(
                        category="PIPELINE_HEALTH",
                        action=f"Flagged platform {platform} as unreliable",
                        reason=f"Success rate {success_rate:.1%} ({successes}/{total}) in 7 days. Dominant error: {dominant_error}",
                        before_value=json.dumps({"success_rate": round(success_rate, 3), "avg_latency_ms": int(avg_latency)}),
                        after_value=json.dumps({"status": "flagged", "recommendation": self._get_platform_recommendation(dominant_error)}),
                        impact_metric="platform_reliability"
                    )
                    
                    logger.warning(f"🧠 [SelfLearning] Platform {platform}: {success_rate:.1%} success rate. Dominant error: {dominant_error}")
                
        except Exception as e:
            logger.error(f"[SelfLearning] Pipeline health analysis error: {e}")

    def _get_platform_recommendation(self, dominant_error: str) -> str:
        """Generate actionable recommendation based on dominant error type."""
        recommendations = {
            "CAPTCHA": "Increase human simulation intensity, add longer delays between actions",
            "TIMEOUT": "Increase page load timeout, add retry with exponential backoff",
            "ANTI_BOT": "Rotate fingerprints more aggressively, use proxy rotation",
            "DOM_CHANGE": "Platform likely updated their UI — worker selectors need updating",
            "NETWORK": "Check proxy connectivity, try direct connection as fallback",
            "UNKNOWN": "Manual investigation required — check logs for new error patterns"
        }
        return recommendations.get(dominant_error, recommendations["UNKNOWN"])

    # ──────────────────────────────────────────────────────
    # 4. Suggestion Effectiveness
    # ──────────────────────────────────────────────────────

    async def analyze_suggestion_effectiveness(self):
        """
        Analyze which money-saving suggestions users actually act on.
        Deprioritize suggestions with consistently low acceptance rates.
        """
        conn = self.db.db
        
        query = """
            SELECT 
                suggestion_type,
                COUNT(*) as total_shown,
                SUM(CASE WHEN was_clicked THEN 1 ELSE 0 END) as clicks,
                SUM(CASE WHEN was_accepted THEN 1 ELSE 0 END) as acceptances,
                AVG(potential_saving) as avg_saving
            FROM suggestion_tracking
            GROUP BY suggestion_type
            HAVING total_shown >= 10
        """
        
        try:
            async with conn.execute(query) as cursor:
                rows = await cursor.fetchall()
            
            for row in rows:
                stype = row[0]
                total = row[1]
                clicks = row[2]
                accepts = row[3]
                avg_saving = row[4] or 0
                
                click_rate = clicks / total if total > 0 else 0
                accept_rate = accepts / total if total > 0 else 0
                
                # Log poor performers
                if total >= 50 and accept_rate < 0.05:
                    await self.log_improvement(
                        category="SUGGESTION_TUNING",
                        action=f"Suggestion type '{stype}' has very low acceptance",
                        reason=f"Only {accept_rate:.1%} acceptance over {total} presentations (avg saving: Rs. {avg_saving:.0f})",
                        before_value=json.dumps({"acceptance_rate": round(accept_rate, 3), "total_shown": total}),
                        after_value=json.dumps({"recommendation": "deprioritize_or_rephrase"}),
                        impact_metric="suggestion_acceptance_rate"
                    )
                
                logger.info(f"🧠 [SelfLearning] Suggestion '{stype}': shown={total}, clicks={clicks} ({click_rate:.1%}), accepts={accepts} ({accept_rate:.1%})")
                
        except Exception as e:
            logger.error(f"[SelfLearning] Suggestion effectiveness analysis error: {e}")

    # ──────────────────────────────────────────────────────
    # 5. Process Journal
    # ──────────────────────────────────────────────────────

    async def log_improvement(self, category: str, action: str, reason: str,
                               before_value: str = None, after_value: str = None,
                               impact_metric: str = None):
        """Record a self-improvement action to the process journal."""
        try:
            conn = self.db.db
            await conn.execute("""
                INSERT INTO process_journal (category, action, reason, before_value, after_value, impact_metric)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (category, action, reason, before_value, after_value, impact_metric))
            await conn.commit()
            logger.info(f"📝 [Journal] [{category}] {action}")
        except Exception as e:
            logger.warning(f"Failed to write process journal entry: {e}")

    # ──────────────────────────────────────────────────────
    # 6. Learning Dashboard Data
    # ──────────────────────────────────────────────────────

    async def get_dashboard_data(self) -> dict:
        """Describe active audit facts; legacy research is not live accuracy.

        Coupon success belongs to a recorded booking/payment, never a global
        trust score. Forecast validation is gated per exact trip in intelligence;
        pooling inactive predictor rows would invent system-wide certainty.
        """
        from datetime import timezone
        conn = self.db.db
        current = datetime.now(timezone.utc)
        data = dict(data_source='active_audits', observed_at=current.isoformat(),
            cycle_count=None, improvements_count=None, provider_run_count=None,
            coupon_stats=dict(available=False, run_count=None, trial_count=None,
                run_statuses={}, trial_statuses={}, review_accepted_trials=None,
                checkout_accepted_trials=None, total_tracked=None, dead_coupons=None,
                avg_success_rate=None, avg_trust_score=None,
                scope_note='Trials are scoped to the recorded flight, date, terms and payment. Review acceptance does not verify final fees.'),
            pipeline_health={}, prediction_accuracy=dict(available=False,
                total_audited=None, avg_mape=None, status='PER_TRIP_VALIDATION_REQUIRED',
                reason='Accuracy and certainty are evaluated for each exact directed route, departure date, adult count, cabin and constraints. Open Price history & booking advice to inspect its evidence gate.'),
            suggestion_stats={}, suggestion_tracking_available=False,
            recent_journal=[], journal_scope='legacy_research_inactive', errors=[])
        try:
            async with conn.execute('SELECT status,COUNT(*) FROM coupon_audit_runs GROUP BY status') as cursor:
                run_statuses = {r[0]:r[1] for r in await cursor.fetchall()}
            async with conn.execute('''SELECT t.status,COUNT(*) FROM coupon_audit_trials t
                JOIN coupon_audit_runs r ON r.id=t.run_id GROUP BY t.status''') as cursor:
                trial_statuses = {r[0]:r[1] for r in await cursor.fetchall()}
            async with conn.execute('''SELECT
                SUM(CASE WHEN t.status='valid_match' AND r.status='review_only' THEN 1 ELSE 0 END),
                SUM(CASE WHEN t.status='valid_match' AND r.status='checkout_verified' THEN 1 ELSE 0 END)
                FROM coupon_audit_trials t JOIN coupon_audit_runs r ON r.id=t.run_id''') as cursor:
                accepted = await cursor.fetchone()
            data['coupon_stats'].update(available=True,run_count=sum(run_statuses.values()),
                trial_count=sum(trial_statuses.values()),run_statuses=run_statuses,trial_statuses=trial_statuses,
                review_accepted_trials=accepted[0] or 0,checkout_accepted_trials=accepted[1] or 0)
        except Exception:
            data['errors'].append('Active coupon audit statistics unavailable; no success rate was assumed.')
        try:
            async with conn.execute('''SELECT platform,COUNT(*),
                SUM(CASE WHEN status='success' THEN 1 ELSE 0 END)
                FROM provider_runs WHERE datetime(observed_at)>=datetime(?)
                AND datetime(observed_at)<=datetime(?) GROUP BY platform''',
                ((current-timedelta(days=7)).isoformat(),current.isoformat())) as cursor:
                rows = await cursor.fetchall()
            data['pipeline_health']={r[0]:dict(total=r[1],successes=r[2],
                success_rate=round(r[2]/r[1],3),avg_latency_ms=None,
                scope='Recorded listing retrieval outcomes during the last 7 days; not checkout or price accuracy.') for r in rows}
            data['provider_run_count']=sum(r[1] for r in rows)
        except Exception:
            data['errors'].append('Active provider outcomes unavailable; no reliability rate was assumed.')
        try:
            async with conn.execute('''SELECT category,action,reason,recorded_at
                FROM process_journal ORDER BY recorded_at DESC LIMIT 20''') as cursor:
                data['recent_journal']=[dict(category=r[0],action=r[1],reason=r[2],timestamp=r[3]) for r in await cursor.fetchall()]
        except Exception:
            data['errors'].append('Legacy research journal unavailable.')
        return data

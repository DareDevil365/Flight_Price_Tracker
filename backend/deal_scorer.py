"""
Flight Finder — Deal Scorer
Computes a composite rating (0-100) for flight deals
combining price history, savings depth, and route benchmarks.
"""

from loguru import logger


class DealScorer:
    def __init__(self, price_tracker):
        self.price_tracker = price_tracker

    async def calculate_score(self, route: str, final_price: float, coupon_savings: float, auxiliary_savings: float, date_alternatives: list = None) -> float:
        """
        Calculate a composite score from 0 to 100 representing the value of the flight deal.
        Weights:
        - Coupon/stacking savings depth: Max 30 points
        - Comparison vs 30-day average: Max 40 points
        - Comparison vs nearby-date prices: Max 20 points
        - Absolute price bonus for tickets under Rs. 2500: Max 10 points
        - Failsafe: Any ticket under Rs. 2000 gets 95-100 points
        """
        logger.info(f"[DealScorer] Scoring deal: Route={route}, Price=Rs. {final_price}, Coupon Savings=Rs. {coupon_savings}, Aux Savings=Rs. {auxiliary_savings}...")

        # 5. Failsafe for very cheap tickets
        if final_price < 2000.0:
            failsafe_bonus = ((2000.0 - final_price) / 2000.0) * 5.0
            total_score = round(95.0 + failsafe_bonus, 1)
            total_score = max(95.0, min(100.0, total_score))
            logger.info(f"[DealScorer] Failsafe triggered: {total_score}/100")
            return total_score

        total_savings = coupon_savings + auxiliary_savings

        # 1. Coupon Savings Depth Score (Max 30 points)
        base_price = final_price + total_savings
        if base_price > 0:
            savings_pct = (total_savings / base_price) * 100.0
        else:
            savings_pct = 0.0
        # 15% savings gives full 30 points
        savings_score = min(30.0, (savings_pct / 15.0) * 30.0)

        # 2. Historical Price Benchmark Score (Max 40 points)
        history_avg = None
        if self.price_tracker:
            try:
                # get_avg_price filters on source='scraped' by default
                history_avg = await self.price_tracker.db.get_avg_price(route, days=30, source="scraped")
            except Exception as e:
                logger.debug(f"Could not retrieve price average for scoring: {e}")

        historical_score = 20.0  # Default to middle value if no history exists
        if history_avg and history_avg > 0:
            diff_pct = ((final_price - history_avg) / history_avg) * 100.0
            if diff_pct < 0:
                discount_ratio = abs(diff_pct) / 15.0
                historical_score = min(40.0, 20.0 + (discount_ratio * 20.0))
            else:
                premium_ratio = diff_pct / 15.0
                historical_score = max(0.0, 20.0 - (premium_ratio * 20.0))
        else:
            historical_score = min(40.0, 20.0 + (total_savings / 1000.0) * 10.0)

        # 3. Comparison vs Nearby-Date Prices (Max 20 points)
        nearby_score = 10.0  # Default to middle value if no alternatives exist
        if date_alternatives:
            valid_alts = [alt for alt in date_alternatives if alt.get("price") and alt["price"] > 0]
            if valid_alts:
                min_alt_price = min(alt["price"] for alt in valid_alts)
                if final_price <= min_alt_price:
                    nearby_score = 20.0
                else:
                    diff_pct_alt = ((final_price - min_alt_price) / min_alt_price) * 100.0
                    nearby_score = max(0.0, 20.0 - (diff_pct_alt / 20.0) * 20.0)

        # 4. Absolute Price Bonus for tickets under Rs. 2500 (Max 10 points)
        absolute_bonus = 0.0
        if final_price < 2500.0:
            absolute_bonus = ((2500.0 - final_price) / 2500.0) * 10.0

        total_score = round(savings_score + historical_score + nearby_score + absolute_bonus, 1)
        total_score = max(0.0, min(100.0, total_score))
        
        logger.info(f"[DealScorer] Calculated Deal Score: {total_score}/100")
        return total_score

"""
Flight Finder — Layer 1 Zero-Latency Rules Engine
Catch obvious edge cases with hard heuristics prior to executing machine learning layers.
Uses continuous fuzzy sigmoids to eliminate binary cliff edges.
"""

import math
from loguru import logger

class Layer1RulesEngine:
    def __init__(self):
        pass

    def _sigmoid_down(self, value: float, center: float, width: float) -> float:
        """
        Decreasing sigmoid membership function.
        Returns 1.0 when value is far below center, 0.5 at center, and 0.0 when far above center.
        """
        if width == 0:
            return 1.0 if value <= center else 0.0
        try:
            return 1.0 / (1.0 + math.exp((value - center) / width))
        except OverflowError:
            return 0.0 if value > center else 1.0

    def _sigmoid_up(self, value: float, center: float, width: float) -> float:
        """
        Increasing sigmoid membership function.
        Returns 0.0 when value is far below center, 0.5 at center, and 1.0 when far above center.
        """
        return 1.0 - self._sigmoid_down(value, center, width)

    def evaluate(self, features: dict) -> dict:
        """
        Evaluate fuzzy rules based on Section 2 architecture specs.
        Returns:
            dict containing "signal" (BUY_NOW, WAIT, or NEUTRAL), "urgency" (HIGH, MEDIUM, LOW), 
            and "rule_triggered" (str)
        """
        days_to_departure = features.get("days_to_departure", 14)
        seats_remaining = features.get("seats_remaining_estimate", 30)
        active_festive = features.get("active_festive_events", [])
        days_to_fest_peak = features.get("days_to_festival_peak", 99)
        percentile_90d = features.get("price_percentile_last_90_days", 50.0)
        sale_active = features.get("airline_sale_window_active", False)
        cancel_window_active = features.get("booking_cancellation_window_active", False)
        competitor_sale = features.get("is_competitor_running_sale", False)
        is_duopoly = features.get("is_duopoly_route", False)
        
        # New feature inputs for enhanced rules
        price_change_24h_pct = features.get("price_change_24h_pct", 0.0)  # % change in 24h
        is_weekend_departure = features.get("is_weekend_departure", False)
        days_to_long_weekend = features.get("days_to_long_weekend", 99)
        new_airline_on_route = features.get("new_airline_on_route", False)
        oil_price_change_7d_pct = features.get("oil_price_change_7d_pct", 0.0)  # Brent crude % change

        # 1. Fuzzy Rule 1: High Urgency (Days to departure < 7 AND seats remaining < 10)
        f_days = self._sigmoid_down(days_to_departure, 7, 2)
        f_seats = self._sigmoid_down(seats_remaining, 10, 3)
        r1_activation = f_days * f_seats

        # 2. Fuzzy Rule 2: Festive Proximity (Festive event active AND days to peak < 14)
        is_festive_event = len(active_festive) > 0
        f_fest_days = self._sigmoid_down(days_to_fest_peak, 14, 3)
        r2_activation = f_fest_days if is_festive_event else 0.0

        # 3. Fuzzy Rule 3: Price Anomaly Low (90d percentile < 15)
        r3_activation = self._sigmoid_down(percentile_90d, 15, 4)

        # 4. Fuzzy Rule 4: Airline Sale Active
        r4_activation = 1.0 if sale_active else 0.0

        # 5. Fuzzy Rule 5: Booking Cancellation Window Active (cancellations spike at T-7 to T-1, only when days > 3)
        f_days_cancel = self._sigmoid_up(days_to_departure, 3, 1)
        r5_activation = f_days_cancel if cancel_window_active else 0.0

        # 6. Fuzzy Rule 6: Competitor Sale on Duopoly Route
        r6_activation = 1.0 if (competitor_sale and is_duopoly) else 0.0

        # ── NEW RULES ──

        # 7. Fuzzy Rule 7: Weekend/Holiday Proximity
        # Prices spike 3-5 days before long weekends or holiday departures
        f_weekend_proximity = self._sigmoid_down(days_to_long_weekend, 5, 1.5)
        r7_activation = f_weekend_proximity * (0.8 if is_weekend_departure else 0.4)

        # 8. Fuzzy Rule 8: Demand Velocity (price increased >5% in last 24h → BUY_NOW)
        f_demand_velocity = self._sigmoid_up(abs(price_change_24h_pct), 5.0, 2.0)
        r8_activation = f_demand_velocity if price_change_24h_pct > 0 else 0.0  # Only on price INCREASES

        # 9. Fuzzy Rule 9: Route Competition (new airline entered → WAIT for price war)
        r9_activation = 0.85 if new_airline_on_route else 0.0

        # 10. Fuzzy Rule 10: Oil Price Shock (Brent crude moved >5% in a week)
        f_oil_shock = self._sigmoid_up(abs(oil_price_change_7d_pct), 5.0, 2.0)
        # If oil went UP → prices will rise → BUY_NOW; if oil went DOWN → prices may fall → WAIT
        r10_buy_activation = f_oil_shock if oil_price_change_7d_pct > 0 else 0.0
        r10_wait_activation = f_oil_shock if oil_price_change_7d_pct < 0 else 0.0

        # 11. Fuzzy Rule 11: Railway Waitlist Pressure (Train waitlists spilling into flight demand)
        irctc_pressure = features.get("irctc_railway_pressure_index", 0.0)
        r11_activation = irctc_pressure

        # Define rules configuration
        rules = [
            {
                "name": "High Urgency Rule (T-7 / seats < 10)",
                "activation": r1_activation,
                "signal": "BUY_NOW",
                "urgency": "HIGH",
                "message": f"Flight is in less than 7 days and seat bucket is depleted (< 10 seats remaining). High risk of fare jump. (Activation: {int(r1_activation * 100)}%)"
            },
            {
                "name": "Festive Proximity Rule",
                "activation": r2_activation,
                "signal": "BUY_NOW",
                "urgency": "HIGH",
                "message": f"Major regional festival is approaching (< 14 days to peak). Demand and prices will spike further. (Activation: {int(r2_activation * 100)}%)"
            },
            {
                "name": "Low Price Anomaly Rule",
                "activation": r3_activation,
                "signal": "BUY_NOW",
                "urgency": "LOW",
                "message": f"Price is at an anomaly low (below 15th percentile of the last 90 days). Excellent buying opportunity. (Activation: {int(r3_activation * 100)}%)"
            },
            {
                "name": "Airline Sale Rule",
                "activation": r4_activation,
                "signal": "WAIT",
                "urgency": "LOW",
                "message": "An active airline sale window has been identified. Wait 48 hours for promo seat allocations to populate."
            },
            {
                "name": "Cancellation Window Rule",
                "activation": r5_activation,
                "signal": "WAIT",
                "urgency": "LOW",
                "message": f"Cancellation spike window detected (T-7 days / T-24hr cycles). Wait 24 hours for cheap released inventory. (Activation: {int(r5_activation * 100)}%)"
            },
            {
                "name": "Competitor Duopoly Price War Rule",
                "activation": r6_activation,
                "signal": "WAIT",
                "urgency": "LOW",
                "message": "Competitor has dropped prices on this duopoly route. Wait 6-12 hours for the main carrier to mirror the price drop."
            },
            {
                "name": "Weekend/Holiday Proximity Rule",
                "activation": r7_activation,
                "signal": "BUY_NOW",
                "urgency": "MEDIUM",
                "message": f"Long weekend or holiday departure approaching within 5 days. Prices typically spike 15-25% in this window. Book now to lock in current fare. (Activation: {int(r7_activation * 100)}%)"
            },
            {
                "name": "Demand Velocity Rule",
                "activation": r8_activation,
                "signal": "BUY_NOW",
                "urgency": "HIGH",
                "message": f"Price increased {price_change_24h_pct:.1f}% in the last 24 hours — strong demand surge detected. Book immediately before further escalation. (Activation: {int(r8_activation * 100)}%)"
            },
            {
                "name": "Route Competition Rule",
                "activation": r9_activation,
                "signal": "WAIT",
                "urgency": "MEDIUM",
                "message": "A new airline has entered this route recently. Wait 48-72 hours for competitive pricing to settle — expect a price war. (Activation: {int(r9_activation * 100)}%)"
            },
            {
                "name": "Oil Price Surge Rule",
                "activation": r10_buy_activation,
                "signal": "BUY_NOW",
                "urgency": "MEDIUM",
                "message": f"Brent crude oil rose {oil_price_change_7d_pct:.1f}% this week. Airlines typically pass fuel surcharges within 1-2 weeks. Lock in current fare. (Activation: {int(r10_buy_activation * 100)}%)"
            },
            {
                "name": "Oil Price Drop Rule",
                "activation": r10_wait_activation,
                "signal": "WAIT",
                "urgency": "LOW",
                "message": f"Brent crude oil dropped {abs(oil_price_change_7d_pct):.1f}% this week. Airline fuel surcharges may decrease. Consider waiting 1-2 weeks. (Activation: {int(r10_wait_activation * 100)}%)"
            },
            {
                "name": "Railway Waitlist Pressure Rule",
                "activation": r11_activation,
                "signal": "BUY_NOW",
                "urgency": "MEDIUM",
                "message": f"High train waitlist pressure (Index: {irctc_pressure:.2f}). Alternate rail options are saturated, spelling spillover demand for flights. Lock in current fare. (Activation: {int(r11_activation * 100)}%)"
            },
        ]

        # Find the rule with the highest activation
        best_rule = max(rules, key=lambda x: x["activation"])

        # Trigger if highest activation is > 0.5
        if best_rule["activation"] > 0.5:
            return {
                "signal": best_rule["signal"],
                "urgency": best_rule["urgency"],
                "rule_triggered": f"Rule Triggered: {best_rule['message']}"
            }

        return {
            "signal": "NEUTRAL",
            "urgency": "LOW",
            "rule_triggered": "Rule Triggered: No zero-latency rules triggered. Falling back to machine learning ensemble layers."
        }


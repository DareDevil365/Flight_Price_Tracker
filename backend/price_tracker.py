"""
Flight Finder — Price Tracker
Tracks historical pricing data points for flight routes and computes moving averages.
"""

from loguru import logger


class PriceTracker:
    def __init__(self, db):
        self.db = db

    async def log_price(self, route: str, departure_date: str, airline: str,
                        flight_number: str, price: float, platform: str,
                        cabin_class: str = "ECONOMY"):
        """Log a pricing data point to database history."""
        logger.info(f"[PriceTracker] Logging price: {route} | {flight_number} | Rs. {price}")
        await self.db.log_price(
            route=route,
            departure_date=departure_date,
            airline=airline,
            flight_number=flight_number,
            price=price,
            platform=platform,
            cabin_class=cabin_class
        )

    async def get_history(self, route: str, days: int = 30) -> list[dict]:
        """Fetch historical price points for a route."""
        return await self.db.get_price_history(route, days)

    async def get_average_price(self, route: str, days: int = 30) -> float:
        """Calculate the average price for a route over the specified timeframe."""
        avg = await self.db.get_avg_price(route, days)
        return avg or 0.0

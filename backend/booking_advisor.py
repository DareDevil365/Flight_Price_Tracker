"""Conservative booking advice using comparable, real quotes only.

The experimental synthetic-data ensemble remains available under price_predictor.py
for research. It is deliberately excluded from user booking decisions.
"""
from datetime import date, datetime
from advisor_evidence import history_rows, fresh_timestamp


class PricePredictor:
    def __init__(self, db):
        self.db = db

    async def predict(self, origin_or_route, destination_or_date, travel_date=None, airline=None,
                      passenger_count=1, cabin_class='ECONOMY', preferred_time='ANY', max_stops=None):
        if travel_date is None:
            origin, destination = origin_or_route.upper().split('-')
            travel_date = destination_or_date
        else:
            origin, destination = origin_or_route.upper(), destination_or_date.upper()
        departure = date.fromisoformat(travel_date)
        days = (departure - datetime.now().date()).days
        if days < 0:
            raise ValueError('Travel date must be today or later')
        route = f'{origin}-{destination}'
        rows = await self.db.get_quotes(route, travel_date, passenger_count, cabin_class,preferred_time=preferred_time,max_stops=max_stops)
        trip=dict(origin=origin,destination=destination,departure_date=travel_date,passenger_count=passenger_count,cabin_class=cabin_class,
            preferred_time=preferred_time,max_stops=max_stops)
        rows=history_rows(rows,trip,airline=airline)
        listed = [r for r in rows if r['verification'] == 'listed']
        rows = [r for r in rows if r['verification'] == 'checkout']
        # fare_quotes is an audit ledger, not a live cart registry. A receipt's
        # age cannot establish that its browser session/payment choices still
        # exist or that another request is eligible for its coupon.
        fresh_listed = [r for r in listed if fresh_timestamp(r['observed_at'])]
        listed_best = min(fresh_listed,key=lambda r:r['price']) if fresh_listed else None
        signal = 'MONITOR'
        reason = 'No current checkout session was verified by this history request. Search your travel dates and verify the selected cart before buying.'
        if listed_best:
            reason = f"Lowest listed fare observed in the last 24 hours is INR {listed_best['price']:,.0f} on {listed_best['platform']}. Verify checkout fees and eligible coupons before comparing final totals."
        # Selected payment/add-on carts are not a comparable 90-day market series.
        # Do not average them or call an arbitrary collection of carts a route low.
        observed_days = len({r['observed_at'][:10] for r in [*rows,*listed]})
        return dict(route=f'{origin} → {destination}',travel_date=travel_date,today=date.today().isoformat(),currency='INR',
            current_price=None,current_best_price=None,current_best_platform=None,
            current_listed_price=listed_best['price'] if listed_best else None,
            current_listed_platform=listed_best['platform'] if listed_best else None,
            current_best_coupon=None,
            decision=dict(signal=signal,urgency='HIGH' if days<=7 else 'LOW',confidence=None,
                recommended_book_by=date.today().isoformat() if signal=='BOOK_NOW' else None,
                expected_price_on_book_date=None,potential_savings=0,reasoning=reason),
            forecast=dict(price_7d=None,price_14d=None,price_30d=None,direction='UNKNOWN',confidence_band=dict(low=None,high=None)),
            price_context=dict(vs_90d_average=None,
                price_bracket='OBSERVED',all_time_low_this_route=None),
            data_freshness=dict(price_data_age_minutes=None,
                model_trained_date=None,observed_days=observed_days,archived_checkout_receipts=len(rows)),
            key_drivers=[],risk_flags=['Checkout totals can change before payment. Future prices are not validated.'],
            scenarios=[],smart_suggestions=[],optimal_booking_strategy=dict(best_day_to_book='Compare fresh totals for the same trip.'))

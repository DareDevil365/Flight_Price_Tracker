"""Price evidence shared by advice and alternative comparisons."""
import math


def positive_amount(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def listed_amount(row):
    """Never substitute a payment total for a missing original listing."""
    meta = row.get('savings_breakdown', {})
    price = meta.get('listed_price')
    if price is None and meta.get('verification') == 'listed':
        price = row.get('final_price')
    return price if positive_amount(price) else None


def listing_view(row):
    price = listed_amount(row)
    if price is None:
        return None
    return {**row, 'final_price': price, 'savings_breakdown': {
        **row['savings_breakdown'], 'verification': 'listed'}}

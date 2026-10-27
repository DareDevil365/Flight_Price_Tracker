"""Current cart state is separate from a previously observed payment receipt."""
import math
from copy import deepcopy

from quotes import utc_now


def invalidate_checkout(quote):
    """Withdraw an old verification before rechecking a mutable merchant cart.

    Retain its small receipt for explanation. Immutable historical observations
    are not deleted; neither the receipt nor this fallback is a new fare sample.
    """
    meta = quote.get('savings_breakdown', {})
    if meta.get('verification') != 'checkout':
        return False
    meta['previous_checkout'] = dict(
        price=quote['final_price'], coupon=quote.get('best_coupon_code'),
        observed_at=meta.get('observed_at'), invalidated_at=utc_now(),
        selected_payment=deepcopy(meta.get('selected_payment')),
    )
    listed = meta.get('listed_price')
    usable_listing = (isinstance(listed, (int, float)) and not isinstance(listed, bool)
                      and math.isfinite(listed) and listed > 0)
    if usable_listing:
        quote.update(base_price=listed, final_price=listed, effective_price=listed)
        meta.update(verification='listed', effective_price=listed,
                    observed_at=meta.get('listed_observed_at'),
                    integrity=dict(status='uncorroborated', reasons=[
                        'Previous payment verification withdrawn while the cart is rechecked. The old listing also needs a fresh comparison.'
                    ], compared_sources=[]))
    else:
        # Legacy receipts without a listing cannot be made into a listed fare.
        meta.update(verification='unverified', integrity=dict(status='flagged',
            reasons=['Previous checkout withdrawn; no original listing is available.'], compared_sources=[]))
    quote.update(best_coupon_code=None, savings=0, all_tested_coupons=[])
    meta['checkout_price'] = None
    meta['fee_status'] = 'Previous checkout total is no longer current. Reverification must succeed before using its fees or coupon savings.'
    for key in ('selected_payment', 'cart_options', 'fee_scope', 'fee_breakdown', 'coupon_coverage'):
        meta.pop(key, None)
    return True

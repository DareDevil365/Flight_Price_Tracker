"""
Flight Finder — Financial Filter
Pre-filters coupon codes against the user's financial profile
BEFORE any DOM interaction (saves time and avoids detection).
"""

from loguru import logger


class FinancialFilter:
    def assess(self, coupon, rules):
        from offer_rules import Decision, evaluate_offer
        if rules.get('is_domestic') is not None:
            from compiler import is_international_only_coupon,is_domestic_only_coupon,is_flight_coupon
            code,desc=coupon.get('code',''),coupon.get('description') or ''
            if not is_flight_coupon(code,desc):
                return Decision('ineligible',['This is not a flight offer'])
            intl=is_international_only_coupon(code,desc)
            domestic=is_domestic_only_coupon(code,desc)
            if (rules['is_domestic'] and intl and not domestic) or (not rules['is_domestic'] and domestic and not intl):
                return Decision('ineligible',['Offer route scope differs from this trip'])
        if not coupon.get('description'):
            for flag,allow,label in [('requires_emi','allow_emi','EMI'),('requires_bnpl','allow_bnpl','BNPL')]:
                if coupon.get(flag) and not rules.get(allow,False):
                    return Decision('ineligible',[label+' blocked by user'])
            if coupon.get('requires_wallet') and not rules.get('allow_wallet_offers',True):
                return Decision('ineligible',['Wallet payment blocked by user'])
        return evaluate_offer(coupon,rules)

    def passes(self, coupon, rules):
        decision=self.assess(coupon,rules)
        # Conditional deals are visible before payment, but cannot prove savings.
        passes=decision.status=='eligible' or (decision.status=='unknown' and rules.get('selected_payment') is None)
        return passes, ('Conditional: ' if decision.status=='unknown' else '')+'; '.join(decision.reasons)

    def contains_violation(self, restriction_text, rules):
        if not restriction_text:
            return False
        from offer_parser import published_offer
        offer=published_offer('verification','TERMS',restriction_text,'')
        return bool(offer and not self.passes(offer,rules)[0])

    def filter_coupons(self, coupons: list[dict], rules: dict) -> tuple[list[dict], list[dict]]:
        """
        Split coupons into passed and filtered lists.
        Returns (passed_coupons, filtered_coupons).
        """
        passed = []
        filtered = []

        for coupon in coupons:
            ok, reason = self.passes(coupon, rules)
            if ok:
                passed.append(coupon)
            else:
                filtered.append({**coupon,'filter_reason':reason})

        logger.info(
            f"Financial filter: {len(passed)} passed, {len(filtered)} filtered "
            f"out of {len(coupons)} total"
        )
        return passed, filtered

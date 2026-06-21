"""
Flight Finder — Financial Filter
Pre-filters coupon codes against the user's financial profile
BEFORE any DOM interaction (saves time and avoids detection).
"""

from loguru import logger


class FinancialFilter:
    def passes(self, coupon: dict, rules: dict) -> tuple[bool, str]:
        """
        Check if a coupon passes the user's financial rules.
        Returns (passes: bool, reason: str).
        """
        # EMI check
        if coupon.get("requires_emi") and not rules.get("allow_emi", False):
            return False, "Requires EMI (blocked by user)"

        # BNPL check
        if coupon.get("requires_bnpl") and not rules.get("allow_bnpl", False):
            return False, "Requires BNPL (blocked by user)"

        # Wallet check
        if coupon.get("requires_wallet") and not rules.get("allow_wallet_offers", True):
            return False, "Requires wallet payment (blocked by user)"

        # App-only check
        if coupon.get("app_only") and not rules.get("allow_app_only", False):
            return False, "App-only offer (blocked by user)"

        # Bank blacklist check
        bank = coupon.get("bank_restriction")
        blacklisted = rules.get("blacklisted_banks", [])
        if bank and blacklisted:
            if bank.upper() in [b.upper() for b in blacklisted]:
                return False, f"Bank {bank} is blacklisted"

        # Bank whitelist check
        whitelisted = rules.get("whitelisted_banks", [])
        if bank and whitelisted:
            if bank.upper() not in [b.upper() for b in whitelisted]:
                return False, f"Bank {bank} not in whitelist"

        # Card type check
        card_type = coupon.get("card_type", "ANY")
        allowed_types = rules.get("allowed_card_types", [])
        if card_type != "ANY" and allowed_types:
            if card_type not in allowed_types:
                return False, f"Card type {card_type} not allowed"

        return True, "Passed all filters"

    def contains_violation(self, restriction_text: str, rules: dict) -> bool:
        """
        Check if restriction text from the DOM contains a financial violation.
        This catches cases where the coupon was accepted by the site but
        requires a bank/method the user has blocked.
        """
        if not restriction_text:
            return False

        text_upper = restriction_text.upper()

        # Check blacklisted banks mentioned in restriction text
        for bank in rules.get("blacklisted_banks", []):
            if bank.upper() in text_upper:
                return True

        # Check for EMI requirement
        if not rules.get("allow_emi", False):
            emi_keywords = ["EMI", "EQUATED MONTHLY", "INSTALLMENT"]
            if any(kw in text_upper for kw in emi_keywords):
                return True

        # Check for BNPL requirement
        if not rules.get("allow_bnpl", False):
            bnpl_keywords = ["BUY NOW PAY LATER", "BNPL", "PAY LATER", "SIMPL", "LAZYPAY"]
            if any(kw in text_upper for kw in bnpl_keywords):
                return True

        return False

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
                coupon["filter_reason"] = reason
                filtered.append(coupon)

        logger.info(
            f"Financial filter: {len(passed)} passed, {len(filtered)} filtered "
            f"out of {len(coupons)} total"
        )
        return passed, filtered

"""
Flight Finder — Third-Party Savings Stacker
Calculates reward rates, cashback portal routing (CashKaro), and payment method bonuses
to determine the absolute lowest 'effective price' for the user.
"""

from loguru import logger


class SavingsStacker:
    def __init__(self, db):
        self.db = db

    async def calculate_all_savings(self, platform: str, checkout_price: float, financial_profile: dict, bank_restriction: str = None) -> dict:
        """
        Evaluate all external savings layers (Cashback portals, Card rewards, UPI/Wallet promotions)
        and compile the optimal stacking strategy, including platform convenience fees.
        """
        logger.info(f"[SavingsStacker] Stacking savings for {platform} on Rs. {checkout_price} (Coupon Bank Restriction: {bank_restriction})...")
        
        # 0. Define platform convenience fees
        convenience_fees = {
            "makemytrip": 0.0,
            "easemytrip": 0.0,
            "cleartrip": 0.0,
            "yatra": 0.0,
            "ixigo": 0.0,
            "paytm": 0.0,
            "google_flights": 0.0,
            "mock": 0.0
        }
        convenience_fee = convenience_fees.get(platform.lower(), 0.0)
        
        # The transaction price at checkout includes the convenience fee
        checkout_price_with_fee = checkout_price + convenience_fee

        # Load active offers from the database
        external_offers = []
        global_offers = []
        if self.db:
            try:
                external_offers = await self.db.get_external_savings(platform)
                global_offers = await self.db.get_external_savings("ALL")
            except Exception as e:
                logger.error(f"[SavingsStacker] Failed to load external savings from DB: {e}")
        all_offers = external_offers + global_offers

        best_cashback_portal = {"provider": "None", "amount": 0.0, "type": "cashback_portal"}
        best_wallet_promo = {"provider": "None", "amount": 0.0, "type": "wallet_offer"}
        best_upi_promo = {"provider": "None", "amount": 0.0, "type": "upi_offer"}
        card_rewards = {"provider": "Credit Card", "amount": 0.0, "type": "card_rewards"}

        # 1. Evaluate Cashback Portals (e.g., CashKaro)
        for offer in all_offers:
            if offer["savings_type"] == "cashback_portal":
                # Check min transaction threshold
                min_tx = offer.get("min_transaction") or 0.0
                if checkout_price_with_fee >= min_tx:
                    rate = offer.get("savings_value") or 0.0
                    val = checkout_price_with_fee * (rate / 100.0)
                    # Apply cap
                    cap = offer.get("max_savings")
                    if cap and val > cap:
                        val = cap
                    if val > best_cashback_portal["amount"]:
                        best_cashback_portal = {
                            "provider": offer["provider"],
                            "amount": val,
                            "type": "cashback_portal",
                            "rate_percent": rate
                        }

            # 2. Evaluate Wallet Offers (Amazon Pay, Paytm)
            elif offer["savings_type"] == "wallet_offer":
                # Check if wallet offers are allowed by user profile
                if not bank_restriction and "WALLET" in financial_profile.get("allowed_card_types", []) and financial_profile.get("allow_wallet_offers", True):
                    min_tx = offer.get("min_transaction") or 0.0
                    if checkout_price_with_fee >= min_tx:
                        val = 0.0
                        if offer["savings_unit"] == "PERCENT":
                            rate = offer.get("savings_value") or 0.0
                            val = checkout_price_with_fee * (rate / 100.0)
                            cap = offer.get("max_savings")
                            if cap and val > cap:
                                val = cap
                        else:  # FLAT
                            val = offer.get("savings_value") or 0.0
                            if val > checkout_price_with_fee:
                                val = checkout_price_with_fee
                        
                        if val > best_wallet_promo["amount"]:
                            best_wallet_promo = {
                                "provider": offer["provider"],
                                "amount": val,
                                "type": "wallet_offer"
                            }

            # 3. Evaluate UPI Offers (PhonePe, GPay)
            elif offer["savings_type"] == "upi_offer" and not bank_restriction and "UPI" in financial_profile.get("allowed_card_types", []):
                min_tx = offer.get("min_transaction") or 0.0
                if checkout_price_with_fee >= min_tx:
                    val = 0.0
                    if offer["savings_unit"] == "PERCENT":
                        rate = offer.get("savings_value") or 0.0
                        val = checkout_price_with_fee * (rate / 100.0)
                        cap = offer.get("max_savings")
                        if cap and val > cap:
                            val = cap
                    else:  # FLAT
                        val = offer.get("savings_value") or 0.0
                        if val > checkout_price_with_fee:
                            val = checkout_price_with_fee
                    
                    if val > best_upi_promo["amount"]:
                        best_upi_promo = {
                            "provider": offer["provider"],
                            "amount": val,
                            "type": "upi_offer"
                        }

        # 4. Calculate Credit Card Reward Points
        card_rates = financial_profile.get("card_reward_rates", [])
        if card_rates and "CREDIT" in financial_profile.get("allowed_card_types", []):
            for card in card_rates:
                bank = card.get("bank", "")
                if bank in financial_profile.get("blacklisted_banks", []):
                    continue
                # If there is a coupon bank restriction, we can ONLY use credit cards from that bank!
                if bank_restriction and bank.upper() != bank_restriction.upper():
                    continue
                rate = card.get("rate") or 0.0
                val = checkout_price_with_fee * (rate / 100.0)
                if val > card_rewards["amount"]:
                    card_rewards = {
                        "provider": f"{bank} Card Rewards",
                        "amount": val,
                        "type": "card_rewards",
                        "rate_percent": rate
                    }

        # Determine best payment method
        payment_options = [best_wallet_promo, best_upi_promo, card_rewards]
        best_payment_method = max(payment_options, key=lambda o: o["amount"])

        total_aux_savings = best_cashback_portal["amount"] + best_payment_method["amount"]
        effective_price = max(0.0, checkout_price_with_fee - total_aux_savings)

        # Generate step-by-step instructions
        instructions = []
        if best_cashback_portal["amount"] > 0:
            instructions.append(f"1. Open {best_cashback_portal['provider']} and click through to {platform.capitalize()} to activate cashback.")
        
        step_num = len(instructions) + 1
        if best_payment_method["type"] == "card_rewards":
            instructions.append(f"{step_num}. At checkout, pay using your {best_payment_method['provider']} to earn reward points.")
        elif best_payment_method["type"] == "wallet_offer":
            instructions.append(f"{step_num}. Select {best_payment_method['provider']} as payment method to claim the wallet offer.")
        elif best_payment_method["type"] == "upi_offer":
            instructions.append(f"{step_num}. Pay using {best_payment_method['provider']} UPI to claim the instant cashback.")

        return {
            "convenience_fee": convenience_fee,
            "checkout_price_before_fee": checkout_price,
            "checkout_price": checkout_price_with_fee,
            "effective_price": effective_price,
            "total_stacking_savings": total_aux_savings,
            "cashback_portal": best_cashback_portal,
            "payment_method": best_payment_method,
            "instructions": instructions
        }


def calculate_net_emi_savings(coupon_code: str, coupon_desc: str, requires_emi: bool, base_price: float, face_discount: float) -> tuple[float, float, str]:
    """
    Given a coupon's properties and base price:
    - Calculates the estimated interest overhead for EMI.
    - If it's No-Cost EMI, the upfront discount is completely offset by the interest charged,
      meaning net savings is 0.
    - If it's Standard EMI, the net savings is face discount - interest overhead.
    Returns: (net_savings, interest_cost, warning_msg)
    """
    coupon_code_upper = (coupon_code or "").upper()
    coupon_desc_lower = (coupon_desc or "").lower()
    
    is_emi = requires_emi or "EMI" in coupon_code_upper or "emi" in coupon_desc_lower
    if not is_emi:
        return face_discount, 0.0, ""

    # Check if No-Cost EMI
    is_nocost = "NOCOST" in coupon_code_upper or "no cost" in coupon_desc_lower or "no-cost" in coupon_desc_lower or "zero interest" in coupon_desc_lower
    
    # Upfront transaction amount = base_price - face_discount
    transaction_amount = max(0.0, base_price - face_discount)
    
    # 14% interest p.a., 6 months tenure
    interest_rate = 0.14
    tenure_months = 6
    monthly_rate = interest_rate / 12
    
    if monthly_rate > 0 and transaction_amount > 0:
        emi = transaction_amount * (monthly_rate * (1 + monthly_rate)**tenure_months) / ((1 + monthly_rate)**tenure_months - 1)
        total_repaid = emi * tenure_months
        interest_cost = max(0.0, total_repaid - transaction_amount)
    else:
        interest_cost = 0.0

    if is_nocost:
        # In a No-Cost EMI transaction, the merchant discount equals the bank's interest charge.
        # This interest is charged to the customer by the bank, offsetting the discount.
        # So true net savings is zero!
        interest_cost = face_discount
        net_savings = 0.0
        warning_msg = f"No-Cost EMI: Upfront ₹{face_discount:.0f} discount is offset by ₹{interest_cost:.0f} bank interest charges. True savings is ₹0."
    else:
        net_savings = max(0.0, face_discount - interest_cost)
        warning_msg = f"EMI Offer: Upfront ₹{face_discount:.0f} discount is offset by ₹{interest_cost:.0f} estimated bank interest (14% p.a., 6m). Net savings is ₹{net_savings:.0f}."

    return net_savings, interest_cost, warning_msg

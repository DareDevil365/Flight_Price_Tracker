"""
Flight Finder — Coupon Brute-Force Engine
Tests a series of pre-filtered coupon codes sequentially on checkout pages.
Monitors price adjustments, parses rules, and maintains session state.
"""

import asyncio
import random
from loguru import logger
from human_sim import HumanSimulator
from savings_stacker import calculate_net_emi_savings


class CouponBruteForcer:
    def __init__(self, platform_worker, financial_filter, log_callback):
        self.worker = platform_worker
        self.filter = financial_filter
        self.log = log_callback
        self.human = HumanSimulator()

    async def brute_force(self, page, coupons: list[dict], financial_rules: dict, search_id: str, db=None, route: str = None) -> dict:
        """
        Test all applicable coupons at the checkout page.
        Returns a summary dictionary of results.
        """
        results = []
        baseline_price = await self.worker.parse_current_price(page)
        best_price = baseline_price
        best_coupon = None

        db_smart_coupons = []
        # Smart ordering: query smartest coupons from DB if available, and sort by priority score
        if db:
            try:
                db_smart_coupons = await db.get_smartest_coupons(self.worker.platform_id, route=route, price=baseline_price)
                priority_map = {c["code"].upper(): c["smart_priority"] for c in db_smart_coupons}
                
                # Sort input coupons using the priority map, default to 50.0 for new/onsite coupons
                sorted_coupons = sorted(coupons, key=lambda c: priority_map.get(c["code"].upper(), 50.0), reverse=True)
            except Exception as e:
                logger.warning(f"Failed to fetch smart coupons for sorting: {e}")
                sorted_coupons = sorted(coupons, key=lambda c: c.get("discount_value") or 0.0, reverse=True)
        else:
            sorted_coupons = sorted(coupons, key=lambda c: c.get("discount_value") or 0.0, reverse=True)

        total_coupons = len(sorted_coupons)
        self.log(search_id, self.worker.platform_id, "info", f"Starting brute force loop. Total coupons to test: {total_coupons}")

        consecutive_failures = 0

        for i, coupon in enumerate(sorted_coupons):
            code = coupon["code"]
            
            # --- 1. PRE-FILTER ---
            passes, reason = self.filter.passes(coupon, financial_rules)
            if not passes:
                self.log(search_id, self.worker.platform_id, "info", f"Skipping {code} — Pre-filter reject: {reason}")
                results.append({
                    "code": code,
                    "status": "pre_filtered",
                    "reason": reason
                })
                continue

            # --- 2. SMART SKIP DEAD COUPONS ---
            if db_smart_coupons:
                db_coupon = next((c for c in db_smart_coupons if c["code"].upper() == code.upper()), None)
                if db_coupon:
                    learned_success_rate = db_coupon.get("learned_success_rate")
                    learned_total_tests = db_coupon.get("learned_total_tests") or 0
                    if learned_success_rate is not None and learned_success_rate < 0.05 and learned_total_tests >= 10:
                        self.log(search_id, self.worker.platform_id, "info", f"Smart Skip: skipping {code} due to low success rate ({learned_success_rate:.1%}) over {learned_total_tests} tests.")
                        results.append({
                            "code": code,
                            "status": "skipped_low_success",
                            "reason": "Learned success rate < 5% over 10+ tests"
                        })
                        continue

            # --- 3. EARLY STOP CHECK ---
            if consecutive_failures >= 3:
                remaining_coupons = sorted_coupons[i:]
                all_low_success = True
                for rc in remaining_coupons:
                    rc_code = rc["code"].upper()
                    rc_db = next((c for c in db_smart_coupons if c["code"].upper() == rc_code), None)
                    rc_success_rate = rc_db.get("learned_success_rate") if rc_db else None
                    
                    if rc_success_rate is None or rc_success_rate >= 0.20:
                        all_low_success = False
                        break
                
                if all_low_success:
                    self.log(search_id, self.worker.platform_id, "info", f"Early Stop triggered: 3 consecutive failures and all remaining coupons have success rate < 20%.")
                    for rc in remaining_coupons:
                        results.append({
                            "code": rc["code"],
                            "status": "skipped_early_stop",
                            "reason": "Early stop triggered"
                        })
                    break

            try:
                self.log(search_id, self.worker.platform_id, "info", f"Testing coupon: {code}...")

                # 1. Clear any existing coupon field contents
                await self.worker.clear_coupon_field(page)
                await page.wait_for_timeout(2000)  # Wait for price layout to recalculate back to baseline
                
                cleared_price = await self.worker.parse_current_price(page)
                if abs(cleared_price - baseline_price) > 0.01:
                    self.log(search_id, self.worker.platform_id, "warning", f"Price did not return to baseline immediately. Expected Rs. {baseline_price}, got Rs. {cleared_price}. Retrying wait...")
                    await page.wait_for_timeout(2000)
                    cleared_price = await self.worker.parse_current_price(page)
                    if abs(cleared_price - baseline_price) > 0.01:
                        self.log(search_id, self.worker.platform_id, "warning", f"Page price Rs. {cleared_price} failed to return to baseline Rs. {baseline_price} after clearing. Proceeding with caution.")
                
                await self.human.random_delay(300, 800)

                # 2. Type coupon code using human simulation
                await self.human.type_text(page, self.worker.coupon_selector, code)
                await self.human.random_delay(200, 500)

                # 3. Click Apply
                await self.worker.click_apply_coupon(page)

                # 4. Wait for page layout/price to recalculate
                await page.wait_for_timeout(3000)

                # 5. Check if coupon was accepted
                apply_check = await self.worker.check_coupon_applied(page)
                
                if not apply_check.get("success"):
                    error_msg = apply_check.get("error") or "Coupon not applicable"
                    self.log(search_id, self.worker.platform_id, "warning", f"Coupon {code} -> Rejected: {error_msg}")
                    results.append({
                        "code": code,
                        "status": "invalid",
                        "reason": error_msg
                    })

                    consecutive_failures += 1
                    test_result = 'FAILED'
                    if "minimum" in error_msg.lower() or "min" in error_msg.lower():
                        test_result = 'MIN_NOT_MET'
                    elif "expired" in error_msg.lower() or "expiry" in error_msg.lower():
                        test_result = 'EXPIRED'

                    if db:
                        await db.save_coupon_test_result(
                            code=code,
                            platform=self.worker.platform_id,
                            result=test_result,
                            discount=None,
                            base_price=baseline_price,
                            route=route,
                            search_id=search_id,
                            error_msg=error_msg
                        )
                    continue

                # 6. Parse new total checkout price
                new_price = await self.worker.parse_current_price(page)

                # 7. Check validation warning text on screen (for card restrictions)
                validation_text = await self.worker.get_coupon_validation_text(page)

                # 8. Filter page text for rules violations (e.g. DOM says 'SBI card required' but user blocks SBI)
                if self.filter.contains_violation(validation_text, financial_rules):
                    self.log(search_id, self.worker.platform_id, "warning", f"Coupon {code} -> Price Rs. {new_price} but violates card rules: '{validation_text}' — SKIPPED")
                    results.append({
                        "code": code,
                        "status": "valid_but_excluded",
                        "price": new_price,
                        "reason": f"Violates card constraints: {validation_text}"
                    })

                    consecutive_failures = 0  # Reconstructed applied state successfully
                    if db:
                        await db.save_coupon_test_result(
                            code=code,
                            platform=self.worker.platform_id,
                            result="SUCCESS",
                            discount=baseline_price - new_price,
                            base_price=baseline_price,
                            route=route,
                            search_id=search_id,
                            error_msg=f"Card rules exclusion: {validation_text}"
                        )

                    # Clear selector to prepare for next test
                    await self.worker.clear_coupon_field(page)
                    continue

                # 9. Coupon is valid and conforms to financial whitelists
                savings = baseline_price - new_price
                
                net_savings, interest_cost, emi_warning = calculate_net_emi_savings(
                    coupon_code=code,
                    coupon_desc=coupon.get("description", ""),
                    requires_emi=coupon.get("requires_emi", False),
                    base_price=baseline_price,
                    face_discount=savings
                )
                
                self.log(search_id, self.worker.platform_id, "success", f"Coupon {code} -> Rs. {new_price} SUCCESS! Saved Rs. {net_savings} (Face savings: Rs. {savings}, Interest cost: Rs. {interest_cost})")

                results.append({
                    "code": code,
                    "status": "valid_match",
                    "price": new_price,
                    "savings": net_savings,
                    "face_savings": savings,
                    "interest_cost": interest_cost,
                    "emi_warning": emi_warning,
                    "terms": (validation_text + " " + emi_warning).strip()
                })

                consecutive_failures = 0
                if db:
                    await db.save_coupon_test_result(
                        code=code,
                        platform=self.worker.platform_id,
                        result="SUCCESS",
                        discount=net_savings,
                        base_price=baseline_price,
                        route=route,
                        search_id=search_id
                    )

                # If this is the best coupon so far based on net savings, keep it
                if net_savings > (baseline_price - best_price):
                    best_price = baseline_price - net_savings
                    best_coupon = code

            except Exception as e:
                self.log(search_id, self.worker.platform_id, "error", f"Coupon {code} -> Testing error: {e}")
                results.append({
                    "code": code,
                    "status": "error",
                    "reason": str(e)
                })

                consecutive_failures += 1
                if db:
                    await db.save_coupon_test_result(
                        code=code,
                        platform=self.worker.platform_id,
                        result="FAILED",
                        discount=None,
                        base_price=baseline_price,
                        route=route,
                        search_id=search_id,
                        error_msg=str(e)
                    )

            await self.human.random_delay(1500, 3000)

        # Re-apply the winning coupon at the end so it's ready for the user handoff
        if best_coupon:
            try:
                self.log(search_id, self.worker.platform_id, "info", f"Re-applying winning coupon: {best_coupon}")
                await self.worker.clear_coupon_field(page)
                await self.human.type_text(page, self.worker.coupon_selector, best_coupon)
                await self.worker.click_apply_coupon(page)
                await page.wait_for_timeout(3000)
            except Exception as e:
                self.log(search_id, self.worker.platform_id, "error", f"Failed to re-apply winning coupon {best_coupon} at the end: {e}")

        return {
            "baseline_price": baseline_price,
            "best_price": best_price,
            "best_coupon": best_coupon,
            "savings": baseline_price - best_price,
            "all_results": results
        }

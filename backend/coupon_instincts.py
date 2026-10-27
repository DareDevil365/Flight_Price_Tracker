import json
from loguru import logger
from api_key_manager import api_key_manager

class CouponInstinctsEngine:
    def __init__(self, db):
        self.db = db

    async def initialize(self):
        """Create coupon_audits table if not exists."""
        if not self.db or not self.db.db:
            return
        try:
            await self.db.db.execute("""
                CREATE TABLE IF NOT EXISTS coupon_audits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    search_id TEXT,
                    coupon_code TEXT,
                    platform TEXT,
                    base_price REAL,
                    calculated_discount REAL,
                    corrected_discount REAL,
                    was_corrected BOOLEAN,
                    reason TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await self.db.db.commit()
            logger.info("[CouponInstinctsEngine] Initialized coupon_audits table.")
        except Exception as e:
            logger.error(f"[CouponInstinctsEngine] Failed to create coupon_audits table: {e}")

    def evaluate_deal_sanity(self, base_price: float, discount: float, final_price: float, is_domestic: bool) -> tuple[bool, str]:
        """
        Evaluate if a coupon match is realistic using domain instincts.
        Returns (is_sane: bool, reason: str).
        """
        if discount <= 0:
            return True, "No discount applied"

        # Failsafe 1: Discount cannot exceed 90% of base price
        if discount >= base_price * 0.9:
            return False, f"Suspiciously high discount: ₹{discount} is >= 90% of base ₹{base_price}"

        # Failsafe 2: Flight price floor and max reasonable discounts
        if is_domestic:
            if final_price < 1500.0:
                return False, f"Domestic flight price ₹{final_price} is below floor limit ₹1500"
            # Capped at either flat 2000 or 35% of flight price
            max_allowed = max(2000.0, base_price * 0.35)
            if discount > max_allowed:
                return False, f"Domestic discount ₹{discount} exceeds max expected threshold (₹{max_allowed})"
        else:
            if final_price < 4500.0:
                return False, f"International flight price ₹{final_price} is below floor limit ₹4500"
            max_allowed = max(8000.0, base_price * 0.45)
            if discount > max_allowed:
                return False, f"International discount ₹{discount} exceeds max expected threshold (₹{max_allowed})"

        return True, "Passed basic heuristics"

    async def analyze_coupon_with_ai(self, coupon_code: str, coupon_desc: str, base_price: float, is_domestic: bool) -> dict:
        """
        Query Gemini 2.5 Pro to analyze the coupon terms and determine the true applicable discount and global parameters.
        """
        prompt = f"""
        You are an elite travel agent and financial coupon analyst. You have instincts about flight prices and ticket discounts.
        Analyze the applicability and value of this coupon:
        
        - Coupon Code: "{coupon_code}"
        - Coupon Description: "{coupon_desc}"
        - Current Flight Type: {"Domestic (within India)" if is_domestic else "International (from India / abroad)"}
        - Flight Ticket Base Price: Rs. {base_price}
        
        Real-world rules:
        1. Read the terms closely. If a coupon says "Get up to Rs 5000 off on international and flat Rs 400 off on domestic", and we are on a domestic flight, the applicable discount is Rs 400, NOT Rs 5000.
        2. Flat coupons cannot exceed the base price.
        3. If the coupon is explicitly NOT valid for the current flight type (e.g. says "valid on international flights only" but we are on domestic), then is_applicable should be false.
        
        Determine both the current flight-specific applicability/discount, and the general/global coupon parameters as specified in the description.
        
        Output strictly valid JSON with keys:
        - "is_applicable": (true/false) whether coupon applies to the current flight.
        - "applicable_discount_value": (number) the actual, true discount in Indian Rupees (INR) that applies to this specific flight base price.
        - "general_discount_type": ("FLAT" or "PERCENT") the global type of discount described by the coupon.
        - "general_discount_value": (number) the general value (e.g. 10 for 10%, 400 for Rs. 400 flat).
        - "general_max_discount": (number or null) the maximum discount limit in INR (e.g. 2000 for "up to Rs. 2000"), or null/999999 if no limit.
        - "general_min_booking_value": (number or null) the minimum booking value in INR required to use this coupon, or null/0 if none.
        - "reason": (string) brief explanation of your reasoning.
        
        Do not wrap in markdown or backticks.
        """
        
        async def make_call(client, model):
            logger.info(f"[CouponInstinctsEngine] Analyzing coupon {coupon_code} with model {model}...")
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a professional JSON-generating assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0
            )
            res_text = response.choices[0].message.content.strip()
            clean_res = res_text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_res)

        try:
            result = await api_key_manager.execute_with_retry("brute", make_call)
            logger.info(f"[CouponInstinctsEngine] AI analysis result for {coupon_code}: {result}")
            return result
        except Exception as e:
            logger.error(f"[CouponInstinctsEngine] AI coupon analysis failed: {e}")
            return {
                "is_applicable": True,
                "applicable_discount_value": 0.0,
                "discount_type": "FLAT",
                "reason": f"AI analysis failed: {str(e)}",
                "ai_failed": True
            }

    async def audit_and_correct(self, platform: str, coupon_code: str, base_price: float, calculated_discount: float, is_domestic: bool, search_id: str = "") -> float:
        """
        Audit a coupon match. If it fails sanity check, run AI analyzer and update the database.
        Returns the corrected discount amount (which will equal calculated_discount if no corrections were needed).
        """
        final_price = base_price - calculated_discount
        is_sane, reason = self.evaluate_deal_sanity(base_price, calculated_discount, final_price, is_domestic)
        if is_sane:
            return calculated_discount

        logger.warning(f"[CouponInstinctsEngine] Suspect calculation: platform={platform}, code={coupon_code}, base={base_price}, discount={calculated_discount}, final={final_price}. Reason: {reason}. Running self-improving AI correction...")

        # Retrieve coupon description from DB
        coupon_desc = ""
        if self.db:
            try:
                async with self.db.db.execute("SELECT description FROM coupons WHERE platform = ? AND code = ?", (platform, coupon_code)) as cur:
                    row = await cur.fetchone()
                    if row:
                        coupon_desc = row[0]
            except Exception as e:
                logger.error(f"Failed to fetch description for {coupon_code}: {e}")

        # AI analysis
        ai_res = await self.analyze_coupon_with_ai(coupon_code, coupon_desc, base_price, is_domestic)
        
        ai_failed = ai_res.get("ai_failed", False)
        corrected_discount = calculated_discount
        was_corrected = False
        audit_reason = reason

        if ai_failed:
            # AI failed (rate limit, etc). Log warning and return calculated_discount fallback instead of zeroing out
            logger.warning(f"[CouponInstinctsEngine] AI analysis failed for {coupon_code}. Falling back to calculated discount ₹{calculated_discount}.")
            corrected_discount = calculated_discount
            was_corrected = False
            audit_reason = f"AI analysis failed (Reason: {ai_res.get('reason')}). Falling back to calculated discount."
        elif not ai_res.get("is_applicable", True):
            # Coupon not applicable! Deactivate it
            corrected_discount = 0.0
            was_corrected = True
            audit_reason = f"AI marked invalid: {ai_res.get('reason')}"
            if self.db:
                try:
                    await self.db.db.execute("UPDATE coupons SET is_active = 0 WHERE platform = ? AND code = ?", (platform, coupon_code))
                    await self.db.db.commit()
                    logger.success(f"[CouponInstinctsEngine] Deactivated invalid coupon {coupon_code} for {platform} in DB.")
                except Exception as e:
                    logger.error(f"Failed to deactivate coupon in DB: {e}")
        else:
            corrected_discount = ai_res.get("applicable_discount_value", 0.0)
            
            if corrected_discount != calculated_discount:
                was_corrected = True
                audit_reason = f"AI adjusted discount to {corrected_discount} ({ai_res.get('reason')})"
                
                # Self-improve DB: Update the coupon value so future runs don't need AI call
                if self.db:
                    try:
                        gen_type = ai_res.get("general_discount_type", ai_res.get("discount_type", "FLAT"))
                        gen_val = ai_res.get("general_discount_value", ai_res.get("applicable_discount_value", 0.0))
                        gen_max = ai_res.get("general_max_discount")
                        gen_min = ai_res.get("general_min_booking_value")
                        
                        # Dynamically check columns to support mock db structure in tests
                        async with self.db.db.execute("PRAGMA table_info(coupons)") as cur:
                            columns = [row["name"] for row in await cur.fetchall()]
                        
                        update_fields = ["discount_type = ?", "discount_value = ?", "updated_at = CURRENT_TIMESTAMP"]
                        update_params = [gen_type, gen_val]
                        
                        if "max_discount" in columns and gen_max is not None:
                            update_fields.append("max_discount = ?")
                            update_params.append(gen_max)
                        if "min_booking_value" in columns and gen_min is not None:
                            update_fields.append("min_booking_value = ?")
                            update_params.append(gen_min)
                            
                        query = f"""
                            UPDATE coupons SET 
                                {', '.join(update_fields)}
                            WHERE platform = ? AND code = ?
                        """
                        update_params.extend([platform, coupon_code])
                        
                        await self.db.db.execute(query, tuple(update_params))
                        await self.db.db.commit()
                        logger.success(f"[CouponInstinctsEngine] Corrected coupon {coupon_code} parameters in DB: val={gen_val}, type={gen_type}.")
                    except Exception as e:
                        logger.error(f"Failed to update coupon in DB: {e}")

        # Save to audits log table
        if self.db:
            try:
                await self.db.db.execute(
                    """
                    INSERT INTO coupon_audits (search_id, coupon_code, platform, base_price, calculated_discount, corrected_discount, was_corrected, reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (search_id, coupon_code, platform, base_price, calculated_discount, corrected_discount, 1 if was_corrected else 0, audit_reason)
                )
                await self.db.db.commit()
            except Exception as e:
                logger.error(f"Failed to write coupon audit log: {e}")

        return corrected_discount

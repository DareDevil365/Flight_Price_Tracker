"""
Flight Finder — Text AI Rules Parser
Parses unstructured custom instructions (e.g. 'I hold an SBI Card, skip Yes Bank')
into structured whitelists/blacklists using heuristic keyword triggers or LLM.
"""

import os
from loguru import logger


class TextAI:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")

    async def parse_custom_instructions(self, text: str) -> list[dict]:
        """
        Parses raw text instructions into structured financial rules.
        """
        logger.info(f"[TextAI] Parsing custom text: '{text}'...")
        
        # Local keyword-based heuristic parsing (always runs as high-reliability fallback)
        rules = []
        text_upper = text.upper()

        # 1. Parse Whitelisted / Held cards
        whitelists = ["SBI", "HDFC", "ICICI", "AXIS", "KOTAK", "PNB", "BOB", "HSBC", "AMEX", "YES"]
        for bank in whitelists:
            if bank in text_upper and any(kw in text_upper for kw in [f"HOLD {bank}", f"HAVE {bank}", f"OWN {bank}", f"USE {bank}"]):
                rules.append({"type": "whitelist_bank", "bank": bank})
                logger.debug(f"[TextAI] Detected whitelisted bank: {bank}")

        # 2. Parse Blacklisted cards
        for bank in whitelists:
            if bank in text_upper and any(kw in text_upper for kw in [f"IGNORE {bank}", f"SKIP {bank}", f"BLOCK {bank}", f"EXCLUDE {bank}", "NO YES BANK"]):
                rules.append({"type": "blacklist_bank", "bank": bank})
                logger.debug(f"[TextAI] Detected blacklisted bank: {bank}")

        # 3. Parse EMI constraints
        if "NO EMI" in text_upper or "IGNORE EMI" in text_upper or "SKIP EMI" in text_upper or "WITHOUT EMI" in text_upper:
            rules.append({"type": "block_emi"})
            logger.debug("[TextAI] Detected block EMI request")

        # 4. Parse BNPL constraints
        if "NO BNPL" in text_upper or "SKIP BNPL" in text_upper or "IGNORE BNPL" in text_upper:
            rules.append({"type": "block_bnpl"})
            logger.debug("[TextAI] Detected block BNPL request")

        if not rules:
            # Default fallback if no keywords matched
            rules.append({"type": "raw_rule", "text": text})

        return rules

    async def parse_trip_nlp(self, query_text: str) -> dict:
        """
        Use Gemini to extract trip parameters from natural language query.
        """
        from api_key_manager import api_key_manager
        import json
        import datetime
        try:
            client, model, _ = api_key_manager.get_client("brute")
            prompt = f'''
            Extract flight search parameters from the following natural language query.
            Today's date is: 2026-06-21. Resolve any relative dates ("next Friday", "tomorrow") relative to this date.
            
            Query: "{query_text}"
            
            Return a JSON object with these exact keys:
            - origin (string: 3-letter IATA code, e.g. "DEL")
            - destination (string: 3-letter IATA code, e.g. "GOI")
            - departureDate (string: YYYY-MM-DD format)
            - returnDate (string or null: YYYY-MM-DD format)
            - cabinClass (string: "ECONOMY", "BUSINESS", "PREMIUM_ECONOMY", or "FIRST")
            - passengerCount (integer)
            
            If any parameter is missing, use reasonable defaults:
            - departureDate: 2026-06-28 (1 week from today)
            - cabinClass: "ECONOMY"
            - passengerCount: 1
            - returnDate: null
            
            Respond only with the JSON object, no markdown formatting or extra text.
            '''
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a flight search assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0
            )
            res_text = response.choices[0].message.content.strip()
            clean_res = res_text.replace("```json", "").replace("```", "").strip()
            result = json.loads(clean_res)
            logger.info(f"[TextAI] NLP Parsed result: {result}")
            return result
        except Exception as e:
            logger.error(f"[TextAI] NLP parsing failed: {e}")
            return {}


"""
Flight Finder — Vision Intake
Uses OpenAI / Gemini Vision API to extract flight intent details from screenshots of itineraries.
Includes fallback regex parsing or mock data triggers for offline/unset API keys.
"""

import os
import json
from loguru import logger


class VisionIntake:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")

    async def extract_trip_details(self, image_b64: str) -> dict:
        """
        Send base64 screenshot to Gemini Vision to extract structured travel criteria.
        """
        logger.info("[VisionIntake] Processing itinerary screenshot...")
        
        from api_key_manager import api_key_manager
        import json
        try:
            client, model, _ = api_key_manager.get_client("brute")
            prompt = f'''
            Today is {__import__('datetime').date.today().isoformat()}.
            Extract flight search parameters from the provided image.

            Return a JSON object with these exact keys:
            - origin (object with "code" string and "name" string)
            - destination (object with "code" string and "name" string)
            - departureDate (string: YYYY-MM-DD format)
            - returnDate (string or null: YYYY-MM-DD format)
            - passengerCount (integer)
            - cabinClass (string: "ECONOMY", "BUSINESS", "PREMIUM_ECONOMY", or "FIRST")
            - specificFlightNumber (string or null, e.g. "6E-2341")

            If any parameter is missing, use reasonable defaults:
            - departureDate: null (ask the user to enter a missing date)
            - cabinClass: "ECONOMY"
            - passengerCount: 1

            Respond only with the JSON object, no markdown formatting or extra text.
            '''
            
            # Note: image_b64 may include the "data:image/jpeg;base64," prefix
            if "base64," in image_b64:
                image_b64 = image_b64.split("base64,")[1]

            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a flight data extraction assistant."},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}"
                                },
                            },
                        ],
                    }
                ],
                temperature=0.0
            )
            
            res_text = response.choices[0].message.content.strip()
            clean_res = res_text.replace("```json", "").replace("```", "").strip()
            result = json.loads(clean_res)
            result["success"] = True
            result["message"] = "Trip details successfully extracted from screenshot."
            
            logger.info(f"[VisionIntake] Extracted result: {result}")
            return result
        except Exception as e:
            logger.error(f"[VisionIntake] Vision API request failed: {e}")
            return self._mock_extraction_fallback()

    def _mock_extraction_fallback(self) -> dict:
        return {'success':False,'message':'Could not extract this screenshot. Enter the trip manually or configure a vision-capable API.'}

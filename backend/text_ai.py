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
        from financial_text import financial_instructions
        parsed = financial_instructions(text)
        rules = []
        for key, kind, field in [('whitelisted_banks','whitelist_bank','bank'),
                                 ('blacklisted_banks','blacklist_bank','bank'),
                                 ('owned_card_names','owned_card','card'),
                                 ('excluded_card_names','excluded_card','card')]:
            rules.extend({'type':kind, field:value} for value in parsed[key])
        for key in ('only_upi','block_emi','block_bnpl'):
            if parsed[key]:
                rules.append({'type':key})
        return rules

    async def parse_trip_nlp(self, query_text: str) -> dict:
        """Resolve explicit airport/city pairs and ISO dates locally before optional AI."""
        import re
        import datetime
        if not isinstance(query_text,str) or not query_text.strip() or len(query_text)>2000:
            raise ValueError('Enter a short route/date request.')
        if re.search(r'\b(?:children|child|infants?|bab(?:y|ies))\b',query_text,re.I):
            raise ValueError('Only adult passengers are supported. Child and infant fares cannot be substituted with adult fares.')
        counts=re.findall(r'\b(\d+)\s*(?:adults?|people|passengers?|travellers?|travelers?)\b',query_text,re.I)
        if counts and (len(set(counts))!=1 or not 1<=int(counts[0])<=9):
            raise ValueError('Specify between one and nine adult passengers.')
        aliases = {'delhi':'DEL','new delhi':'DEL','chennai':'MAA','chennei':'MAA',
            'hyderabad':'HYD','jaipur':'JAI','mumbai':'BOM','bangalore':'BLR','bengaluru':'BLR',
            'dabolim':'GOI','mopa':'GOX','manohar':'GOX','kolkata':'CCU','kochi':'COK','pune':'PNQ'}
        from compiler import INDIAN_AIRPORT_CODES
        codes = INDIAN_AIRPORT_CODES | {'DXB','SIN','LHR','JFK'}
        tokens = list(re.finditer(r'\b(?:'+ '|'.join(sorted(aliases,key=len,reverse=True))+r'|'+ '|'.join(sorted(codes))+r')\b',query_text,re.I))
        airports = [aliases.get(m[0].lower(),m[0].upper()) for m in tokens]
        dates = re.findall(r'\b\d{4}-\d{2}-\d{2}\b',query_text)
        if not dates and re.search(r'\btomorrow\b',query_text,re.I):
            dates=[(datetime.date.today()+datetime.timedelta(days=1)).isoformat()]
        if len(airports)>2 or len(dates)>2 or re.search(r'\b(?:via|multi[ -]?city)\b',query_text,re.I):
            raise ValueError('Specify one directed airport pair. Use Explore for connections; multi-city requests are unsupported.')
        if len(airports)==2 and dates:
            if re.search(r'\b(?:return|round[ -]?trip)\b',query_text,re.I) and len(dates)!=2:
                raise ValueError('A round trip needs both departure and return dates.')
            cabin = 'PREMIUM_ECONOMY' if re.search('premium economy',query_text,re.I) else 'BUSINESS' if re.search('business',query_text,re.I) else 'FIRST' if re.search('first class',query_text,re.I) else 'ECONOMY'
            return dict(origin=airports[0],destination=airports[1],departureDate=dates[0],
                returnDate=dates[1] if len(dates)>1 else None,cabinClass=cabin,passengerCount=int(counts[0]) if counts else 1,
                maxStops=0 if re.search(r'non[ -]?stop|direct only',query_text,re.I) else int(re.search(r'\b([12])\s*stops?\b',query_text,re.I)[1]) if re.search(r'\b([12])\s*stops?\b',query_text,re.I) else None,
                preferredTime=next((name for name in ['MORNING','AFTERNOON','EVENING','NIGHT'] if name.lower() in query_text.lower()),'ANY'))
        from api_key_manager import api_key_manager
        import json
        try:
            client, model, _ = api_key_manager.get_client('brute')
            response = await client.chat.completions.create(model=model,temperature=0,
                messages=[{'role':'system','content':'Extract a flight trip as JSON with origin/destination IATA, departureDate/returnDate YYYY-MM-DD, cabinClass, passengerCount, maxStops (0 for nonstop, 1 or 2, otherwise null), preferredTime (ANY/MORNING/AFTERNOON/EVENING/NIGHT). Never invent missing airports or dates; use null. Today is '+datetime.date.today().isoformat()},
                          {'role':'user','content':query_text}])
            return json.loads(response.choices[0].message.content.strip().removeprefix('```json').removesuffix('```').strip())
        except Exception:
            raise ValueError('Enter a clear route and date, such as GOI to HYD on 2026-11-12. Goa has two airports: use GOI or GOX. Other phrasing requires a configured AI key.')

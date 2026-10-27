"""Public merchant and GrabOn discovery with bounded, independent requests.
Offer advertisements are candidates, never measured checkout savings.
"""
import asyncio
import json
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit
import aiohttp
from bs4 import BeautifulSoup
from loguru import logger
from offer_parser import published_offer


class CouponHarvester:
    def __init__(self, db):
        self.db = db
        self._locks = {}
        self._retry_after = {}
        self.last_status = {}
        self.source_status = {}

    async def _initialize_harvester_table(self):
        await self.db.db.execute("CREATE TABLE IF NOT EXISTS harvester_history (platform TEXT PRIMARY KEY, last_scraped_at TEXT NOT NULL)")
        await self.db.db.commit()

    async def should_harvest(self, platform, ttl_hours=6):
        await self._initialize_harvester_table()
        if self._retry_after.get(platform, datetime.min) > datetime.now():
            return False
        async with self.db.db.execute('SELECT last_scraped_at FROM harvester_history WHERE platform=?',(platform,)) as cur:
            row=await cur.fetchone()
        return not row or datetime.now()-datetime.fromisoformat(row[0]) >= timedelta(hours=ttl_hours)

    async def record_harvest(self, platform):
        # An explicit first refresh skips should_harvest(), including its table
        # initialization. Fresh installs must be able to record that refresh.
        await self._initialize_harvester_table()
        await self.db.db.execute("INSERT INTO harvester_history VALUES (?,?) ON CONFLICT(platform) DO UPDATE SET last_scraped_at=excluded.last_scraped_at",(platform,datetime.now().isoformat()))
        await self.db.db.commit()

    async def _harvest(self, platforms, force=False):
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async def collect(platform):
                if platform=='google_flights':
                    return []
                async with self._locks.setdefault(platform,asyncio.Lock()):
                    if not force and not await self.should_harvest(platform):
                        self.last_status.setdefault(platform, 'Using cached offers or waiting before retry')
                        return []
                    try:
                        offers=await self._crawl_platform_deals(platform,session)
                        if offers:
                            await self.db.add_coupons_batch(offers)
                            if any(s.startswith('Unavailable:') for s in self.source_status.get(platform,{}).values()):
                                self._retry_after[platform]=datetime.now()+timedelta(minutes=15)
                            else:
                                await self.record_harvest(platform)
                            self.last_status[platform]=f'{len(offers)} published codes discovered; checkout eligibility unverified. '+self._source_summary(platform)
                        else:
                            self._retry_after[platform]=datetime.now()+timedelta(minutes=15)
                            self.last_status[platform]='No explicit codes found; the source may require JavaScript or human verification. '+self._source_summary(platform)
                        return offers
                    except Exception as exc:
                        self._retry_after[platform]=datetime.now()+timedelta(minutes=15)
                        self.last_status[platform]=str(exc)
                        logger.warning(f'Offer discovery unavailable for {platform}: {exc}')
                        return []
            results=await asyncio.gather(*(collect(p) for p in dict.fromkeys(platforms)))
        return [offer for offers in results for offer in offers]

    async def quick_harvest(self, platforms):
        return await self._harvest(platforms)

    async def deep_harvest(self, platforms=None):
        # Explicit refresh retries a failed source rather than hiding it for six hours.
        return await self._harvest(platforms or ['makemytrip','easemytrip','cleartrip','yatra','paytm','ixigo'],force=True)

    async def _crawl_platform_deals(self, platform, session=None):
        if platform not in {'makemytrip','easemytrip','cleartrip','yatra','paytm','ixigo'}:
            return []
        if session is None:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as own:
                return await self._crawl_platform_deals(platform,own)
        self.source_status[platform]={}
        collectors=[('GrabOn',self._crawl_grabon(platform,session))]
        if platform=='easemytrip':
            # These static JSON files are linked by the public deals.html page;
            # they are advertisements, not private booking/payment endpoints.
            collectors.insert(0,('EaseMyTrip published flight offers',self._crawl_emt('flight',session)))
            collectors.insert(1,('EaseMyTrip published bank offers',self._crawl_emt('bank',session)))
        outcomes=await asyncio.gather(*(work for _,work in collectors),return_exceptions=True)
        offers={}
        for (label,_),outcome in zip(collectors,outcomes):
            if isinstance(outcome,BaseException):
                if isinstance(outcome,asyncio.CancelledError):raise outcome
                self.source_status[platform][label]='Unavailable: '+type(outcome).__name__
                continue
            self.source_status[platform][label]=f'{len(outcome)} explicit codes; advertised conditions only'
            for offer in outcome:
                # Public merchant descriptions take priority over third-party
                # duplicates. Current native checkout cards still take priority
                # over this entire database in Dispatcher.verify_checkout.
                offers.setdefault(offer['code'],offer)
        return list(offers.values())

    def _source_summary(self,platform):
        return '; '.join(f'{name}: {status}' for name,status in self.source_status.get(platform,{}).items())

    async def _crawl_emt(self,category,session):
        url=f'https://www.easemytrip.com/offers/offerjson/deals/{category}offers.json'
        async with session.get(url) as response:
            if response.status!=200:
                raise ValueError(f'Public merchant offer source returned HTTP {response.status}')
            if urlsplit(str(response.url)).hostname!='www.easemytrip.com':
                raise ValueError('Public merchant offer source redirected off its expected host')
            payload=bytearray()
            async for chunk in response.content.iter_chunked(16384):
                payload.extend(chunk)
                if len(payload)>450000:
                    raise ValueError('Public merchant offer source exceeds the read limit')
            rows=json.loads(payload)
        return self.parse_emt_feed(rows,url)

    @staticmethod
    def parse_emt_feed(rows,source_url):
        from offer_rules import parse_date
        from compiler import is_flight_coupon
        import re
        if not isinstance(rows,list) or len(rows)>1000:
            raise ValueError('Unrecognized public merchant offer feed')
        offers={}
        for row in rows:
            if not isinstance(row,dict):continue
            code=row.get('promoCode')
            if not isinstance(code,str) or not code.strip():continue
            # Never infer a coupon from a URL, heading, airline or fare amount.
            text='\n'.join(str(row.get(key) or '') for key in ('title','description'))
            if len(text)>8000 or not is_flight_coupon(code,text):continue
            offer=published_offer('easemytrip',code,text,source_url,native=True)
            if not offer:continue
            offer.update(evidence_kind='public_http',eligibility_unconfirmed=True)
            # A listing is not complete terms, even if it calls a code active.
            # Retain its published expiry without assuming it is the travel date.
            validity=str(row.get('validity') or '').strip()
            expiry=parse_date(re.sub(r'^(?:valid\s+till\s*:?|till)\s*','',validity,flags=re.I))
            if expiry:offer['valid_until']=expiry.isoformat()
            try:
                target=urlsplit(str(row.get('url') or ''))
                if target.scheme=='https' and target.hostname=='www.easemytrip.com' and not target.username and target.port in (None,443) and target.path.startswith('/offers/'):
                    offer['terms_url']=urlunsplit((target.scheme,target.netloc,target.path,'',''))
            except ValueError:
                pass  # A malformed detail link cannot become a navigation target.
            offers.setdefault(offer['code'],offer)
        return list(offers.values())

    async def _crawl_grabon(self,platform,session):
        slug='paytm-flights' if platform=='paytm' else platform
        url=f'https://www.grabon.in/{slug}-coupons/'
        async with session.get(url) as response:
            if response.status!=200:
                raise ValueError(f'Public offer source returned HTTP {response.status}')
            soup=BeautifulSoup(await response.text(),'html.parser')
        return self.parse_grabon(soup,platform,url)

    @staticmethod
    def parse_grabon(soup,platform,url):
        from compiler import is_flight_coupon
        offers={}
        # Related merchants are embedded in this page. Only its main coupon
        # cards belong to the requested company; button parents omit the terms.
        for element in soup.select('.gc-box .gcbr[data-code]'):
            parent=element.find_parent(class_='gc-box')
            if parent.find_parent(class_='suggested-coupons-boxes') or 'su' in parent.get('class',[]):
                continue
            text=parent.get_text(' ',strip=True)
            code=element.get('data-code','').strip()
            if not is_flight_coupon(code,text):
                continue
            offer=published_offer(platform,code,text,url)
            if offer:
                offers[offer['code']]=offer
        return list(offers.values())

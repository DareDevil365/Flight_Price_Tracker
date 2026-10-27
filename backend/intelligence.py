"""Sourced market context and explainable advice; news never invents flight prices."""
import asyncio
import csv
import io
import json
import math
import re
import statistics
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urlparse
import aiohttp
from quotes import utc_now
from advisor_evidence import observed_timestamp, fresh_timestamp, history_rows, matching_quote
from quote_contract import positive_amount
from evidence_feeds import (ATF_URL, AAI_URL, fred_points, atf_html, aai_links,
    aai_pdf, fetch_bytes, source_metadata, source_document_metadata, merge_source_documents)

SCHEMA = '''
CREATE TABLE IF NOT EXISTS intelligence_cache (
  key TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS offer_observations (
  id INTEGER PRIMARY KEY, platform TEXT, code TEXT, description TEXT, valid_from TEXT,
  valid_until TEXT, source_url TEXT, observed_day TEXT,
  UNIQUE(platform,code,description,observed_day));
CREATE TABLE IF NOT EXISTS red_room (
  id TEXT PRIMARY KEY, request TEXT NOT NULL, interval_hours INTEGER NOT NULL,
  created_at TEXT NOT NULL, last_checked TEXT, last_price REAL, report TEXT,
  last_alert_key TEXT, last_error TEXT, is_active INTEGER DEFAULT 1);
'''


class PriceSeries(list):
    """Retain coverage information instead of hiding missing providers from validation."""
    coverage_stable = True
    providers = None


def sourced_url(value,domains=None):
    if not isinstance(value,str):
        return False
    try:
        parsed=urlparse(value)
        return isinstance(value,str) and parsed.scheme=='https' and bool(parsed.hostname) and not parsed.username and (domains is None or parsed.hostname in domains)
    except (TypeError,ValueError):
        return False


def context_payload(cache,key,expected,problems):
    wrapper=cache.get(key,{})
    value=wrapper.get('data',expected()) if isinstance(wrapper,dict) else None
    if isinstance(value,expected):
        return value
    problems.append(f'{key}: malformed cached payload was excluded.')
    return expected()


def daily_prices(rows):
    """Repeated scrapes are one day's evidence, not independent training samples."""
    days = {}
    valid=[]
    for row in rows:
        if not isinstance(row,dict):
            continue
        stamp=observed_timestamp(row.get('observed_at'))
        # Date-only fixtures represent a dated daily observation, never a live quote.
        try:
            day=stamp.date() if stamp else date.fromisoformat(row.get('observed_at',''))
        except (TypeError,ValueError):
            continue
        if day>date.today() or (stamp and stamp>datetime.now(timezone.utc)) or not positive_amount(row.get('price')):
            continue
        valid.append({**row,'day':day.isoformat()})
    rows=valid
    # A disappearing cheap website must not look like a market-wide increase.
    providers={}
    for row in rows:
        if row.get('platform'):
            providers.setdefault(row['day'],set()).add(row['platform'])
    common=set.intersection(*providers.values()) if providers else None
    if common is not None:
        rows=[r for r in rows if r.get('platform') in common]
    for row in rows:
        day = row['day']
        days[day] = min(days.get(day, math.inf), row['price'])
    result=PriceSeries((date.fromisoformat(day),price) for day,price in sorted(days.items()))
    result.providers=common
    # The intersection is useful for describing comparable past prices, but its
    # membership uses later coverage. Do not use it to claim leakage-free backtests.
    result.coverage_stable=not providers or all(v==next(iter(providers.values())) for v in providers.values())
    return result


def slope_forecast(points, target):
    if not points or not isinstance(target,date):
        return None
    recent = points[-14:]
    if any(not isinstance(d,date) or not positive_amount(p) for d,p in recent):
        return None
    if any(a[0]>=b[0] for a,b in zip(recent,recent[1:])) or target<=recent[-1][0]:
        return None
    slopes = [(b[1]-a[1])/(b[0]-a[0]).days for i,a in enumerate(recent) for b in recent[i+1:] if b[0]!=a[0]]
    slope = statistics.median(slopes) if slopes else 0
    estimate=recent[-1][1]+slope*(target-recent[-1][0]).days
    return estimate if math.isfinite(estimate) and estimate>0 else None


def forecast_readiness(points, weekly_outcomes=0, last_validation_target=None, status='INSUFFICIENT_DATA'):
    """Report evidence requirements using dates only; no future prices are fabricated.

    Earliest dates are conditional evidence milestones. Even perfectly continuous
    collection cannot guarantee that a model ever beats the persistence baseline.
    """
    observed=len(points)
    report=dict(observed_days=observed,training_days_required=21,
        training_days_remaining=max(0,21-observed),weekly_outcomes_observed=weekly_outcomes,
        weekly_outcomes_required_for_forecast=7,weekly_outcomes_required_for_certainty=20,
        weekly_outcomes_remaining_for_forecast=max(0,7-weekly_outcomes),
        weekly_outcomes_remaining_for_certainty=max(0,20-weekly_outcomes),
        minimum_additional_daily_observations_for_forecast=None,
        minimum_additional_daily_observations_for_certainty=None,
        earliest_forecast_evidence_date=None,earliest_certainty_evidence_date=None,
        blockers=[],assumptions=[
            'Successful accepted observations on each collection day for this exact directed route, travel date, passengers, cabin and preferences.',
            'Unchanged comparable provider coverage; repeated scrapes on one day count as one observation day.',
            'Future seven-day outcomes produce valid model projections and a fresh model beats the last-price baseline by at least 10%.',
            'The newest measured seven-day validation outcome must be no more than fourteen days old; a fresh quote does not refresh old accuracy.',
            'Dates are earliest evidence milestones, not promised prediction or certainty dates. The model may never qualify.'])
    valid=all(type(day) is date and day<=date.today() and positive_amount(price) for day,price in points)
    valid=valid and all(a[0]<b[0] for a,b in zip(points,points[1:]))
    if not valid:
        report['blockers'].append('Invalid, future, duplicated or unordered history must be corrected before estimating readiness.')
        return report
    if not getattr(points,'coverage_stable',True):
        report['blockers'].append('Provider coverage changed. A genuinely comparable collection cohort is required; adding rows alone cannot validate the retrospective cohort.')
        return report
    if report['training_days_remaining']:
        report['blockers'].append(f"{report['training_days_remaining']} more distinct accepted training observation days are needed.")
    if weekly_outcomes<7:
        report['blockers'].append(f'{7-weekly_outcomes} more non-overlapping seven-day outcomes are needed before testing the forecast gate.')
    if weekly_outcomes<20:
        report['blockers'].append(f'{20-weekly_outcomes} more non-overlapping seven-day outcomes are needed for a percentage certainty meter.')
    if points and (date.today()-points[-1][0]).days>2:
        report['blockers'].append('The latest accepted observation is stale; collect a fresh exact-trip fare.')
    if status!='LOCAL_HOLDOUT_PASSED':
        report['blockers'].append('The forecast has not passed the recent accuracy and freshness gate; data counts alone do not enable it.')
    dates=[day for day,price in points]
    first_collection=date.today() if not dates or dates[-1]<date.today() else date.today()+timedelta(days=1)
    # One date per assumed future successful daily collection. Values deliberately
    # remain absent: this is a calendar calculation, never a synthetic training set.
    future=[first_collection+timedelta(days=offset) for offset in range(182)]
    schedule=dates+future
    available=set(schedule)
    count=weekly_outcomes
    next_origin=last_validation_target
    for label,required in [('forecast',7),('certainty',20)]:
        if weekly_outcomes>=required:
            report[f'minimum_additional_daily_observations_for_{label}']=0
            report[f'earliest_{label}_evidence_date']=date.today().isoformat()
    for origin in schedule[20:]:
        if next_origin and origin<next_origin:
            continue
        target=origin+timedelta(days=7)
        if target<=date.today() or target not in available:
            continue
        count+=1
        next_origin=target
        for label,required in [('forecast',7),('certainty',20)]:
            if count>=required and report[f'earliest_{label}_evidence_date'] is None:
                report[f'earliest_{label}_evidence_date']=target.isoformat()
                report[f'minimum_additional_daily_observations_for_{label}']=(target-first_collection).days+1
        if count>=20:
            break
    if status=='STALE_VALIDATION_WITHHELD':
        # Completed counts are retained, but a new outcome cannot exist today
        # merely because monitoring resumed. Report the earliest actual pending
        # seven-day target, conditional on successful daily collection.
        pending=[origin+timedelta(days=7) for origin in schedule[20:]
            if origin+timedelta(days=7)>date.today()]
        if pending:
            target=min(pending)
            for label,required in [('forecast',7),('certainty',20)]:
                if weekly_outcomes>=required:
                    report[f'earliest_{label}_evidence_date']=target.isoformat()
                    report[f'minimum_additional_daily_observations_for_{label}']=(target-first_collection).days+1
    return report


def calibrated_trend(points):
    result = dict(status='INSUFFICIENT_DATA',observed_days=len(points),forecast_7d=None,
                  model_mae=None,baseline_mae=None,confidence=None,
                  certainty=dict(percent=None,sample_count=0,range=None,scope='Future fare direction',explanation='Not calibrated. More independent seven-day outcomes are needed.'))
    result['readiness']=forecast_readiness(points)
    if any(not isinstance(d,date) or not positive_amount(p) or d>date.today() for d,p in points) or any(a[0]>=b[0] for a,b in zip(points,points[1:])):
        result['status']='INVALID_DATA_WITHHELD'
        return result
    if not getattr(points,'coverage_stable',True):
        result['status']='COVERAGE_CHANGED_WITHHELD'
        result['certainty']['explanation']='Not calibrated. Provider coverage changed; retrospective cohort selection cannot establish independent forecast accuracy.'
        return result
    # A fresh quote must not reactivate months-old validation after monitoring
    # stopped. Restart only the forecast cohort after a gap beyond its horizon;
    # stored accepted history remains available for descriptive comparisons.
    # Seven days is a conservative collection policy, not a fitted confidence.
    restart=next((i for i in range(len(points)-1,0,-1)
        if (points[i][0]-points[i-1][0]).days>7),0)
    if restart:
        points=points[restart:]
        result.update(observed_days=len(points),historical_observed_days=len(points)+restart,
            collection_restart_date=points[0][0].isoformat(),excluded_pre_gap_days=restart)
        result['readiness']=forecast_readiness(points)
        result['readiness'].update(collection_restart_date=points[0][0].isoformat(),
            prior_observations_excluded_after_gap=restart,maximum_collection_gap_days=7)
        result['readiness']['blockers'].append(
            f'Collection resumed on {points[0][0].isoformat()} after a gap longer than seven days. '
            f'{restart} older observation days are retained as history but excluded from this forecast validation cohort.')
    if len(points)<21 or (points[-1][0]-points[0][0]).days<20:
        return result
    model, baseline = [], []
    # Validate the actual forecast horizon using non-overlapping weekly outcomes.
    # The meter is historical directional accuracy, never a probability that news
    # caused a fare change. Do not publish a percentage from a handful of trials.
    hits=[]
    latest_validation_target=None
    next_origin=None
    for i in range(20,len(points)):
        if next_origin and points[i][0]<next_origin:
            continue
        target=points[i][0]+timedelta(days=7)
        outcome=next((p for p in points[i+1:] if p[0]==target),None)
        if not outcome:
            continue
        predicted=slope_forecast(points[:i+1],target)
        if predicted is None:
            continue
        next_origin=target
        estimated=predicted/points[i][1]-1
        actual=outcome[1]/points[i][1]-1
        model.append(abs(predicted-outcome[1]))
        baseline.append(abs(points[i][1]-outcome[1]))
        direction=lambda v:1 if v>.02 else -1 if v<-.02 else 0
        hits.append(direction(estimated)==direction(actual))
        latest_validation_target=target
    if len(model)>=7:
        mae, naive = statistics.mean(model[-20:]), statistics.mean(baseline[-20:])
        result.update(model_mae=round(mae,2),baseline_mae=round(naive,2),status='BASELINE_PREFERRED')
        if latest_validation_target and (date.today()-latest_validation_target).days>14:
            result['status']='STALE_VALIDATION_WITHHELD'
            result['certainty']['explanation']='Not calibrated for current conditions. The latest seven-day validation outcome is more than fourteen days old; a fresh quote alone cannot refresh measured accuracy.'
        elif naive>0 and mae<naive*.9 and (date.today()-points[-1][0]).days<=2:
            projected=slope_forecast(points,points[-1][0]+timedelta(days=7))
            if projected is not None:
                result.update(status='LOCAL_HOLDOUT_PASSED',forecast_7d=round(projected,2),confidence='LOW')
            else:
                result['status']='INVALID_PROJECTION_WITHHELD'
    result['certainty']['sample_count']=len(hits)
    if len(hits)>=20 and result['status']=='LOCAL_HOLDOUT_PASSED':
        # The meter and MAE gate describe the same recent outcomes, not separate
        # regimes with an old impressive success rate hiding recent mistakes.
        hits=hits[-20:]
        n=len(hits);p=sum(hits)/n;z=1.96
        center=(p+z*z/(2*n))/(1+z*z/n)
        margin=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
        result['certainty'].update(percent=round(p*100),range=[round((center-margin)*100),round((center+margin)*100)],
            explanation='Historical seven-day directional accuracy on non-overlapping outcomes. The 95% Wilson interval assumes independent outcomes; serial correlation can make it too narrow. It is not a guarantee for this trip or causal news attribution.')
        result['certainty']['sample_count']=n
    if result['forecast_7d'] is not None:
        result.update(forecast_as_of=points[-1][0].isoformat(),forecast_target_date=(points[-1][0]+timedelta(days=7)).isoformat())
    result['validation_outcomes']=len(model)
    result['latest_validation_outcome_date']=latest_validation_target.isoformat() if latest_validation_target else None
    result['readiness']=forecast_readiness(points,len(model),next_origin,result['status'])
    if result['status']=='STALE_VALIDATION_WITHHELD':
        result['readiness']['blockers'].append(
            'The latest measured seven-day outcome is more than fourteen days old. '
            'Collect a new matched weekly outcome and pass the accuracy gate; old outcome counts alone cannot restore the forecast.')
    if restart:
        result['readiness'].update(collection_restart_date=points[0][0].isoformat(),
            prior_observations_excluded_after_gap=restart,maximum_collection_gap_days=7)
        result['readiness']['assumptions'].append(
            'Forecast training and holdouts restart after a collection gap longer than the seven-day forecast horizon; older accepted fares remain stored.')
    return result


def constrain_forecast_to_trip(forecast,departure_date):
    """A price forecast after departure is not actionable booking advice."""
    departure=date.fromisoformat(departure_date)
    readiness=forecast.get('readiness',{})
    readiness['trip_departure_date']=departure_date
    for label in ('forecast','certainty'):
        milestone=readiness.get(f'earliest_{label}_evidence_date')
        before=date.fromisoformat(milestone)<departure if milestone else None
        readiness[f'{label}_evidence_possible_before_departure']=before
        if before is False:
            readiness.setdefault('blockers',[]).append(
                f'The earliest {label} evidence milestone ({milestone}) is on or after departure ({departure_date}). '
                'Use current exact-trip comparisons and target-price monitoring; these counts cannot mature before this flight.')
    target=forecast.get('forecast_target_date')
    if target and date.fromisoformat(target)>=departure:
        forecast.update(status='DEPARTURE_BEFORE_FORECAST_HORIZON',forecast_7d=None,confidence=None)
        certainty=forecast.get('certainty',{})
        certainty.update(percent=None,range=None,
            explanation='A seven-day prediction would reach or pass this trip’s departure. No future price or certainty percentage is presented for it.')
        readiness.setdefault('blockers',[]).append(
            f'The forecast target ({target}) reaches or passes departure ({departure_date}); that prediction is withheld.')
    return forecast


class MarketContext:
    def __init__(self,db):
        self.db=db
        self._lock=asyncio.Lock()

    async def initialize(self):
        await self.db.db.executescript(SCHEMA)
        async with self.db.db.execute('PRAGMA table_info(red_room)') as cursor:
            columns=[r['name'] for r in await cursor.fetchall()]
        if 'last_error' not in columns:
            await self.db.db.execute('ALTER TABLE red_room ADD COLUMN last_error TEXT')
        # Full-text retrieval is local and grounded in stored source metadata.
        await self.db.db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(title,kind,source_url,content='knowledge_sources',content_rowid='id')")
        await self.db.db.commit()

    async def snapshot(self):
        async with self.db.db.execute('SELECT * FROM intelligence_cache') as cursor:
            rows=await cursor.fetchall()
        return {r['key']:dict(data=json.loads(r['payload']),updated_at=r['updated_at']) for r in rows}

    async def _save(self,key,value):
        await self.db.db.execute('INSERT INTO intelligence_cache VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at',
            (key,json.dumps(value),utc_now()))
        if isinstance(value,list):
            for article in value:
                await self.db.db.execute('INSERT INTO knowledge_sources (kind,title,source_url,published_at,observed_at,payload) VALUES (?,?,?,?,?,?) ON CONFLICT(kind,source_url,title) DO UPDATE SET observed_at=excluded.observed_at,payload=excluded.payload',
                    (key,article['title'],article['url'],article.get('published_at'),utc_now(),json.dumps(article)))
            await self.db.db.execute("INSERT INTO knowledge_fts(knowledge_fts) VALUES ('rebuild')")
        await self.db.db.commit()

    async def refresh(self,force=False,archive=False):
        async with self._lock:
            cache=await self.snapshot()
            entry=cache.get('feed_status',{})
            fresh=observed_timestamp(entry.get('updated_at')) if isinstance(entry,dict) else None
            if not force and fresh and timedelta(0)<=datetime.now(timezone.utc)-fresh<timedelta(hours=6):
                return cache
            status={}
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
                async def series(code,name,units):
                    entry=cache.get(name,{})
                    previous=entry.get('data',{}) if isinstance(entry,dict) else {}
                    if not isinstance(previous,dict):
                        previous={}
                    if not isinstance(previous.get('observations',[]),list):
                        previous={**previous,'observations':[]}
                    begin='2023-01-01'
                    if previous.get('parser_version')==1 and previous.get('observations'):
                        try:
                            begin=(date.fromisoformat(previous['observations'][-1]['date'])-timedelta(days=14)).isoformat()
                        except (ValueError,KeyError,TypeError):
                            pass
                    url='https://fred.stlouisfed.org/graph/fredgraph.csv?'+urlencode(dict(id=code,cosd=begin))
                    try:
                        body=await fetch_bytes(session,url,1_000_000)
                        raw=body.decode('utf-8-sig')
                        points=fred_points(raw,code)
                        old={r['date']:r for r in previous.get('observations',[]) if isinstance(r,dict) and isinstance(r.get('date'),str) and '2023-01-01'<=r['date']<=date.today().isoformat() and positive_amount(r.get('value'))} if previous.get('parser_version')==1 else {}
                        old.update({p['date']:p for p in points})
                        document=source_document_metadata(body,'https://fred.stlouisfed.org/series/'+code,points,download_url=url)
                        await self._save(name,merge_source_documents(previous,[document],
                            series=code,units=units,observations=[old[d] for d in sorted(old)],
                            scope='Global cost context for Indian fares; not route fare training data',as_of=points[-1]['date']))
                        status[name]=f'Updated; {len(old)} dated context observations'
                    except Exception as exc:
                        status[name]=f'Unavailable: {type(exc).__name__}. Cached data, if any, retains its date.'
                async def traffic():
                    try:
                        index=(await fetch_bytes(session,AAI_URL,2_000_000)).decode('utf-8',errors='replace')
                        urls=aai_links(index)[:8 if archive else 2]
                        semaphore=asyncio.Semaphore(2)
                        async def report(url):
                            async with semaphore:
                                try:
                                    raw=await fetch_bytes(session,url)
                                    rows=await asyncio.to_thread(aai_pdf,raw,url)
                                    return rows,dict(**source_document_metadata(raw,url,rows,'period_end'),period_end=rows[0]['period_end']),None
                                except Exception as exc:
                                    return [],None,dict(source_url=url,error=f'{type(exc).__name__}: {exc}')
                        reports=await asyncio.gather(*(report(url) for url in urls))
                        entry=cache.get('airport_traffic',{})
                        previous=entry.get('data',{}) if isinstance(entry,dict) else {}
                        if not isinstance(previous,dict):
                            previous={}
                        if not isinstance(previous.get('observations',[]),list):
                            previous={**previous,'observations':[]}
                        if not isinstance(previous.get('reports',[]),list):
                            previous={**previous,'reports':[]}
                        merged={(r['airport'],r['period_month']):r for r in previous.get('observations',[]) if isinstance(r,dict) and r.get('airport') and r.get('period_month')} if previous.get('parser_version')==1 else {}
                        metadata={r['source_url']:r for r in previous.get('reports',[]) if isinstance(r,dict) and r.get('source_url')}
                        accepted=0;failures=[];documents=[]
                        for rows,provenance,error in reports:
                            if error:
                                failures.append(error)
                            if rows:
                                accepted+=1;metadata[provenance['source_url']]=provenance
                                documents.append(provenance)
                                merged.update({(r['airport'],r['period_month']):r for r in rows})
                        if not accepted:
                            raise ValueError('No passenger report passed header/row validation')
                        observations=sorted(merged.values(),key=lambda r:(r['period_end'],r['airport']))
                        prior_documents=previous.get('source_documents',[]) if isinstance(previous.get('source_documents'),list) else []
                        provenance_previous={**previous,'source_documents':prior_documents+previous['reports']} if 'reports' in previous else previous
                        await self._save('airport_traffic',merge_source_documents(provenance_previous,documents,source_url=AAI_URL,parser_version=1,units='Domestic passenger movements (arrivals plus departures)',
                            observations=observations,reports=list(metadata.values()),failed_reports=failures,as_of=observations[-1]['period_end'],
                            scope='Airport-level observed movements. Not directed route demand, seat inventory or unique travellers. Subject to AAI revisions.'))
                        status['airport_traffic']=f'{accepted} published reports validated; {len(observations)} airport-month rows; {len(failures)} reports unavailable'
                    except Exception as exc:
                        status['airport_traffic']=f'Unavailable: {type(exc).__name__}. Cached traffic retains reporting months.'
                async def feed(name,url,primary):
                    try:
                        raw=await fetch_bytes(session,url,2_000_000)
                        root=ET.fromstring(raw)
                        news=[]
                        for item in root.findall('.//item')[:40]:
                            title=item.findtext('title') or ''
                            published=item.findtext('pubDate') or ''
                            try:
                                day=parsedate_to_datetime(published).astimezone(timezone.utc).isoformat()
                            except (ValueError,TypeError):
                                continue
                            if datetime.fromisoformat(day)>datetime.now(timezone.utc):
                                continue
                            if not re.search(r'oil|crude|fuel|aviation|airline|flight|airfare|war|conflict|airspace',title,re.I):
                                continue
                            link=item.findtext('link') or ''
                            if link.startswith('https://'):
                                news.append(dict(title=title[:300],url=link,published_at=day,primary_source=primary))
                        await self._save(name,news)
                        status[name]=f'{len(news)} relevant dated headlines'
                    except Exception as exc:
                        status[name]=f'Unavailable: {type(exc).__name__}'
                from carrier_context import refresh_atf,refresh_capacity
                await asyncio.gather(series('DCOILBRENTEU','brent','USD/barrel (crude oil proxy, not Indian jet fuel)'),
                    series('DEXINUS','usd_inr','INR per USD'),
                    refresh_atf(self,session,status),refresh_capacity(self,session,status),traffic(),
                    feed('energy_news','https://www.eia.gov/rss/todayinenergy.xml',True),
                    feed('aviation_news','https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3',True),
                    feed('reported_news','https://news.google.com/rss/search?'+urlencode(dict(q='India aviation fuel airfare airspace war when:7d',hl='en-IN',gl='IN',ceid='IN:en')),False))
            await self._save('feed_status',status)
            return await self.snapshot()


class SuggestionBrain:
    def __init__(self,db,context):
        self.db,self.context=db,context
        self.checkout_session_valid=None

    async def assess(self,trip,financial=None,target_price=None,current_quotes=None):
        financial=financial or {}
        if target_price is None:
            target_price=financial.get('max_final_price')
        if target_price is not None and not positive_amount(target_price):
            raise ValueError('Target price must be a finite positive INR amount')
        route=trip['origin']+'-'+trip['destination']
        days=(date.fromisoformat(trip['departure_date'])-date.today()).days
        round_trip=trip.get('trip_type')=='round_trip'
        if days<0:
            raise ValueError('Travel date must be today or later')
        rows=await self.db.get_quotes(route,trip['departure_date'],trip['passenger_count'],trip['cabin_class'],preferred_time=trip.get('preferred_time','ANY'),max_stops=trip.get('max_stops'))
        rows=history_rows(rows,trip)
        # Payment/add-on choices vary between checkouts. Forecast only listed
        # market fares; use a current eligible checkout as the buying comparator.
        series=[r for r in rows if r['verification']=='listed']
        points=daily_prices(series)
        forecast=constrain_forecast_to_trip(calibrated_trend(points),trip['departure_date'])
        fresh=[r for r in series if fresh_timestamp(r['observed_at'])]
        if current_quotes is not None:
            # Restored search results can contain yesterday's valid evidence.
            # Recheck freshness at the recommendation boundary, not just scraping.
            current_quotes=[r for r in current_quotes if matching_quote(r,trip)]
            current_quotes=[r for r in current_quotes
                if r['savings_breakdown']['verification']!='checkout' or
                (self.checkout_session_valid is not None and self.checkout_session_valid(r) is True)]
            # Recheck explicit after-search exclusions at this decision boundary.
            if financial:
                from deal_feedback import available_result
                offers=[]
                for platform in {r['platform'] for r in current_quotes}:
                    offers.extend(await self.db.get_live_coupons(platform))
                current_quotes=[r for r in current_quotes if available_result(r,financial,offers)]
            fresh=[dict(price=r['final_price'],platform=r['platform'],verification=r['savings_breakdown']['verification']) for r in current_quotes
                ]
            fresh=[r for r in fresh if isinstance(r['price'],(int,float)) and not isinstance(r['price'],bool) and math.isfinite(r['price']) and r['price']>0]
        fresh_verified=[r for r in fresh if r['verification']=='checkout']
        best=min(fresh_verified or fresh,key=lambda r:r['price']) if fresh else None
        market_best=min((r for r in fresh if r['verification']=='listed'),key=lambda r:r['price'],default=None)
        if current_quotes is not None:
            from quote_contract import listed_amount
            snapshots=[dict(price=listed_amount(r),platform=r['platform'],verification='listed') for r in current_quotes
                if matching_quote(r,trip,listing=True) and listed_amount(r) is not None]
            market_best=min(snapshots,key=lambda r:r['price'],default=None)
        if points.providers is not None and market_best and market_best['platform'] not in points.providers:
            market_best=None
        cache=await self.context.snapshot()
        context_problems=[]
        if not isinstance(cache,dict):
            cache={}
            context_problems.append('Malformed market cache was excluded; no context was used.')
        factors=[]
        news=[]
        cost_pressure=False
        for name,label in [('brent','Crude oil'),('usd_inr','USD/INR')]:
            series_data=context_payload(cache,name,dict,context_problems)
            if series_data and (not sourced_url(series_data.get('source_url'),{'fred.stlouisfed.org'}) or not isinstance(series_data.get('units'),str)):
                context_problems.append(f'{name}: missing primary source or units; excluded.')
                continue
            values=[]
            for value in series_data.get('observations',[]) if isinstance(series_data.get('observations',[]),list) else []:
                try:
                    day=date.fromisoformat(value['date'])
                    if day<=date.today() and positive_amount(value.get('value')):
                        values.append(value)
                except (KeyError,TypeError,ValueError):
                    continue
            values.sort(key=lambda value:value['date'])
            if values:
                latest=values[-1]
                reference=next((x for x in reversed(values) if 30<=(date.fromisoformat(latest['date'])-date.fromisoformat(x['date'])).days<=37),None)
                change=(latest['value']/reference['value']-1)*100 if reference else None
                stale=(date.today()-date.fromisoformat(latest['date'])).days>7
                cost_pressure |= bool(not stale and change is not None and change>(10 if name=='brent' else 3))
                factors.append(dict(kind=name,title=label,value=latest['value'],units=series_data.get('units'),as_of=latest['date'],change_30d_pct=round(change,2) if change is not None else None,
                    comparison_date=reference['date'] if reference else None,comparison_days=(date.fromisoformat(latest['date'])-date.fromisoformat(reference['date'])).days if reference else None,
                    stale=stale,source_url=series_data.get('source_url'),interpretation='Cost context; does not establish when or whether this flight fare will change.'))
        # Additional primary context stays descriptive: no conversion from fuel
        # or airport counts to a claimed route fare, certainty or BUY signal.
        atf=context_payload(cache,'indian_atf',dict,context_problems)
        for city in ('Delhi','Mumbai','Kolkata','Chennai'):
            values=[]
            for row in atf.get('observations',[]) if isinstance(atf.get('observations',[]),list) else []:
                if not isinstance(row,dict):
                    continue
                try:
                    if row.get('city')==city and date.fromisoformat(row['date'])<=date.today() and positive_amount(row.get('value')) and row.get('units',atf.get('units'))=='INR/kilolitre' and sourced_url(row.get('source_url') or atf.get('source_url'),{'iocl.com','www.iocl.com'}):
                        values.append(row)
                except (TypeError,ValueError,KeyError):
                    continue
            values.sort(key=lambda r:r['date'])
            if values:
                latest=values[-1]
                factors.append(dict(kind='indian_atf',title=city+' published jet fuel price',value=latest['value'],units='INR/kilolitre',
                    as_of=latest['date'],stale=(date.today()-date.fromisoformat(latest['date'])).days>35,
                    source_url=latest.get('source_url') or atf.get('source_url'),interpretation='Dated metro ATF context; stale rows cannot indicate current fuel pressure. Not an airline fuel contract or route forecast.'))
        traffic=context_payload(cache,'airport_traffic',dict,context_problems)
        for airport in (trip['origin'],trip['destination']):
            values=[]
            for row in traffic.get('observations',[]) if isinstance(traffic.get('observations',[]),list) else []:
                if not isinstance(row,dict):
                    continue
                try:
                    if row.get('airport')!=airport or date.fromisoformat(row['period_end'])>date.today():
                        continue
                    if any(type(row.get(k)) is not int or row[k]<0 for k in ('domestic_current','domestic_previous')):
                        continue
                    if not sourced_url(row.get('source_url') or traffic.get('source_url'),{'aai.aero','www.aai.aero'}):
                        continue
                    values.append(row)
                except (TypeError,ValueError,KeyError):
                    continue
            values.sort(key=lambda r:r['period_end'])
            if values:
                latest=values[-1];previous=latest['domestic_previous']
                factors.append(dict(kind='airport_traffic',title=airport+' domestic passenger movements',value=latest['domestic_current'],
                    units=traffic.get('units'),as_of=latest['period_end'],previous_year_value=previous,
                    change_yoy_pct=round((latest['domestic_current']/previous-1)*100,2) if previous else None,
                    stale=(date.today()-date.fromisoformat(latest['period_end'])).days>60,source_url=latest.get('source_url') or traffic.get('source_url'),
                    interpretation='Published arrivals plus departures compared with the same month last year. Airport activity is not demand or available seats for this directed route.'))
        capacity=context_payload(cache,'airline_capacity',dict,context_problems)
        capacity_rows=[]
        for row in capacity.get('observations',[]) if isinstance(capacity.get('observations',[]),list) else []:
            try:
                if row.get('airline')!='IndiGo' or date.fromisoformat(row['period_end'])>date.today():
                    continue
                if type(row.get('passengers')) is not int or row['passengers']<0:
                    continue
                if not positive_amount(row.get('seat_km_thousands')) or not positive_amount(row.get('passenger_km_thousands')):
                    continue
                plf=row.get('load_factor_pct')
                if isinstance(plf,bool) or not isinstance(plf,(int,float)) or not math.isfinite(plf) or not 0<=plf<=100:
                    continue
                if abs(row['passenger_km_thousands']/row['seat_km_thousands']*100-plf)>.2:
                    continue
                if not sourced_url(row.get('source_url') or capacity.get('source_url'),{'goindigo.in','www.goindigo.in'}):
                    continue
                capacity_rows.append(row)
            except (TypeError,ValueError,KeyError,AttributeError):
                continue
        capacity_rows.sort(key=lambda row:row['period_end'])
        if capacity_rows:
            latest=capacity_rows[-1]
            month=date.fromisoformat(latest['period_end'])
            prior=next((row for row in reversed(capacity_rows[:-1]) if (date.fromisoformat(row['period_end']).year,date.fromisoformat(row['period_end']).month)==(month.year-1,month.month)),None)
            factors.append(dict(kind='airline_capacity',title='IndiGo domestic passenger load factor',value=latest['load_factor_pct'],
                units='Percent of available seat-kilometres occupied',as_of=latest['period_end'],passengers=latest['passengers'],
                change_yoy_pp=round(latest['load_factor_pct']-prior['load_factor_pct'],2) if prior else None,
                stale=(date.today()-month).days>60,source_url=latest.get('source_url') or capacity.get('source_url'),
                interpretation='Published carrier-wide domestic traffic utilisation, not this directed route’s bookings, fare trend or available seats. Historical context does not predict this flight’s price.'))
        for name in ('energy_news','aviation_news','reported_news'):
            for article in context_payload(cache,name,list,context_problems):
                stamp=observed_timestamp(article.get('published_at')) if isinstance(article,dict) else None
                if not stamp:
                    continue
                if not isinstance(article.get('title'),str) or not article['title'].strip() or not sourced_url(article.get('url')):
                    continue
                domain={'energy_news':{'eia.gov','www.eia.gov'},'aviation_news':{'pib.gov.in','www.pib.gov.in'}}.get(name)
                if domain and not sourced_url(article['url'],domain):
                    continue
                age=datetime.now(timezone.utc)-stamp
                if timedelta(0)<=age<timedelta(days=7):
                    news.append({**article,'published_at':stamp.isoformat(),'primary_source':name!='reported_news'})
        news=sorted(news,key=lambda n:observed_timestamp(n['published_at']),reverse=True)[:10]
        conflict=[n for n in news if re.search(r'\b(?:war|conflict|airspace\s+closures?|supply\s+disruptions?)\b',n['title'],re.I)]
        if conflict:
            factors.append(dict(kind='disruption',title='Recent headlines mentioning conflict or disruption',interpretation='Review these linked reports and their geography. Their relevance to this Indian domestic journey is unconfirmed; headlines do not prove a fare hike on your route.',sources=conflict[:3]))
        upcoming=[]
        from financial_filter import FinancialFilter
        async with self.db.db.execute("SELECT c.*,e.observed_at AS evidence_observed_at FROM coupons c JOIN live_offer_evidence e ON e.platform=c.platform AND e.code=c.code WHERE c.is_active=1 AND c.valid_from>? AND c.valid_from<=?",(date.today().isoformat(),trip['departure_date'])) as cursor:
            candidates=await cursor.fetchall()
        for candidate in candidates:
            offer=dict(candidate)
            if not fresh_timestamp(offer.get('evidence_observed_at'),168) or not sourced_url(offer.get('source_url')):
                continue
            from compiler import is_flight_coupon,is_international_only_coupon,is_domestic_only_coupon
            if not is_flight_coupon(offer['code'],offer.get('description') or ''):
                continue
            intl=is_international_only_coupon(offer['code'],offer.get('description') or '')
            domestic=is_domestic_only_coupon(offer['code'],offer.get('description') or '')
            if (trip.get('is_domestic') and intl and not domestic) or (not trip.get('is_domestic',True) and domestic and not intl):
                continue
            # Apply other restrictions while assessing a genuinely announced future offer.
            future_rules={**financial,'passenger_count':trip['passenger_count'],'is_domestic':True,'booking_date':offer['valid_from']}
            if FinancialFilter().passes(offer,future_rules)[0]:
                upcoming.append({**{k:offer.get(k) for k in ['platform','code','description','valid_from','valid_until','source_url']},
                    'eligibility_and_savings_unverified':True})
        reasons=[]
        signal='MONITOR'
        wait_until=None
        basis='NO_CURRENT_PRICE'
        affordable=False
        if best:
            basis='CURRENT_COMPARISON'
            reasons.append(f"Lowest recently observed {'merchant payment total among verified options' if fresh_verified else 'accepted listed fare'}: INR {best['price']:,.0f} on {best['platform']}.")
            affordable=not round_trip and target_price is not None and best['price']<=target_price
            bargain=not fresh_verified and points.coverage_stable and market_best is not None and best['price']==market_best['price'] and len(points)>=7 and best['price']<=sorted(p for _,p in points)[max(0,len(points)//5)]
            if not round_trip and target_price is not None and not affordable:
                reasons.append(f'Your INR {target_price:,.0f} target is not met; this result is not a buy recommendation within that budget.')
            if not round_trip and (affordable or (target_price is None and days<=14)):
                signal='BUY_CANDIDATE'
                basis='TARGET_MET' if affordable else 'DEPARTURE_DEADLINE'
                reasons.append(('The merchant payment total meets your target; later gateway/issuer charges are unconfirmed.' if fresh_verified else 'The listed fare meets your target before unverified checkout charges.') if affordable else 'Departure is within fourteen days; the remaining time to book is short. This is a deadline rule, not evidence of rising prices or falling seat inventory.')
                if not fresh_verified:
                    reasons.append('Confirm eligible coupons and the final payment total before buying.')
                if affordable and not fresh_verified and market_best and forecast['forecast_7d'] and forecast['forecast_7d']<market_best['price']*.95:
                    reasons.append('The qualified listing model also estimates a lower future fare. This candidate follows your target threshold, not a claim that today is the minimum; continued monitoring carries availability risk.')
            elif not round_trip and market_best and not fresh_verified and forecast['forecast_7d'] and forecast['forecast_7d']<market_best['price']*.95 and days>30:
                signal='WAIT_AND_RECHECK'
                basis='VALIDATED_LOCAL_TREND'
                wait_until=forecast.get('forecast_target_date') or (date.today()+timedelta(days=7)).isoformat()
                reasons.append('A local trend model beat the last-price baseline in recent chronological checks and estimates a lower fare next week. Confidence is low; availability can change.')
            elif not round_trip and target_price is None and bargain:
                signal='BUY_CANDIDATE'
                basis='OBSERVED_LOW'
                reasons.append('The fare is in the lowest fifth of comparable observed daily prices; this is a historical comparison, not a forecast. Confirm eligible coupons and the final payment total before buying.')
            elif upcoming:
                reasons.append('Published upcoming offers are listed for review. Their eligibility and net savings are unverified, so they do not justify a waiting recommendation.')
        else:
            reasons.append('No fresh exact-trip fare is available. Keep monitoring; do not buy from an old quote.')
        if not round_trip and best and days<=14 and target_price is not None and not affordable:
            reasons.append('Departure is close. Review your target or compare acceptable alternatives; waiting is not evidence that your budget will be met.')
        if trip.get('trip_type')=='round_trip':
            # This report compares outbound fares. The return is separately
            # searched and may have failed; no full-trip timing/budget decision
            # can follow from the outbound leg alone.
            signal='MONITOR'
            basis='OUTBOUND_ONLY_ROUND_TRIP'
            wait_until=None
            affordable=False
            forecast.update(status='ROUND_TRIP_TIMING_WITHHELD',forecast_7d=None,confidence=None)
            forecast['certainty'].update(percent=None,range=None,
                explanation='Whole-trip timing is not calibrated. This evidence covers the outbound leg; both separately booked legs need a fresh comparison.')
            reasons.insert(0,'This is an outbound-only comparison for a round-trip request. No whole-trip buy/wait recommendation or return-inclusive target assessment is available; compare and verify both legs before buying.')
        if cost_pressure:
            reasons.append('Recent energy/currency observations show upstream cost pressure. Its effect on this route is unmeasured; it does not change the buy/wait rule or certainty meter.')
        if conflict:
            reasons.append('Recent headlines mention conflict or disruption. Check their geography and booking flexibility; their effect on this domestic journey is unconfirmed and does not change model certainty.')
        if len(points)<21:
            reasons.append(f'Only {len(points)} distinct observation days are available; no trained fare forecast is used.')
        years=sorted({observed_timestamp(r['observed_at']).year for r in series})
        observed_span=(points[-1][0]-points[0][0]).days if points else 0
        lower_listings=[r for r in fresh if r['verification']=='listed' and best and r['price']<best['price']]
        if fresh_verified and lower_listings:
            reasons.append(f'{len(lower_listings)} lower listed option(s) remain unverified and may beat this after their own fees and coupons are checked.')
        reasons.append('Multi-year seasonality and bank-anniversary offers are not assumed without dated evidence.')
        return dict(signal=signal,reasoning=' '.join(reasons),wait_until=wait_until,days_to_departure=days,
            price=best['price'] if best else None,platform=best['platform'] if best else None,
            verification=best['verification'] if best else None,confidence=forecast['confidence'],forecast=forecast,
            historical_years=int(observed_span/365.25),observed_calendar_years=years,factors=factors,news=news,upcoming_offers=upcoming,
            urgency='HIGH' if days<=14 else 'LOW',recommended_book_by=date.today().isoformat() if signal=='BUY_CANDIDATE' else None,
            decision_basis=dict(rule=basis,target_price=target_price,target_met=affordable if target_price is not None and trip.get('trip_type')!='round_trip' else None,
                accepted_current_quotes=len(fresh),verified_current_quotes=len(fresh_verified),lower_unverified_options=len(lower_listings),
                forecast_used=signal=='WAIT_AND_RECHECK',news_used_as_causal_prediction=False,price_scope='merchant_payment' if fresh_verified else 'listed'),
            context_problems=context_problems,
            certainty=forecast['certainty'],
            feed_status=cache.get('feed_status',{}),updated_at=utc_now(),
            missing_parameters=['Route-specific demand/seat inventory','Validated multi-year seasonal history','Future unannounced bank offers'])

"""Persistent booking monitors. Runs independently of whether the UI tab is open."""
import asyncio
import json
import math
import uuid
from datetime import datetime, timedelta, timezone, date
from quotes import utc_now
from advisor_evidence import observed_timestamp


class RedRoom:
    def __init__(self,db,compiler,dispatcher,brain,market,harvester,emit,desktop_notify=None):
        self.db,self.compiler,self.dispatcher=db,compiler,dispatcher
        self.brain,self.market,self.harvester,self.emit=brain,market,harvester,emit
        self.running=set()
        self.desktop_notify=desktop_notify
        self.owner=str(uuid.uuid4())

    async def list(self):
        async with self.db.db.execute('SELECT * FROM red_room WHERE is_active=1 ORDER BY created_at DESC') as cursor:
            rows=await cursor.fetchall()
        now=utc_now()
        result=[]
        for row in rows:
            item={**dict(row),'request':json.loads(row['request']),'report':json.loads(row['report']) if row['report'] else None,
                'checking':row['id'] in self.running or bool(row['lease_until'] and row['lease_until']>now)}
            if item['report'] and item['report'].get('evidence_version')!=2:
                item['report']=None
                item['last_error']='Saved report predates the current evidence checks. Run a fresh check before using it.'
            result.append(item)
        return result

    async def add(self,request):
        self.compiler._validate_trip(request.get('trip',{}))
        if request['trip'].get('tripType','one_way')!='one_way':
            raise ValueError('Monitor outbound and return as separate one-way Red Room requests')
        price=request.get('targetPrice')
        if price is not None and (isinstance(price,bool) or not isinstance(price,(int,float)) or not math.isfinite(price) or price<=0):
            raise ValueError('Target price must be a positive finite INR amount')
        hours=request.get('intervalHours',24)
        if isinstance(hours,bool) or not isinstance(hours,int) or hours<6 or hours>168:
            raise ValueError('Check interval must be between 6 and 168 hours')
        if len(await self.list())>=10:
            raise ValueError('Keep at most ten active monitors to limit website traffic')
        budget=request.get('transferBudget',2000)
        if isinstance(budget,bool) or not isinstance(budget,(int,float)) or not math.isfinite(budget) or budget<0:
            raise ValueError('Ground transfer estimate must be a finite nonnegative INR amount')
        trip=request['trip']
        # Each monitored request retains cabin/adults/bank rules, not current UI settings.
        await self.compiler.compile({**request,'trip':trip,'platforms':['google_flights','easemytrip','cleartrip']},persist=False)
        rid=str(uuid.uuid4())
        await self.db.db.execute('INSERT INTO red_room (id,request,interval_hours,created_at) VALUES (?,?,?,?)',
            (rid,json.dumps(request),hours,utc_now()))
        await self.db.db.commit()
        return rid

    async def remove(self,rid):
        await self.db.db.execute('UPDATE red_room SET is_active=0 WHERE id=?',(rid,))
        await self.db.db.commit()

    async def emit_list(self):
        self.emit('redroom:data',dict(items=await self.list()))

    async def check(self,rid):
        try:
            async with asyncio.timeout(600):
                await self._check(rid)
        except TimeoutError:
            await self.db.db.execute('UPDATE red_room SET last_checked=?,last_error=?,failure_count=failure_count+1 WHERE id=?',
                (utc_now(),'Check exceeded ten minutes; partial/old results were not used for a new alert.',rid))
            await self.db.db.commit()
            await self.emit_list()

    async def _check(self,rid):
        if rid in self.running:
            return
        item=next((r for r in await self.list() if r['id']==rid),None)
        if not item:
            raise ValueError('Red Room request not found')
        now=datetime.now(timezone.utc)
        claim=await self.db.db.execute('''UPDATE red_room SET lease_owner=?,lease_until=?,last_attempt=?
            WHERE id=? AND is_active=1 AND (lease_until IS NULL OR lease_until<?)''',
            (self.owner,(now+timedelta(minutes=15)).isoformat(),now.isoformat(),rid,now.isoformat()))
        await self.db.db.commit()
        if claim.rowcount!=1:
            return
        self.running.add(rid)
        try:
            await self.emit_list()
            request=item['request']
            if date.fromisoformat(request['trip']['departureDate'])<date.today():
                raise ValueError('Travel date has passed; remove this request')
            task=await self.compiler.compile({**request,'platforms':['google_flights','easemytrip','cleartrip'],'cloak':{'maxConcurrentBots':2}})
            task['background']=True
            await self.market.refresh()
            await self.harvester.quick_harvest(task['platforms'])
            await self.dispatcher.dispatch_all(task)
            results=await self.db.get_search_results(task['search_id'])
            if not results:
                raise ValueError('No fresh fares returned. The previous report is retained; retry later.')
            report=await self.brain.assess(task['trip'],task['financial'],request.get('targetPrice'),current_quotes=results)
            report['evidence_version']=2
            report['search_id']=task['search_id']
            report['source_problems']=task.get('platform_failures',{})
            report['partial_results']=[dict(platform=r['platform'],price=r['final_price'],airline=r['airline'],departure_time=r['departure_time'],integrity=r['savings_breakdown'].get('integrity',{})) for r in results[:12]]
            report['alternatives']=[]
            if request.get('exploreAlternatives'):
                try:
                    report['alternatives']=await self.dispatcher.explore_alternatives(task['search_id'],request.get('transferBudget',2000),request.get('hubs',['BOM','AMD']))
                except Exception as exc:
                    report['source_problems']['alternative planner']=str(exc)
            # Removed monitors must not publish a late recommendation or notification.
            active=any(r['id']==rid for r in await self.list())
            if not active:
                return
            key=report['signal']
            if key=='BUY_CANDIDATE':
                key+=f"|{report['price']}|{report['platform']}"
            elif report.get('wait_until'):
                key+='|'+report['wait_until']
            await self.db.db.execute('UPDATE red_room SET last_checked=?,last_success=?,last_price=?,report=?,last_error=NULL,failure_count=0 WHERE id=? AND lease_owner=?',
                (utc_now(),utc_now(),report['price'],json.dumps(report),rid,self.owner))
            await self.db.db.commit()
            prior=json.loads(item['report']) if isinstance(item['report'],str) else item['report']
            should_alert=(report['signal']=='BUY_CANDIDATE' and (not prior or prior['signal']!='BUY_CANDIDATE' or report['price']<(prior.get('price') or math.inf))) or (report['signal'].startswith('WAIT_') and key!=item['last_alert_key'])
            if should_alert:
                trip=request['trip']
                message=f"Red Room: {trip['origin']}-{trip['destination']} on {trip['departureDate']}. {report['reasoning']}"
                inserted=await self.db.add_notification('red_room','Booking recommendation',message,dict(red_room_id=rid,report=report),
                    # Deduplicate a single observed decision episode. A deal
                    # which disappears and later returns at the same price is
                    # actionable again; a permanent price key hid that alert.
                    dedup_key='redroom|'+rid+'|'+key+'|'+task['search_id'])
                if inserted:
                    self.emit('redroom:alert',dict(id=rid,message=message,report=report))
                await self.db.db.execute('UPDATE red_room SET last_alert_key=? WHERE id=?',(key,rid))
                await self.db.db.commit()
                if inserted and self.desktop_notify:
                    try:
                        await self.desktop_notify('Flight Finder — Red Room',message)
                    except Exception:
                        self.emit('redroom:delivery_error',dict(id=rid,message='Desktop delivery failed. The alert is saved in Red Room.'))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.db.db.execute('UPDATE red_room SET last_checked=?,last_error=?,failure_count=failure_count+1 WHERE id=? AND lease_owner=?',(utc_now(),str(exc),rid,self.owner))
            await self.db.db.commit()
            self.emit('redroom:error',dict(id=rid,message=str(exc)))
        finally:
            await self.db.db.execute('UPDATE red_room SET lease_owner=NULL,lease_until=NULL WHERE id=? AND lease_owner=?',(rid,self.owner))
            await self.db.db.commit()
            self.running.discard(rid)
            await self.emit_list()

    async def loop(self):
        while True:
            try:
                items=await self.list()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.emit('redroom:error',dict(message='Saved monitors could not be read; retrying: '+str(exc)))
                items=[]
            for item in items:
                try:
                    # Naive or invalid stored timestamps cannot establish when
                    # to skip a check; retry rather than kill the whole loop.
                    checked=observed_timestamp(item.get('last_checked'))
                    retry_hours=min(item['interval_hours'],.5*2**min(item.get('failure_count',0),4)) if item.get('last_error') else item['interval_hours']
                    if not checked or datetime.now(timezone.utc)-checked>=timedelta(hours=retry_hours):
                        await self.check(item['id'])
                except asyncio.CancelledError:
                    raise
                except ValueError:
                    # A user may remove a request between listing and starting it.
                    continue
                except Exception as exc:
                    # One broken monitor must not stop every other saved request.
                    self.emit('redroom:error',dict(id=item['id'],message='Monitor check failed; other requests will continue: '+str(exc)))
            await asyncio.sleep(30)

"""Durable small facts about each trial, never full browser pages or inputs."""
import json
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit


def now():
    return datetime.now(timezone.utc).isoformat()


def public_text(value, limit=1200):
    text=str(value or '')
    text=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[redacted email]', text)
    text=re.sub(r'\b(?:\d[ -]?){10,19}\b', '[redacted number]', text)
    text=re.sub(r'https?://\S+', '[page link omitted]', text)
    return text[:limit]


def public_url(value):
    parsed=urlsplit(str(value or ''))
    if parsed.scheme!='https' or parsed.username or parsed.password:
        return None
    # Public offer links only; never persist booking/query/session identifiers.
    if not re.search(r'offer|promo|coupon|discount',parsed.path,re.I):
        return None
    return urlunsplit((parsed.scheme,parsed.netloc,parsed.path,'',''))[:500]


def safe_scope(scope):
    data={key:scope[key] for key in ('origin','destination','departure_date','passenger_count',
        'cabin_class','flight_number','departure_time','stage','onsite_collection') if key in scope}
    data={key:public_text(value,100) if isinstance(value,str) else value for key,value in data.items()}
    payment=scope.get('selected_payment') or {}
    data['payment']={'method':public_text(payment.get('method'),30),
        'banks':[public_text(b,30) for b in payment.get('banks',[])[:8]]}
    data['stage']=data.get('stage','unverified')
    return data


class CouponAudit:
    def __init__(self,db,run_id):
        self.db,self.id,self.ordinal=db,run_id,0

    @classmethod
    async def start(cls,db,platform,search_id,scope):
        audit=cls(db,str(uuid.uuid4()))
        async with db.lock:
            await db.db.execute('INSERT INTO coupon_audit_runs(id,platform,search_id,scope,status,started_at) VALUES(?,?,?,?,?,?)',
                (audit.id,platform,search_id,json.dumps(safe_scope(scope)),'running',now()))
            await db.db.commit()
        return audit

    async def trial(self,result,offer=None):
        offer=offer or {}
        payload={key:public_text(result[key]) for key in ('reason','terms') if result.get(key)}
        for key in ('price','savings'):
            if result.get(key) is not None:
                payload[key]=result[key]
        payload.update(source_url=public_url(offer.get('source_url')),
            source_host=urlsplit(str(offer.get('source_url') or '')).hostname,
            restrictions=public_text(offer.get('description')),
            valid_until=public_text(offer.get('valid_until'),50),
            source_observed_at=public_text(offer.get('observed_at'),50),
            native=offer.get('source_type')=='platform_native')
        async with self.db.lock:
            await self.db.db.execute('INSERT INTO coupon_audit_trials(run_id,ordinal,code,status,payload,observed_at) VALUES(?,?,?,?,?,?)',
                (self.id,self.ordinal,public_text(result.get('code'),40),result['status'],json.dumps(payload),now()))
            await self.db.db.commit()
        self.ordinal+=1

    async def finish(self,status,summary):
        # Caller supplies only total/coverage/winner metadata, never page contents.
        safe={key:summary[key] for key in ('baseline_price','best_price','best_coupon','savings','coverage') if key in summary}
        if summary.get('reason'):
            safe['reason']=public_text(summary['reason'])
        async with self.db.lock:
            await self.db.db.execute('UPDATE coupon_audit_runs SET status=?,completed_at=?,summary=? WHERE id=?',
                (status,now(),json.dumps(safe),self.id))
            await self.db.db.commit()


async def history(db,platform,limit=40):
    async with db.lock:
        async with db.db.execute('SELECT * FROM coupon_audit_runs WHERE platform=? ORDER BY started_at DESC LIMIT ?',
                (platform,max(1,min(int(limit),100)))) as cursor:
            records=[dict(row) for row in await cursor.fetchall()]
        for row in records:
            row['scope']=json.loads(row['scope']);row['summary']=json.loads(row['summary'])
            async with db.db.execute('SELECT code,status,payload,observed_at FROM coupon_audit_trials WHERE run_id=? ORDER BY ordinal',(row['id'],)) as cursor:
                row['trials']=[{**json.loads(trial['payload']),**{k:trial[k] for k in ('code','status','observed_at')}} for trial in await cursor.fetchall()]
    return records

"""Export accepted live evidence. Never touches legacy training data or models."""
import argparse
import asyncio
import csv
import json
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from coupon_db import CouponDB
from quotes import utc_now
from advisor_evidence import history_row_problem

async def export(folder):
    folder.mkdir(parents=True,exist_ok=True)
    db=CouponDB();await db.initialize()
    try:
        async with db.db.execute("SELECT * FROM fare_quotes WHERE evidence_version=2 AND quality_status IN ('corroborated','checkout_verified') AND platform!='mock' ORDER BY route,departure_date,observed_at") as cur:
            candidates=[dict(r) for r in await cur.fetchall()]
        excluded=Counter()
        fares=[]
        for row in candidates:
            problem=history_row_problem(row)
            if problem:
                excluded[problem]+=1
            else:
                fares.append(row)
        with (folder/'accepted_fares.csv').open('w',newline='',encoding='utf-8') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(fares[0]) if fares else ['route','departure_date','passenger_count','cabin_class','price','verification','quality_status','observed_at'])
            writer.writeheader();writer.writerows(fares)
        counts={'accepted_fares':len(fares)}
        for table in ('intelligence_cache','knowledge_sources','live_offer_evidence','offer_observations','provider_runs'):
            async with db.db.execute('SELECT * FROM '+table) as cur:
                rows=[dict(r) for r in await cur.fetchall()]
            (folder/(table+'.json')).write_text(json.dumps(rows,indent=2),encoding='utf-8')
            counts[table]=len(rows)
        manifest=dict(exported_at=utc_now(),counts=counts,excluded_fare_candidates=sum(excluded.values()),
            excluded_fare_reasons=dict(excluded),
            policy='Directed routes, departure date, adults and cabin stay separate. Listed and checkout series remain separate. Quarantined, uncorroborated and legacy seeded prices are excluded.',
            forecast_gate='Listed fares only; exact time/stops preferences. At least seven nonoverlapping weekly holdouts after 20 training days (roughly 70 daily observations), fresh data, and 10% lower MAE than last-price persistence. Forecast cohorts restart after collection gaps over seven days; completed validation outcomes must be at most fourteen days old. No numerical certainty before 20 independent weekly outcomes and a passed holdout gate.')
        (folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        print(json.dumps(manifest))
    finally:
        await db.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[2]/'sessions'/'brain-data')
    args=parser.parse_args();asyncio.run(export(args.output))

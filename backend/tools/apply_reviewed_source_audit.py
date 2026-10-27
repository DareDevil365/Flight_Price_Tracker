"""Apply the explicitly reviewed October source audit; preserve originals in backup.

Default is a read-only plan. --apply changes only the identified audit records
and verified carrier context. Never seeds fares or overwrites model files.
"""
import argparse
import json
import math
import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coupon_db import DB_PATH
from quotes import utc_now

ROOT = Path(__file__).resolve().parents[2]
OWNED_SEARCH = '229a94cf-6e41-4d26-9202-d559060f04d4'


def main(apply=False):
    folder=ROOT/'sessions'/'data-source-audit'
    audited=json.loads((folder/'primary_recheck.json').read_text(encoding='utf-8'))
    report=json.loads((folder/'report.json').read_text(encoding='utf-8'))
    carrier=audited['carrier']
    assert carrier['source_url']=='https://www.goindigo.in/information/investor-relations/operational-statistics/domestic.html'
    assert carrier['existing_matches']==96 and carrier['existing_mismatches']==0
    source=sqlite3.connect('file:'+DB_PATH.as_posix()+'?mode=ro',uri=True)
    source.row_factory=sqlite3.Row
    old=json.loads(source.execute("SELECT payload FROM intelligence_cache WHERE key='airline_capacity'").fetchone()[0])
    observations=carrier['observations']
    assert len(observations)==133 and len({r['period_month'] for r in observations})==133
    for row in observations:
        assert date.fromisoformat(row['period_end'])<=date.today()
        assert row['airline']=='IndiGo' and row['source_url']==carrier['source_url']
        assert type(row['passengers']) is int and row['passengers']>0
        rpk,ask,plf=(row[k] for k in ('passenger_km_thousands','seat_km_thousands','load_factor_pct'))
        assert all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in (rpk,ask,plf))
        assert plf<=100 and abs(100*rpk/ask-plf)<=.11
    by_month={r['period_month']:r for r in observations}
    assert all(by_month[r['period_month']]==r for r in old['observations'])
    fares=[dict(r) for r in source.execute('SELECT * FROM fare_quotes WHERE id IN (645,646) ORDER BY id')]
    assert len(fares)==2
    for row,platform,amount in zip(fares,('easemytrip','google_flights'),(8841,9191)):
        assert (row['route'],row['departure_date'],row['flight_number'],row['platform'],row['price'])==('DEL-CCU','2026-11-23','QP-1260',platform,amount)
    results=[dict(r) for r in source.execute("SELECT * FROM search_results WHERE search_id=? AND flight_number IN ('QP-1260','QP-1258')",(OWNED_SEARCH,))]
    plan=dict(checked_at=utc_now(),carrier_rows_before=len(old['observations']),carrier_rows_after=133,
        fare_ids_reviewed=[645,646],search_id=OWNED_SEARCH,apply=apply,
        limitation='Historical primary context is still stale; no fare outcomes or certainty are added.')
    if not apply:
        source.close();print(json.dumps(plan));return
    stamp=utc_now().replace(':','-')
    backup=folder/f'before-reviewed-repair-{stamp}.db'
    with sqlite3.connect(backup) as target:
        source.backup(target)
    source.close()
    con=sqlite3.connect(DB_PATH)
    try:
        with con:
            original={'fares':fares,'results':results}
            (folder/f'original-owned-records-{stamp}.json').write_text(json.dumps(original,indent=2),encoding='utf-8')
            for row in fares:
                evidence=json.loads(row['evidence'])
                status='flagged' if row['id']==646 else 'uncorroborated'
                reason='Known corrupt QP airline label in retained segment evidence' if row['id']==646 else 'Only corroborating source has contradictory segment evidence; agreement withdrawn'
                evidence['integrity']=dict(status=status,reasons=[reason],compared_sources=[])
                evidence['audit_checked_at']=utc_now()
                con.execute('UPDATE fare_quotes SET quality_status=?,evidence=? WHERE id=?',(status,json.dumps(evidence),row['id']))
            for row in results:
                meta=json.loads(row['savings_breakdown'])
                bad=row['platform']=='google_flights'
                status='flagged' if bad else 'uncorroborated'
                reason='Known corrupt QP airline label in retained segment evidence' if bad else 'Only corroborating source has contradictory segment evidence; agreement withdrawn'
                if bad:
                    con.execute('INSERT OR REPLACE INTO quote_quarantine VALUES (?,?,?,?)',(row['id'],json.dumps([reason]),json.dumps(row),utc_now()))
                meta['integrity']=dict(status=status,reasons=[reason],compared_sources=[])
                con.execute('UPDATE search_results SET savings_breakdown=? WHERE id=?',(json.dumps(meta),row['id']))
            updated={**old,'observations':observations,'as_of':carrier['as_of'],
                'rejected_rows':carrier['rejected_rows'],'reviewed_recheck':{k:v for k,v in carrier.items() if k!='observations'},
                'scope':carrier['scope']}
            document={k:carrier[k] for k in ('source_url','source_sha256','hash_scope','parser_version','transport','checked_at')}
            documents=old.get('source_documents',[])
            updated['source_documents']=documents if document in documents else documents+[document]
            con.execute('UPDATE intelligence_cache SET payload=?,updated_at=? WHERE key=?',(json.dumps(updated),utc_now(),'airline_capacity'))
            for key in ('brent','usd_inr','indian_atf','airport_traffic'):
                payload=json.loads(con.execute('SELECT payload FROM intelligence_cache WHERE key=?',(key,)).fetchone()[0])
                payload['independent_recheck']={'checked_at':report['checked_at'],**report['results'][key]}
                # Preserve original collection timestamp and all source observations.
                con.execute('UPDATE intelligence_cache SET payload=? WHERE key=?',(json.dumps(payload),key))
        plan['backup']=str(backup)
        plan['source_failures_preserved']=True
        (folder/'repair_manifest.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
        print(json.dumps(plan))
    finally:
        con.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    main(parser.parse_args().apply)

"""Fetch real startup context/offers, back up SQLite, and export a dated manifest."""
import argparse
import asyncio
import json
import math
import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from coupon_db import CouponDB,DB_PATH
from coupon_harvester import CouponHarvester
from evidence_feeds import ATF_URL,atf_rows,source_metadata,source_document_metadata,merge_source_documents
from intelligence import MarketContext
from carrier_context import capacity_text,current_atf_html,CAPACITY_URL,CURRENT_ATF_URL
from quotes import utc_now
from tools.export_brain_dataset import export


def merge_reviewed_atf(previous, raw, url, rows, scope):
    """Preserve older observations and document receipts when importing reviewed facts."""
    previous = previous if isinstance(previous, dict) else {}
    merged={}
    old_rows=previous.get('observations',[]) if isinstance(previous.get('observations'),list) else []
    if previous.get('parser_version')==1:
        for row in old_rows:
            try:
                if isinstance(row,dict) and row.get('city') in ('Delhi','Kolkata','Mumbai','Chennai') and date.fromisoformat(row['date']) <= date.today() and row.get('units') == 'INR/kilolitre' and isinstance(row.get('value'),(int,float)) and not isinstance(row['value'],bool) and math.isfinite(row['value']) and row['value'] > 0 and isinstance(row.get('source_url'),str) and row['source_url'].startswith('https://'):
                    merged[(row['date'],row['city'])]=row
            except (ValueError,TypeError,KeyError):
                continue
    merged.update({(r['date'],r['city']):r for r in rows})
    observations=[merged[key] for key in sorted(merged)]
    document=source_document_metadata(raw,url,rows,transport='reviewed_primary_page_text')
    return merge_source_documents(previous,[document],units='INR/kilolitre',observations=observations,
        as_of=observations[-1]['date'],observed_at=utc_now(),scope=scope)


async def main(args):
    folder=args.output;folder.mkdir(parents=True,exist_ok=True)
    try:
        previous_manifest=json.loads((folder/'bootstrap_manifest.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):
        previous_manifest={}
    if DB_PATH.exists():
        stamp=utc_now().replace(':','-')
        backup=folder/f'before-bootstrap-{stamp}.db'
        with sqlite3.connect(DB_PATH) as source,sqlite3.connect(backup) as target:
            source.backup(target)
    db=CouponDB();await db.initialize()
    try:
        context=MarketContext(db);await context.initialize()
        if args.atf_text:
            # Explicit reviewed primary-page extraction, never an invented seed.
            raw=args.atf_text.read_text(encoding='utf-8')
            rows=atf_rows(raw)
            previous=(await context.snapshot()).get('indian_atf',{}).get('data',{})
            await context._save('indian_atf',merge_reviewed_atf(previous,raw,ATF_URL,rows,
                'Reviewed historical IOCL table. Import does not refresh source observation dates or claim current fuel prices.'))
        if args.atf_current_text:
            raw=args.atf_current_text.read_text(encoding='utf-8')
            rows=current_atf_html(raw)
            previous=(await context.snapshot()).get('indian_atf',{}).get('data',{})
            await context._save('indian_atf',merge_reviewed_atf(previous,raw,CURRENT_ATF_URL,rows,
                'Reviewed dated domestic IOCL block. HTTP/source access failure remains separate; footer dates cannot refresh ATF observations.'))
        if args.capacity_text:
            merged,documents,rejected={},{},[]
            for path in args.capacity_text:
                raw=path.read_text(encoding='utf-8')
                rows=capacity_text(raw,rejected=rejected)
                for row in rows:
                    if row['period_month'] in merged and merged[row['period_month']]!=row:
                        raise ValueError('Conflicting reviewed carrier monthly documents')
                    merged[row['period_month']]=row
                documents[str(path.name)]=source_metadata(raw,CAPACITY_URL,'reviewed_primary_page_text')
            observations=[merged[key] for key in sorted(merged)]
            await context._save('airline_capacity',dict(parser_version=1,source_url=CAPACITY_URL,source_documents=list(documents.values()),
                transport='reviewed_primary_page_text',observations=observations,rejected_rows=rejected,
                units='Percent (passenger-km / available seat-km)',as_of=observations[-1]['period_end'],
                scope='IndiGo-wide scheduled domestic operations only. Not directed route demand, bookable seat inventory or fare training.'))
        cache=await context.refresh(force=True,archive=True)
        harvester=CouponHarvester(db)
        offers=await harvester.deep_harvest() if not args.skip_offers else []
        counts={}
        for name,entry in cache.items():
            data=entry['data']
            if isinstance(data,dict) and isinstance(data.get('observations'),list):
                observations=data['observations']
                as_of=data.get('as_of')
                threshold=35 if name=='indian_atf' else 60 if name in ('airport_traffic','airline_capacity') else 7
                counts[name]=dict(count=len(observations),as_of=as_of,
                    stale=bool(as_of and (date.today()-date.fromisoformat(as_of)).days>threshold),
                    source_url=data.get('source_url'),units=data.get('units'))
            elif isinstance(data,list):
                counts[name]=dict(count=len(data),type='dated headlines')
        manifest=dict(collected_at=utc_now(),scope='Domestic Indian fares with global and Indian cost context',
            context=counts,feed_status=cache.get('feed_status',{}).get('data',{}),
            offer_refresh_performed=not args.skip_offers,
            discovered_offer_codes=len(offers) if not args.skip_offers else None,offer_sources=harvester.last_status,
            last_offer_refresh=previous_manifest.get('last_offer_refresh') if args.skip_offers else dict(
                observed_at=utc_now(),discovered_codes=len(offers),sources=harvester.last_status),
            policy='Real context and advertised coupons are separate from accepted route fares. No inferred seasonal fares, coupon success rates, causal fuel coefficients or model certainty are seeded.')
        (folder/'bootstrap_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        print(json.dumps(manifest),flush=True)
    finally:
        await db.close()
    await export(folder/'brain-data')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[2]/'sessions'/'source-bootstrap')
    parser.add_argument('--atf-text',type=Path,help='Explicitly reviewed IOCL dated city table in pipe-separated text')
    parser.add_argument('--skip-offers',action='store_true')
    parser.add_argument('--capacity-text',type=Path,action='append',default=[],help='Reviewed primary IndiGo table excerpt; repeat for separate excerpts')
    parser.add_argument('--atf-current-text',type=Path,help='Reviewed primary IOCL domestic block as structured HTML, preserving its table date')
    asyncio.run(main(parser.parse_args()))

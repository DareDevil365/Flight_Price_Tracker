"""Deterministic document receipts only; no production evidence or network writes."""
import hashlib
import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from evidence_feeds import source_document_metadata, merge_source_documents, ATF_URL
from carrier_context import refresh_atf, CURRENT_ATF_URL
from tools.bootstrap_brain_data import merge_reviewed_atf
from intelligence import MarketContext


def document(raw='first', url='https://example.org/series', download='https://example.org/csv?from=2026-01-01'):
    return source_document_metadata(raw,url,[{'date':'2026-01-01'},{'date':'2026-01-03'}],download_url=download)


def test_actual_document_hash_bounds_and_utc_receipt_not_merged_series():
    first=document()
    previous=merge_source_documents({},[first],observations=[{'date':'2023-01-01'}],audit_note='Keep this independent audit')
    fresh=document('incremental',download='https://example.org/csv?from=2026-01-02')
    saved=merge_source_documents(previous,[fresh],observations=[{'date':'2023-01-01'},{'date':'2026-01-03'}])
    assert saved['source_sha256']==hashlib.sha256(b'incremental').hexdigest()
    assert saved['hash_scope']=='latest_source_document_not_merged_observations'
    assert saved['first_observation_date']=='2026-01-01'
    assert saved['observation_count']==2
    assert len(saved['source_documents'])==2 and saved['audit_note']==previous['audit_note']
    assert datetime.fromisoformat(fresh['fetched_at']).utcoffset().total_seconds()==0


def test_identical_receipt_updates_but_revised_hash_and_distinct_download_survive():
    first=document()
    again={**first,'fetched_at':'2026-10-10T12:00:00+00:00'}
    previous=merge_source_documents({},[first])
    repeated=merge_source_documents(previous,[again])
    assert len(repeated['source_documents'])==1
    revised=document('revision')
    second_url=document(download='https://example.org/csv?from=2025-01-01')
    saved=merge_source_documents(repeated,[revised,second_url])
    assert len(saved['source_documents'])==3
    assert saved['source_documents'][0]['fetched_at']==again['fetched_at']


def test_unknown_legacy_hash_never_acquires_merged_history_bounds():
    old={'source_url':'https://example.org/series','source_sha256':'oldhash',
         'parser_version':1,'observations':[{'date':'2023-01-01'},{'date':'2026-01-03'}]}
    saved=merge_source_documents(old,[document()])
    legacy=saved['source_documents'][0]
    assert legacy['source_sha256']=='oldhash'
    assert legacy['coverage']=='unknown_legacy_document_coverage'
    assert 'first_observation_date' not in legacy and 'observation_count' not in legacy
    assert saved['legacy_document_coverage_unknown'] is True


def test_receipt_registry_is_bounded_and_discarded_history_is_explicit():
    old={'source_url':'https://example.org/old','source_sha256':'old'}
    saved=merge_source_documents(old,[document(str(index)) for index in range(70)])
    assert len(saved['source_documents'])==64 and saved['source_documents_limit']==64
    assert saved['source_documents_discarded']==7
    assert saved['legacy_document_coverage_unknown'] is True
    assert saved['source_documents'][0]['source_sha256']==hashlib.sha256(b'6').hexdigest()
    repeated=merge_source_documents(saved,[document('69')])
    assert len(repeated['source_documents'])==64 and repeated['source_documents_discarded']==7


def test_incomplete_receipt_cannot_inherit_other_document_bounds():
    previous=merge_source_documents({},[document()])
    saved=merge_source_documents(previous,[dict(source_url='https://example.org/unknown',source_sha256='new-unknown')])
    assert saved['coverage']=='unknown_legacy_document_coverage'
    assert 'first_observation_date' not in saved and 'observation_count' not in saved
    complete_legacy={**document()}
    complete_legacy.pop('coverage')
    restored=merge_source_documents({'source_documents':[complete_legacy]},[])
    assert restored['source_documents'][0]['coverage']=='recorded_document_rows'


def atf_rows(day,url=ATF_URL):
    return [dict(date=day,city=city,value=100000,units='INR/kilolitre',source_url=url)
            for city in ('Delhi','Kolkata','Mumbai','Chennai')]


def test_both_reviewed_atf_import_formats_preserve_prior_observations_and_receipts():
    first=merge_reviewed_atf({},'reviewed older table',ATF_URL,atf_rows('2026-01-01'),'Historical')
    second=merge_reviewed_atf(first,'reviewed new block',CURRENT_ATF_URL,atf_rows('2026-04-01',CURRENT_ATF_URL),'Dated current block')
    assert len(second['observations'])==8 and len(second['source_documents'])==2
    assert second['as_of']=='2026-04-01'
    assert second['source_documents'][0]['observation_count']==4
    assert second['source_documents'][1]['first_observation_date']=='2026-04-01'
    assert second['transport']=='reviewed_primary_page_text'
    assert 'recorded_at' in second and 'fetched_at' not in second


@pytest.mark.asyncio
async def test_successful_atf_refresh_keeps_old_unknown_receipt_and_new_actual_coverage(monkeypatch):
    old=dict(parser_version=1,source_url=ATF_URL,source_sha256='legacy',observations=atf_rows('2026-01-01'))
    context=SimpleNamespace(snapshot=AsyncMock(return_value={'indian_atf':{'data':old}}),_save=AsyncMock())
    monkeypatch.setattr('carrier_context.fetch_bytes',AsyncMock(side_effect=[b'new source',ValueError('Unavailable')]))
    monkeypatch.setattr('carrier_context.atf_html',lambda raw:atf_rows('2026-04-01'))
    status={}
    await refresh_atf(context,None,status)
    saved=context._save.await_args.args[1]
    assert len(saved['observations'])==8 and len(saved['source_documents'])==2
    assert saved['source_documents'][0]['coverage']=='unknown_legacy_document_coverage'
    assert saved['source_documents'][1]['observation_count']==4
    assert saved['source_documents'][1]['last_observation_date']=='2026-04-01'
    assert saved['failed_sources'][0]['source_url']==CURRENT_ATF_URL


@pytest.mark.parametrize('previous',[None,{'parser_version':1,'observations':None},
    {'parser_version':1,'observations':[None,{'date':'2026-01-01','city':'Delhi','value':True}]}])
def test_reviewed_atf_recovers_malformed_cache_without_importing_bad_observations(previous):
    saved=merge_reviewed_atf(previous,'reviewed',ATF_URL,atf_rows('2026-04-01'),'Historical')
    assert len(saved['observations'])==4


@pytest.mark.asyncio
async def test_incremental_fred_receipt_and_revised_aai_report_keep_prior_documents(monkeypatch):
    pdf_url='https://www.aai.aero/sites/default/files/traffic-news/Jan2k26Annex3.pdf'
    previous_fred=dict(parser_version=1,source_url='https://fred.stlouisfed.org/series/DCOILBRENTEU',
        source_sha256='older-fred',download_url='https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU&cosd=2023-01-01',
        observations=[dict(date='2023-01-02',value=90),dict(date='2026-01-01',value=100)])
    cache={'brent':{'data':previous_fred},'airport_traffic':{'data':dict(parser_version=1,
        observations=[dict(airport='DEL',period_month='2025-12',period_end='2025-12-31')],
        reports=[dict(source_url=pdf_url,source_sha256='older-pdf',period_end='2026-01-31')])}}
    context=SimpleNamespace(_lock=asyncio.Lock(),snapshot=AsyncMock(return_value=cache),_save=AsyncMock())
    async def fake_fetch(session,url,limit=5000000):
        if 'fredgraph.csv' in url:
            code='DCOILBRENTEU' if 'DCOILBRENTEU' in url else 'DEXINUS'
            return b'\xef\xbb\xbf'+f'observation_date,{code}\n2026-01-01,101\n2026-01-03,102\n'.encode()
        if url==pdf_url:
            return b'revised PDF bytes'
        if 'aai-traffic-news' in url:
            return b'<a href="https://www.aai.aero/sites/default/files/traffic-news/Jan2k26Annex3.pdf">Report</a>'
        raise ValueError('Intentionally unavailable isolated feed')
    monkeypatch.setattr('intelligence.fetch_bytes',fake_fetch)
    monkeypatch.setattr('intelligence.aai_pdf',lambda raw,url:[dict(airport='DEL',period_month='2026-01',period_end='2026-01-31')])
    monkeypatch.setattr('carrier_context.refresh_atf',AsyncMock())
    monkeypatch.setattr('carrier_context.refresh_capacity',AsyncMock())
    await MarketContext.refresh(context,force=True)
    saved={call.args[0]:call.args[1] for call in context._save.await_args_list}
    brent=saved['brent']
    assert len(brent['observations'])==3 and brent['observations'][1]['value']==101
    assert len(brent['source_documents'])==2
    assert brent['source_documents'][0]['coverage']=='unknown_legacy_document_coverage'
    latest=brent['source_documents'][1]
    assert latest['source_sha256']==hashlib.sha256(b'\xef\xbb\xbfobservation_date,DCOILBRENTEU\n2026-01-01,101\n2026-01-03,102\n').hexdigest()
    assert latest['first_observation_date']=='2026-01-01' and latest['observation_count']==2
    assert 'cosd=2025-12-18' in latest['download_url']
    traffic=saved['airport_traffic']
    assert len(traffic['observations'])==2 and len(traffic['source_documents'])==2
    assert traffic['source_documents'][0]['source_sha256']=='older-pdf'
    assert traffic['source_documents'][0]['coverage']=='unknown_legacy_document_coverage'
    assert traffic['source_documents'][1]['first_observation_date']=='2026-01-31'
    assert traffic['source_documents'][1]['observation_count']==1

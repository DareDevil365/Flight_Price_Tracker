"""Source boundary regressions. Test data is never imported into the live store."""
from datetime import date,timedelta
import pytest
from compiler import TaskCompiler,is_indian_airport
from evidence_feeds import fred_points,atf_rows,atf_html,aai_links,aai_text,AIRPORT_LABELS
from intelligence import MarketContext,SuggestionBrain
from tests.test_verified_pricing import database,TRIP


def test_domestic_gate_uses_country_reference_not_old_typo_list():
    compiler=TaskCompiler(None,None)
    trip=dict(origin='DEL',destination='JDH',departureDate=(date.today()+timedelta(days=35)).isoformat())
    compiler._validate_trip(trip)
    assert is_indian_airport('HDO') and is_indian_airport('GOX')
    for code in ('DXB','CMB','MUA','MTE','NGP','ZZZ'):
        with pytest.raises(ValueError,match='Indian'):
            compiler._validate_trip({**trip,'destination':code})
    with pytest.raises(ValueError):
        compiler._validate_trip({**trip,'origin':123})


def test_fred_future_nan_and_conflicting_revisions():
    raw='observation_date,X\n2026-01-02,100\n2026-01-01,.\n2099-01-01,10\n2026-01-03,nan\n2026-01-04,-1\n'
    assert fred_points(raw,'X',date(2026,10,8))==[dict(date='2026-01-02',value=100)]
    with pytest.raises(ValueError,match='Conflicting'):
        fred_points(raw+'2026-01-02,200\n','X',date(2026,10,8))
    with pytest.raises(ValueError):
        fred_points('<html>Access denied</html>','X')


def test_atf_dated_indian_grouping_and_future_rows():
    raw='January 1, 2026 | 92,323.02 | 95,378.02 | 86,352.19 | 95,770.00\nJanuary 1, 2099 | 10.00 | 20.00 | 30.00 | 40.00'
    rows=atf_rows(raw,date(2026,10,8))
    assert len(rows)==4 and {r['date'] for r in rows}=={'2026-01-01'}
    with pytest.raises(ValueError,match='grouping'):
        atf_rows(raw.replace('92,323.02','9,2323.02'),date(2026,10,8))
    with pytest.raises(ValueError):
        atf_html('<html>Javascript is required before you are allowed to see this page</html>')


def traffic_fixture(month='August',year=2026):
    # International and cumulative columns are deliberately incompatible values.
    rows='\n'.join(f'{i} {label} 1100 1000 10.0% 999999 888888' for i,label in enumerate(AIRPORT_LABELS.values(),1))
    return f'International Passengers\nDELHI (DIAL) 1 2 -50.0% 3 4\nDomestic Passengers\n{month} {month}\n{year} {year-1}\n{rows}\nANNEXURE-III C\nTotal Passengers\nDELHI (DIAL) 3 4 -25.0% 5 6'


def test_aai_domestic_monthly_columns_and_header_dates():
    rows=aai_text(traffic_fixture(),'https://www.aai.aero/report.pdf',date(2026,10,8))
    assert len(rows)==17 and rows[0]['domestic_current']==1100
    assert rows[0]['domestic_previous']==1000 and rows[0]['period_end']=='2026-08-31'
    older=traffic_fixture().replace('August August\n2026 2025','August August\nS.NO Airport April To August\n2026 2025').replace('DELHI (DIAL)','DELHI').replace('GOA (DABOLIM)','GOA')
    assert aai_text(older,'https://www.aai.aero/report.pdf',date(2026,10,8))[0]['domestic_current']==1100
    with pytest.raises(ValueError,match='Future'):
        aai_text(traffic_fixture('December'),'https://www.aai.aero/report.pdf',date(2026,10,8))
    with pytest.raises(ValueError,match='percentage'):
        aai_text(traffic_fixture().replace('1100 1000','2100 1000',1),'https://www.aai.aero/report.pdf',date(2026,10,8))
    with pytest.raises(ValueError,match='duplicated'):
        aai_text(traffic_fixture().replace('ANNEXURE-III C','DELHI (DIAL) 1100 1000 10.0% 1 2\nANNEXURE-III C'),'https://www.aai.aero/report.pdf',date(2026,10,8))


def test_aai_link_discovery_rejects_external_and_http_reports():
    raw='''<a href="https://www.aai.aero/sites/default/files/traffic-news/Aug2k26Annex3.pdf">report</a>
    <a href="https://evil.test/Aug2k26Annex3.pdf">report</a><a href="http://www.aai.aero/Jul2k26Annex3.pdf">report</a>'''
    assert aai_links(raw)==['https://www.aai.aero/sites/default/files/traffic-news/Aug2k26Annex3.pdf']


@pytest.mark.asyncio
async def test_context_bootstrap_cannot_seed_buy_or_numeric_certainty(database):
    context=MarketContext(database);await context.initialize()
    old=(date.today()-timedelta(days=100)).isoformat()
    future=(date.today()+timedelta(days=1)).isoformat()
    await context._save('indian_atf',dict(source_url='https://iocl.com/atf-domestic-airlines',units='INR/kilolitre',observations=[dict(date=old,city='Delhi',value=95000),dict(date=future,city='Delhi',value=1000000)]))
    await context._save('airport_traffic',dict(source_url='https://www.aai.aero/en/business-opportunities/aai-traffic-news',observations=[dict(period_end=old,airport=TRIP['origin'],domestic_current=1100,domestic_previous=1000)]))
    result=await SuggestionBrain(database,context).assess(TRIP,target_price=6000)
    assert result['signal']=='MONITOR' and result['certainty']['percent'] is None
    factors=[r for r in result['factors'] if r['kind'] in ('indian_atf','airport_traffic')]
    assert len(factors)==2 and all(r['stale'] for r in factors)
    assert result['forecast']['observed_days']==0


@pytest.mark.asyncio
async def test_truncated_coupon_terms_remain_unknown_after_database_roundtrip(database):
    from offer_parser import published_offer
    from offer_rules import evaluate_offer
    offer=published_offer('cleartrip','LONGCODE','10% flight discount. '+'Additional terms apply. '*110+'Only available to new customers.', 'https://www.cleartrip.com/offers')
    assert offer['eligibility_unconfirmed'] is True
    await database.add_coupon(offer)
    saved=await database.get_live_coupons('cleartrip')
    assert saved[0]['eligibility_unconfirmed'] is True
    assert evaluate_offer(saved[0],{}).status=='unknown'

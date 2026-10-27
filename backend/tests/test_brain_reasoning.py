"""Reasoning and context regressions; all invented test fixtures are disposable."""
from datetime import date,datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from advisor_evidence import history_rows,history_row_problem
from intelligence import MarketContext,SuggestionBrain
from travel_advisor import SmartAdvisor
from quotes import utc_now
from tests.test_verified_pricing import database,TRIP
from tests.test_quote_integrity import quote
from offer_parser import published_offer


def history(**extra):
    return {**dict(route='DEL-BOM',departure_date=TRIP['departure_date'],passenger_count=1,cabin_class='ECONOMY',
        price=5000,platform='cleartrip',verification='listed',evidence_version=2,quality_status='corroborated',
        observed_at=utc_now(),stops=0,departure_time='08:30',flight_number='6E-101'),**extra}


@pytest.mark.parametrize('change',[{'route':'BOM-DEL'},{'passenger_count':2},{'cabin_class':'BUSINESS'},
    {'departure_time':'22:30'},{'stops':1},{'platform':'mock'},{'evidence_version':0},
    {'quality_status':'flagged'},{'stops':None},{'departure_time':None}])
def test_history_boundary_does_not_trust_database_filtering(change):
    trip={**TRIP,'preferred_time':'MORNING','max_stops':0}
    assert history_rows([history()],trip)
    assert history_rows([history(**change)],trip)==[]


@pytest.mark.parametrize('evidence',[None,'bad-json','{"integrity":null}','{"integrity":{"status":"flagged"}}'])
def test_malformed_stored_evidence_cannot_be_exported_as_accepted(evidence):
    row=history(evidence=evidence)
    assert history_row_problem(row) is not None
    assert history_rows([row],TRIP)==[]


async def declining_history(database,trip):
    today=datetime.now(timezone.utc).date()
    last=None
    for index in range(70):
        day=today-timedelta(days=69-index)
        row=quote(str(day),'cleartrip',30000-index*200,integrity={'status':'corroborated'})
        row.update(departure_date=trip['departure_date'],best_coupon_code=None)
        row['savings_breakdown']['observed_at']=datetime.combine(day,datetime.min.time(),timezone.utc).isoformat()
        await database.record_quote(row)
        last=row
    return last


@pytest.mark.asyncio
async def test_deadline_does_not_approve_price_above_target(database):
    context=MarketContext(database);await context.initialize()
    trip={**TRIP,'departure_date':(date.today()+timedelta(days=5)).isoformat()}
    row=quote('near','cleartrip',5000,integrity={'status':'corroborated'});row['departure_date']=trip['departure_date']
    report=await SuggestionBrain(database,context).assess(trip,target_price=4000,current_quotes=[row])
    assert report['signal']=='MONITOR' and report['urgency']=='HIGH'
    assert report['decision_basis']['target_met'] is False
    assert 'target is not met' in report['reasoning'] and 'not a buy recommendation' in report['reasoning']


@pytest.mark.asyncio
async def test_validated_decline_takes_priority_over_historical_bargain(database):
    context=MarketContext(database);await context.initialize()
    trip={**TRIP,'departure_date':(date.today()+timedelta(days=90)).isoformat()}
    await declining_history(database,trip)
    report=await SuggestionBrain(database,context).assess(trip)
    assert report['forecast']['status']=='LOCAL_HOLDOUT_PASSED'
    assert report['signal']=='WAIT_AND_RECHECK'
    assert report['decision_basis']['rule']=='VALIDATED_LOCAL_TREND'
    assert report['certainty']['percent'] is None  # seven trials do not earn a probability


@pytest.mark.asyncio
async def test_global_headlines_and_fuel_do_not_become_unmeasured_domestic_vetoes(database):
    context=MarketContext(database);await context.initialize()
    trip={**TRIP,'departure_date':(date.today()+timedelta(days=90)).isoformat()}
    await declining_history(database,trip)
    await context._save('reported_news',[dict(title='War disrupts distant foreign airspace',url='https://example.test/story',published_at=utc_now(),primary_source=False)])
    await context._save('brent',dict(source_url='https://fred.stlouisfed.org/series/DCOILBRENTEU',units='USD/barrel',
        observations=[dict(date=(date.today()-timedelta(days=30)).isoformat(),value=60),dict(date=date.today().isoformat(),value=90)]))
    report=await SuggestionBrain(database,context).assess(trip)
    assert report['signal']=='WAIT_AND_RECHECK'
    assert report['decision_basis']['news_used_as_causal_prediction'] is False
    assert 'effect on this route is unmeasured' in report['reasoning']


@pytest.mark.asyncio
async def test_award_and_software_are_not_war_reports(database):
    context=MarketContext(database);await context.initialize()
    await context._save('reported_news',[dict(title='Airline wins award for forward software',url='https://example.test/award',published_at=utc_now())])
    report=await SuggestionBrain(database,context).assess(TRIP)
    assert not any(factor['kind']=='disruption' for factor in report['factors'])


@pytest.mark.asyncio
async def test_malformed_cache_and_unlinked_news_do_not_break_or_ground_advice(database):
    context=MarketContext(database);await context.initialize()
    for key in ('brent','indian_atf','airport_traffic','airline_capacity','reported_news'):
        await context._save(key,'bad-data')
    report=await SuggestionBrain(database,context).assess(TRIP)
    assert report['signal']=='MONITOR' and report['factors']==[] and report['news']==[]
    assert len(report['context_problems'])==5


@pytest.mark.asyncio
async def test_two_year_labels_do_not_claim_two_years_of_history(database):
    context=MarketContext(database);await context.initialize()
    # A historical fixture spanning a calendar boundary remains only two days.
    for day in ('2025-12-31','2026-01-01'):
        row=quote(day,'cleartrip',5000,integrity={'status':'corroborated'});row.update(best_coupon_code=None)
        row['savings_breakdown']['observed_at']=day+'T12:00:00+00:00'
        await database.record_quote(row)
    report=await SuggestionBrain(database,context).assess(TRIP)
    assert report['historical_years']==0 and report['observed_calendar_years']==[2025,2026]


@pytest.mark.asyncio
async def test_future_crawl_timestamp_cannot_confirm_future_coupon(database):
    context=MarketContext(database);await context.initialize()
    future=(date.today()+timedelta(days=1)).isoformat()
    offer=published_offer('cleartrip','FUTURE10','Domestic flight discount','https://www.cleartrip.com/offers',native=True)
    offer['valid_from']=future
    await database.add_coupon(offer)
    report=await SuggestionBrain(database,context).assess(TRIP)
    assert report['upcoming_offers']
    await database.db.execute('UPDATE live_offer_evidence SET observed_at=?',((datetime.now(timezone.utc)+timedelta(days=5)).isoformat(),))
    await database.db.commit()
    report=await SuggestionBrain(database,context).assess(TRIP)
    assert report['upcoming_offers']==[]


@pytest.mark.asyncio
async def test_carrier_utilisation_is_stale_context_and_cannot_seed_fares(database):
    context=MarketContext(database);await context.initialize()
    source='https://www.goindigo.in/information/domestic-operational-statistics.html'
    await context._save('airline_capacity',dict(source_url=source,observations=[dict(airline='IndiGo',period_end='2026-07-31',
        passengers=10000000,passenger_km_thousands=8000000,seat_km_thousands=10000000,load_factor_pct=80)]))
    report=await SuggestionBrain(database,context).assess(TRIP,target_price=5000)
    factor=next(f for f in report['factors'] if f['kind']=='airline_capacity')
    assert factor['value']==80 and factor['stale']
    assert 'not this directed route' in factor['interpretation']
    assert report['price'] is None and report['signal']=='MONITOR' and report['forecast']['observed_days']==0


@pytest.mark.asyncio
async def test_smart_advisor_uses_one_decision_for_verdict_and_confidence():
    predictor=SimpleNamespace(predict=AsyncMock(return_value={'route':'DEL → BOM','decision':dict(signal='MONITOR',reasoning='Legacy summary',confidence=None,urgency='LOW',recommended_book_by=None)}))
    brain=SimpleNamespace(assess=AsyncMock(return_value=dict(signal='BUY_CANDIDATE',reasoning='Target comparison',confidence='LOW',urgency='HIGH',recommended_book_by=date.today().isoformat())))
    report=await SmartAdvisor(None,predictor,brain=brain).get_advisory(TRIP,[])
    assert report['verdict']=='BUY_CANDIDATE' and report['urgency']=='HIGH' and report['confidence']=='LOW'
    assert report['recommended_book_by']==date.today().isoformat()

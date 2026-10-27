"""Adversarial forecast/advice fixtures stay in disposable databases."""
from datetime import date,datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from intelligence import calibrated_trend,daily_prices,MarketContext,SuggestionBrain
from advisor_evidence import matching_quote
from booking_advisor import PricePredictor
from travel_advisor import SmartAdvisor
from alternative_planner import connection_candidates
from tests.test_verified_pricing import database,TRIP,DAY
from tests.test_quote_integrity import quote
from tests.test_intelligence_and_red_room import leg


def trend():
    return [(date.today()-timedelta(days=209-i),30000-i*100) for i in range(210)]


@pytest.mark.parametrize('bad',[lambda p:p+[(date.today()+timedelta(days=1),9000)],
    lambda p:p+[p[-1]], lambda p:p[:-1]+[(date.today(),float('nan'))],
    lambda p:list(reversed(p)),lambda p:p[:-1]+[(date.today(),True)]])
def test_invalid_history_cannot_calibrate(bad):
    report=calibrated_trend(bad(trend()))
    assert report['forecast_7d'] is None and report['certainty']['percent'] is None


def test_changed_provider_coverage_withholds_retrospective_calibration():
    rows=[]
    for i,(day,price) in enumerate(trend()):
        rows.append(dict(observed_at=day.isoformat(),price=price,platform='easemytrip'))
        if i<150:
            rows.append(dict(observed_at=day.isoformat(),price=price-50,platform='cleartrip'))
    points=daily_prices(rows)
    assert len(points)==210
    assert calibrated_trend(points)['status']=='COVERAGE_CHANGED_WITHHELD'


def test_duplicate_scrapes_and_future_dates_do_not_inflate_independent_days():
    now=datetime.now(timezone.utc)
    rows=[dict(observed_at=now.isoformat(),price=5000)]*200
    rows += [dict(observed_at=(now+timedelta(days=1)).isoformat(),price=100),
             dict(observed_at='bad',price=1),dict(observed_at=now.isoformat(),price=float('inf'))]
    assert len(daily_prices(rows))==1


@pytest.mark.parametrize('age',[timedelta(hours=1),timedelta(days=-1)])
def test_old_or_future_checkout_cannot_be_buying_evidence(age):
    row=quote('cart','cleartrip',5000,verification='checkout',integrity={'status':'checkout_verified'})
    row['savings_breakdown']['observed_at']=(datetime.now(timezone.utc)-age).isoformat()
    assert not matching_quote(row,TRIP)


@pytest.mark.asyncio
async def test_specific_flight_cannot_borrow_other_flight_history(database):
    context=MarketContext(database);await context.initialize()
    row=quote('other','cleartrip',1000,integrity={'status':'corroborated'})
    row.update(best_coupon_code=None)
    await database.record_quote(row)
    report=await SuggestionBrain(database,context).assess({**TRIP,'specific_flight_number':'AI999'},target_price=5000)
    assert report['price'] is None and report['forecast']['observed_days']==0


@pytest.mark.asyncio
async def test_predictor_rejects_future_and_naive_timestamps_and_honors_airline(database):
    now=datetime.now(timezone.utc)
    for stamp,price,airline in [(now+timedelta(days=1),10,'IndiGo'),(now.replace(tzinfo=None),20,'IndiGo'),(now,1000,'Air India'),(now,5000,'IndiGo')]:
        row=quote(str(price),'cleartrip',price,verification='checkout',integrity={'status':'checkout_verified'})
        row.update(airline=airline,best_coupon_code=None)
        row['savings_breakdown']['observed_at']=stamp.isoformat()
        await database.record_quote(row)
    report=await PricePredictor(database).predict('DEL-BOM',DAY,airline='IndiGo')
    assert report['current_price'] is None
    assert report['data_freshness']['archived_checkout_receipts']==1
    assert report['price_context']['vs_90d_average'] is None


@pytest.mark.asyncio
async def test_current_wrong_direction_cannot_create_layover_saving():
    predictor=SimpleNamespace(predict=AsyncMock(return_value=dict(route='DEL → BOM',decision=dict(
        reasoning='Monitor',signal='MONITOR',urgency='LOW',confidence=None,recommended_book_by=None))))
    direct=quote('direct','cleartrip',6000,integrity={'status':'corroborated'})
    reverse=quote('reverse','easemytrip',100,origin='BOM',destination='DEL',integrity={'status':'corroborated'})
    reverse['stops']=1
    report=await SmartAdvisor(None,predictor).get_advisory(TRIP,[direct,reverse])
    assert report['suggestions']==[]


@pytest.mark.asyncio
async def test_bare_date_saving_claim_requires_exact_evidence():
    predictor=SimpleNamespace(predict=AsyncMock(return_value=dict(route='DEL → BOM',decision=dict(
        reasoning='Monitor',signal='MONITOR',urgency='LOW',confidence=None,recommended_book_by=None))))
    report=await SmartAdvisor(None,predictor).get_advisory(TRIP,[],date_alternatives=[{'date':DAY,'savings':99999}])
    assert report['suggestions']==[]


@pytest.mark.asyncio
async def test_stale_listing_snapshot_cannot_create_roundtrip_total():
    predictor=SimpleNamespace(predict=AsyncMock(return_value=dict(route='DEL → BOM',decision=dict(
        reasoning='Monitor',signal='MONITOR',urgency='LOW',confidence=None,recommended_book_by=None))))
    row=quote('out','cleartrip',8000,verification='checkout',listed_price=2000,integrity={'status':'checkout_verified'})
    row['savings_breakdown']['listed_observed_at']=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
    inbound=quote('back','cleartrip',2000,origin='BOM',destination='DEL',integrity={'status':'corroborated'})
    inbound['savings_breakdown']['direction']='inbound'
    report=await SmartAdvisor(None,predictor).get_advisory({**TRIP,'trip_type':'round_trip','return_date':DAY},[row,inbound])
    assert 'separate outbound and return' not in report['advice']


def test_self_transfer_rejects_contradictory_second_leg_schedule():
    a=leg('DEL','BOM',DAY,'06:00','08:00','2h',3000)
    b=leg('BOM','GOI',DAY,'13:00','14:20','1h 20m',2000)
    assert connection_candidates([a],[b],6000)
    assert not connection_candidates([a],[{**b,'arrival_time':'12:00'}],6000)
    assert not connection_candidates([a],[b],float('nan'))

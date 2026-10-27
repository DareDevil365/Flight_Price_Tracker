from quote_integrity import check_outputs
from quotes import utc_now
from tests.test_verified_pricing import database, TRIP, DAY
import pytest

def quote(id,platform,price,**extra):
    meta=dict(origin='DEL',destination='BOM',passenger_count=1,cabin_class='ECONOMY',direction='outbound',currency='INR',verification='listed',observed_at=utc_now())
    meta.update(extra)
    return dict(id=id,platform=platform,airline='IndiGo',flight_number='6E-101',departure_date=DAY,departure_time='08:30',arrival_time='10:30',stops=0,final_price=price,savings_breakdown=meta)

def test_too_good_fare_quarantined_and_google_not_infallible():
    rows=[quote('good','google_flights',5000),quote('agree','easemytrip',5050),quote('bad','cleartrip',50)]
    checks=check_outputs(rows,TRIP)
    assert checks['bad']['status']=='flagged'
    assert checks['good']['status']==checks['agree']['status']=='corroborated'
    rows=[quote('bad','google_flights',50),quote('good','easemytrip',5000),quote('agree','cleartrip',5050)]
    assert check_outputs(rows,TRIP)['bad']['status']=='flagged'

def test_reverse_route_date_and_cabin_cannot_supply_peer_evidence():
    good=quote('good','cleartrip',5000)
    reversed=quote('reverse','google_flights',5000,origin='BOM',destination='DEL')
    checks=check_outputs([good,reversed],TRIP)
    assert checks['reverse']['status']=='flagged' and checks['good']['status']=='uncorroborated'
    for change in [dict(cabin_class='BUSINESS'),dict(passenger_count=2),dict(currency='USD')]:
        assert check_outputs([quote('bad','cleartrip',5000,**change)],TRIP)['bad']['status']=='flagged'

def test_low_agreed_fare_has_no_arbitrary_floor_and_two_source_disagreement_is_held():
    rows=[quote('a','google_flights',450),quote('b','easemytrip',460)]
    assert all(v['status']=='corroborated' for v in check_outputs(rows,TRIP).values())
    rows=[quote('a','google_flights',450),quote('b','easemytrip',5000)]
    assert all(v['status']=='flagged' for v in check_outputs(rows,TRIP).values())

@pytest.mark.asyncio
async def test_unchecked_flagged_and_reversed_history_never_reaches_brain(database):
    for status in ('flagged','uncorroborated','pending'):
        row=quote(status,'cleartrip',50);row['best_coupon_code']=None
        row['savings_breakdown']['integrity']=dict(status=status)
        await database.record_quote(row)
    assert await database.get_quotes('DEL-BOM',DAY)==[]
    row=quote('real','cleartrip',5000);row['best_coupon_code']=None
    row['savings_breakdown']['integrity']=dict(status='corroborated')
    await database.record_quote(row)
    assert len(await database.get_quotes('DEL-BOM',DAY))==1
    assert await database.get_quotes('BOM-DEL',DAY)==[]

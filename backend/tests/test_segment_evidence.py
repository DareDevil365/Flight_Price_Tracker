from copy import deepcopy

import pytest

from segment_evidence import segment_identity_problem
from tests.test_verified_pricing import database


SUMMARY = dict(origin='DEL', destination='CCU', departure_date='2026-11-23',
               departure_time='20:55', arrival_time='23:25', stops=0,
               flight_number='QP-1260', airline='Akasa Air', cabin_class='ECONOMY')
LEG = dict(origin='DEL', destination='CCU', departure_date='2026-11-23',
           departure_datetime='2026-11-23T20:55:00', arrival_datetime='2026-11-23T23:25:00',
           airline='Akasa Air', flight_number='QP-1260', duration=150)


def check(segments, **changes):
    return segment_identity_problem(segments, **{**SUMMARY, **changes})


def test_real_retained_fli_corruption_is_rejected_without_changing_price_or_source():
    leg = {**LEG, 'airline': 'Air Kenya Aviation'}
    original = deepcopy(leg)
    assert 'corrupt QP' in check([leg])
    assert leg == original
    assert check([LEG]) is None


@pytest.mark.parametrize('key,value', [
    ('origin', 'BOM'), ('destination', 'HYD'), ('departure_date', '2026-11-24'),
    ('flight_number', '6E-9999'), ('departure_datetime', '2026-11-23T01:00:00'),
    ('arrival_datetime', '2026-11-23T20:54:00'), ('duration', 2),
    ('duration', True), ('duration', float('nan')), ('cabin_class', 'BUSINESS'),
    ('departure_datetime', '2026-11-23T20:55:00+00:00'),
    ('departure_datetime', '2026-11-23'), ('flight_number', ''),
    ('origin', 'del'), ('arrival_datetime', None),
])
def test_present_contradictory_segment_never_passes(key, value):
    assert check([{**LEG, key: value}]) is not None


@pytest.mark.parametrize('segments', [None, []])
def test_absent_nonstop_evidence_remains_allowed_but_connections_require_legs(segments):
    assert check(segments) is None
    assert check(segments, stops=1) is not None


@pytest.mark.parametrize('segments', [{}, 'DEL-CCU', [None], [LEG, LEG]])
def test_malformed_or_wrong_count_is_rejected(segments):
    assert check(segments) is not None


def test_timezone_and_number_formatting_are_supported():
    leg = {**LEG, 'flight_number': 'QP1260',
           'departure_datetime': LEG['departure_datetime']+'+05:30',
           'arrival_datetime': LEG['arrival_datetime']+'+05:30'}
    assert check([leg]) is None


def test_operator_and_marketing_labels_need_not_be_equal():
    # Codeshares and mixed carriers require provider/operator evidence rather
    # than an unsupported blanket string-equality policy.
    assert check([{**LEG, 'airline': 'QP'}]) is None
    assert check([{**LEG, 'airline': 'Operating carrier label'}]) is None


def connecting():
    return [dict(origin='DEL', destination='BOM', departure_datetime='2026-11-23T20:55:00',
                 arrival_datetime='2026-11-23T23:25:00', airline='Akasa Air', flight_number='QP-1260'),
            dict(origin='BOM', destination='CCU', departure_datetime='2026-11-24T01:25:00',
                 arrival_datetime='2026-11-24T03:55:00', airline='IndiGo', flight_number='6E-456')]


def test_overnight_mixed_carrier_connection_is_valid():
    assert check(connecting(), stops=1, flight_number='', arrival_time='03:55') is None


@pytest.mark.parametrize('key,value', [
    ('origin', 'AMD'), ('departure_datetime', '2026-11-23T22:00:00'),
    ('destination', 'GOI'), ('departure_date', '2026-11-23'),
])
def test_broken_connection_chain_and_timeline_are_rejected(key, value):
    legs = connecting()
    legs[1][key] = value
    assert check(legs, stops=1, flight_number='', arrival_time='03:55') is not None


def test_summary_arrival_mismatch_is_rejected():
    assert check([LEG], arrival_time='23:35') is not None


def test_international_connection_cannot_enter_domestic_evidence():
    legs = connecting()
    legs[0]['destination'] = legs[1]['origin'] = 'DXB'
    assert 'non-Indian' in check(legs, stops=1, flight_number='', arrival_time='03:55')


def test_connection_date_only_timestamp_is_not_a_full_clock():
    legs = connecting()
    legs[1]['departure_datetime'] = '2026-11-24'
    assert 'full local date and time' in check(legs, stops=1, flight_number='', arrival_time='03:55')


def test_corrupt_segment_cannot_vote_for_other_fare():
    from quote_integrity import check_outputs
    from quotes import utc_now
    meta=dict(origin='DEL', destination='CCU', passenger_count=1, cabin_class='ECONOMY',
        verification='listed',currency='INR',direction='outbound',observed_at=utc_now())
    good=dict(id='peer',platform='easemytrip',airline='Akasa Air',flight_number='QP-1260',
        departure_date='2026-11-23',departure_time='20:55',arrival_time='23:25',stops=0,
        final_price=8841,savings_breakdown=meta)
    bad={**good,'id':'bad','platform':'google_flights','final_price':9191,
        'savings_breakdown':{**meta,'segments':[{**LEG,'airline':'Air Kenya Aviation'}]}}
    trip=dict(origin='DEL',destination='CCU',departure_date='2026-11-23',
        passenger_count=1,cabin_class='ECONOMY',preferred_time='ANY',max_stops=None)
    output=check_outputs([good,bad],trip)
    assert output['bad']['status']=='flagged'
    assert output['peer']['status']=='uncorroborated'


def test_saved_segment_contradiction_is_excluded_from_history_and_output_advice():
    import json
    from advisor_evidence import history_row_problem,matching_quote
    from quotes import utc_now
    meta=dict(origin='DEL',destination='CCU',passenger_count=1,cabin_class='ECONOMY',
        verification='listed',observed_at=utc_now(),integrity={'status':'corroborated'},
        segments=[{**LEG,'origin':'BOM'}])
    row=dict(route='DEL-CCU',departure_date='2026-11-23',passenger_count=1,cabin_class='ECONOMY',
        platform='google_flights',airline='Akasa Air',flight_number='QP-1260',departure_time='20:55',
        stops=0,price=9191,verification='listed',observed_at=meta['observed_at'],
        quality_status='corroborated',evidence_version=2,evidence=json.dumps(meta))
    assert 'endpoints' in history_row_problem(row)
    assert not matching_quote({**row,'final_price':9191,'savings_breakdown':meta},meta|{'departure_date':'2026-11-23'})


def test_cached_reference_cannot_corroborate_current_listing_even_when_amounts_agree():
    from quote_integrity import check_outputs
    from advisor_evidence import matching_quote
    from quotes import utc_now
    meta=dict(origin='DEL',destination='CCU',passenger_count=1,cabin_class='ECONOMY',
        verification='listed',currency='INR',direction='outbound',observed_at=utc_now())
    row=dict(id='live',platform='easemytrip',airline='Akasa Air',flight_number='QP-1260',
        departure_date='2026-11-23',departure_time='20:55',arrival_time='23:25',stops=0,
        final_price=8841,savings_breakdown=meta)
    reference={**row,'id':'ref','platform':'makemytrip','savings_breakdown':{**meta,
        'source_transport':'makemytrip_public_mcp','source_learning_allowed':False}}
    trip=dict(origin='DEL',destination='CCU',departure_date='2026-11-23',
        passenger_count=1,cabin_class='ECONOMY',preferred_time='ANY',max_stops=None)
    output=check_outputs([row,reference],trip)
    assert output['live']['status']==output['ref']['status']=='uncorroborated'
    assert 'cached' in output['ref']['reasons'][0]
    reference['savings_breakdown']['integrity']={'status':'corroborated'}
    assert not matching_quote(reference,trip)


@pytest.mark.asyncio
@pytest.mark.parametrize('restriction',[
    {'source_learning_allowed':False},
    {'source_transport':'makemytrip_public_mcp'},
    {'segments':[{**LEG,'airline':'Air Kenya Aviation'}]},
])
async def test_forged_accepted_status_cannot_persist_unusable_evidence(database,restriction):
    from quotes import utc_now
    meta=dict(origin='DEL',destination='CCU',passenger_count=1,cabin_class='ECONOMY',
        verification='listed',observed_at=utc_now(),integrity={'status':'corroborated'},**restriction)
    row=dict(id='forged',platform='google_flights',airline='Akasa Air',flight_number='QP-1260',
        departure_date=SUMMARY['departure_date'],departure_time=SUMMARY['departure_time'],
        arrival_time=SUMMARY['arrival_time'],stops=0,final_price=9191,best_coupon_code=None,
        savings_breakdown=meta)
    await database.record_quote(row)
    assert await database.get_quotes('DEL-CCU',SUMMARY['departure_date'])==[]

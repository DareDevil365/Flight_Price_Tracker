"""Readiness is a dates-only milestone, never fabricated fare observations."""
from datetime import date,timedelta
from intelligence import calibrated_trend,forecast_readiness,PriceSeries
from intelligence import constrain_forecast_to_trip,MarketContext,SuggestionBrain
from tests.test_verified_pricing import database,TRIP
from tests.test_quote_integrity import quote
from datetime import datetime,timezone
import pytest


def observations(count):
    return [(date.today()-timedelta(days=count-i-1),20000-i*20) for i in range(count)]


def test_empty_and_one_day_cold_start_milestones_are_conditional():
    empty=forecast_readiness([])
    assert empty['training_days_remaining']==21
    assert empty['minimum_additional_daily_observations_for_forecast']==70
    one=calibrated_trend(observations(1))['readiness']
    assert one['training_days_remaining']==20
    assert one['weekly_outcomes_remaining_for_forecast']==7
    assert one['minimum_additional_daily_observations_for_forecast']==69
    assert one['minimum_additional_daily_observations_for_certainty']==160
    assert one['earliest_forecast_evidence_date']==(date.today()+timedelta(days=69)).isoformat()
    assert any('may never qualify' in text for text in one['assumptions'])


def test_training_is_not_confused_with_holdout_readiness():
    report=calibrated_trend(observations(21))
    readiness=report['readiness']
    assert readiness['training_days_remaining']==0
    assert readiness['weekly_outcomes_observed']==0
    assert readiness['minimum_additional_daily_observations_for_forecast']==49
    assert report['forecast_7d'] is None


def test_partial_week_progress_uses_existing_training_origins():
    report=calibrated_trend(observations(27))
    assert report['readiness']['minimum_additional_daily_observations_for_forecast']==43
    report=calibrated_trend(observations(28))
    assert report['readiness']['weekly_outcomes_observed']==1
    assert report['readiness']['minimum_additional_daily_observations_for_forecast']==42


def test_seven_windows_can_enable_forecast_but_do_not_invent_certainty():
    report=calibrated_trend(observations(70))
    readiness=report['readiness']
    assert report['status']=='LOCAL_HOLDOUT_PASSED'
    assert readiness['weekly_outcomes_observed']==7
    assert readiness['minimum_additional_daily_observations_for_forecast']==0
    assert readiness['weekly_outcomes_remaining_for_certainty']==13
    assert readiness['minimum_additional_daily_observations_for_certainty']==91
    assert report['certainty']['percent'] is None


def test_counts_alone_cannot_pass_accuracy_gate():
    report=calibrated_trend([(day,5000) for day,price in observations(161)])
    assert report['readiness']['weekly_outcomes_observed']==20
    assert report['readiness']['weekly_outcomes_remaining_for_certainty']==0
    assert report['forecast_7d'] is None
    assert report['certainty']['percent'] is None
    assert any('accuracy' in text for text in report['readiness']['blockers'])


def test_coverage_changed_and_invalid_history_have_no_promised_dates():
    points=PriceSeries(observations(50));points.coverage_stable=False
    report=calibrated_trend(points)['readiness']
    assert report['earliest_forecast_evidence_date'] is None
    assert report['minimum_additional_daily_observations_for_forecast'] is None
    points=observations(1)*200
    report=calibrated_trend(points)['readiness']
    assert report['earliest_forecast_evidence_date'] is None
    assert report['blockers']


def test_missed_historical_windows_are_not_filled_with_hypothetical_prices():
    points=[(date.today()-timedelta(days=120-i*4),10000-i*10) for i in range(21)]
    report=calibrated_trend(points)['readiness']
    assert report['weekly_outcomes_observed']==0
    assert report['minimum_additional_daily_observations_for_forecast']==50
    assert any('stale' in text for text in report['blockers'])


def test_deadline_withholds_a_forecast_even_with_calibrated_history():
    forecast=calibrated_trend(observations(161))
    assert forecast['certainty']['percent']==100
    count=forecast['readiness']['weekly_outcomes_observed']
    departure=(date.today()+timedelta(days=7)).isoformat()
    constrained=constrain_forecast_to_trip(forecast,departure)
    assert constrained['status']=='DEPARTURE_BEFORE_FORECAST_HORIZON'
    assert constrained['forecast_7d'] is None
    assert constrained['certainty']['percent'] is None
    assert constrained['readiness']['weekly_outcomes_observed']==count
    assert any('prediction is withheld' in message for message in constrained['readiness']['blockers'])


def test_one_day_cannot_promise_readiness_before_a_nearby_departure():
    departure=(date.today()+timedelta(days=30)).isoformat()
    forecast=constrain_forecast_to_trip(calibrated_trend(observations(1)),departure)
    assert forecast['readiness']['forecast_evidence_possible_before_departure'] is False
    assert forecast['readiness']['certainty_evidence_possible_before_departure'] is False
    assert any('cannot mature before this flight' in message for message in forecast['readiness']['blockers'])


@pytest.mark.asyncio
async def test_assess_never_publishes_a_post_departure_fare(database):
    context=MarketContext(database);await context.initialize()
    departure=(date.today()+timedelta(days=3)).isoformat()
    # Recorded timestamps use UTC. Local midnight in India can still be the
    # previous UTC date, so never fabricate a future midnight observation.
    utc_today=datetime.now(timezone.utc).date()
    for index in range(70):
        day=utc_today-timedelta(days=69-index)
        price=20000-index*20
        row=quote(str(day),'cleartrip',price,integrity={'status':'corroborated'})
        row.update(departure_date=departure,best_coupon_code=None)
        row['savings_breakdown']['observed_at']=datetime.combine(day,datetime.min.time(),tzinfo=timezone.utc).isoformat()
        await database.record_quote(row)
    report=await SuggestionBrain(database,context).assess({**TRIP,'departure_date':departure})
    assert report['forecast']['readiness']['weekly_outcomes_observed']==7
    assert report['forecast']['status']=='DEPARTURE_BEFORE_FORECAST_HORIZON'
    assert report['forecast']['forecast_7d'] is None
    assert report['signal']!='WAIT_AND_RECHECK'

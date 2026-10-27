"""Source parsing fixtures never enter the live evidence store."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from carrier_context import capacity_text,current_atf_html,refresh_capacity,refresh_atf

HEADER = '''Monthly Operational Statistics for FY 2025-26 on scheduled domestic services
MONTH | PASSENGERS CARRIED (IN NUMBER) | PASSENGER KMS.PERFORMED (IN THOUSAND) | AVAILABLE SEAT KILOMETRE (IN THOUSAND) | PAX.LOAD FACTOR# (IN %)'''
ROW = 'APR | 100 | 200 | 300 | 1,000 | 800 | 1,000 | 80.0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9'
ATF = '''<h2>ATF Prices in Metros (Rupees/Kl) for Domestic Airlines</h2><h3>Last updated on April 1, 2026</h3>
<table><tr><th>Metros</th><th>Prices</th></tr><tr><td>Delhi</td><td>1,04,927</td></tr>
<tr><td>Kolkata</td><td>1,09,450</td></tr><tr><td>Mumbai</td><td>98,247</td></tr><tr><td>Chennai</td><td>1,09,873</td></tr></table>
<h2>ATF Prices in Metros (Dollars/Kl) for International Run</h2><h3>Last updated on October 1, 2026</h3>
<footer>Last updated on October 8, 2026</footer>'''


def test_fiscal_calendar_scope_and_ratio_validation():
    rows = capacity_text(HEADER+'\n'+ROW+'\n'+ROW.replace('APR','JAN'),date(2026,10,9))
    assert [r['period_month'] for r in rows]==['2025-04','2026-01']
    assert rows[0]['passengers']==1000 and rows[0]['seat_km_thousands']==1000
    assert rows[0]['load_factor_pct']==80
    with pytest.raises(ValueError,match='load factor'):
        capacity_text(HEADER+'\n'+ROW.replace('80.0','82.0'))
    with pytest.raises(ValueError,match='grouping'):
        capacity_text(HEADER+'\n'+ROW.replace('1,000','1,00'))


def test_blank_truncated_and_future_rows_never_become_zero_or_training_samples():
    rejected=[]
    blank='MAY | '+' | '.join('' for _ in range(16))
    rows=capacity_text(HEADER+'\n'+ROW+'\n'+blank+'\nJUN | 100 | 200',rejected=rejected)
    assert len(rows)==1 and rejected[0]['month']=='JUN'
    with pytest.raises(ValueError,match='No dated'):
        capacity_text(HEADER.replace('2025-26','2027-28')+'\n'+ROW,date(2026,10,9))
    assert 'price' not in rows[0] and 'fare' not in rows[0]


@pytest.mark.parametrize('replacement',[('FY 2025-26','FY 2025-27'),('domestic services','international services'),('IN THOUSAND','IN MILLION'),('PASSENGERS CARRIED','OTHER COLUMN')])
def test_source_scope_or_units_change_is_not_guessed(replacement):
    with pytest.raises(ValueError):
        capacity_text((HEADER+'\n'+ROW).replace(*replacement))


def test_domestic_atf_date_is_local_to_its_block_not_footer_or_usd_section():
    rows=current_atf_html(ATF,date(2026,10,9))
    assert len(rows)==4 and {r['date'] for r in rows}=={'2026-04-01'}
    assert {r['units'] for r in rows}=={'INR/kilolitre'}
    assert next(r for r in rows if r['city']=='Delhi')['value']==104927


@pytest.mark.parametrize('replacement',[('Rupees/Kl','Dollars/Kl'),('April 1, 2026','April 1, 2099'),('<td>1,04,927</td>','<td>1,04927</td>'),('<td>Chennai</td>','<td>Unknown</td>')])
def test_atf_changed_currency_future_date_and_malformed_row_fail(replacement):
    with pytest.raises(ValueError):
        current_atf_html(ATF.replace(*replacement),date(2026,10,9))


@pytest.mark.asyncio
async def test_failed_capacity_refresh_keeps_prior_dated_cache(monkeypatch):
    context=SimpleNamespace(_save=AsyncMock())
    monkeypatch.setattr('carrier_context.fetch_bytes',AsyncMock(side_effect=TimeoutError))
    status={}
    await refresh_capacity(context,None,status)
    context._save.assert_not_awaited()
    assert 'retain their actual reporting months' in status['airline_capacity']


@pytest.mark.asyncio
async def test_failed_atf_sources_do_not_overwrite_or_refresh_cached_date(monkeypatch):
    context=SimpleNamespace(_save=AsyncMock(),snapshot=AsyncMock(return_value={'indian_atf':{'data':{'parser_version':1,'observations':[]}}}))
    monkeypatch.setattr('carrier_context.fetch_bytes',AsyncMock(side_effect=ValueError('access denied')))
    status={}
    await refresh_atf(context,None,status)
    context._save.assert_not_awaited()
    assert 'both published tables failed' in status['indian_atf']


@pytest.mark.asyncio
@pytest.mark.parametrize('previous',[None,{'parser_version':1,'observations':None},
    {'parser_version':1,'observations':[None,{'date':'2026-04-01','city':'Delhi','value':True,'units':'INR/kilolitre'}]}])
async def test_valid_source_recovers_malformed_cache_without_importing_bad_rows(monkeypatch,previous):
    context=SimpleNamespace(_save=AsyncMock(),snapshot=AsyncMock(return_value={'indian_atf':{'data':previous}}))
    monkeypatch.setattr('carrier_context.fetch_bytes',AsyncMock(side_effect=[ValueError('blocked'),ATF.encode()]))
    await refresh_atf(context,None,{})
    saved=context._save.await_args.args[1]
    assert len(saved['observations'])==4 and saved['as_of']=='2026-04-01'
    assert all(not isinstance(row['value'],bool) for row in saved['observations'])
    assert len(saved['failed_sources'])==1

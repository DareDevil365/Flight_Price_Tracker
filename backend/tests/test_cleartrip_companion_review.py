"""Real-layout-inspired local fixtures, never a payment verification claim."""
import json

import pytest

from tests.test_browser_companion import SCRIPT,page


TRIP=dict(origin='BLR',destination='LKO',departure_date='2027-02-23',passenger_count=1,
          cabin_class='ECONOMY',flight_number='QP-1521',departure_time='12:25')
REVIEW='''<article><div><div><h1>Review your itinerary</h1></div>
<p>Tue, 23 Feb 2027</p><p>QP-1521</p><p>SAVER</p>
<div><div><h2>12:25</h2><h2><span>BLR</span></h2><p>Terminal 1</p></div>
<div><h2>15:05</h2><h2><span>LKO</span></h2><p>Terminal 3</p></div></div>
</div></article>
<aside><div><div><h3>Total Price</h3><h2>₹6,785</h2></div><div><p>1 Adult</p></div></div>
<div><p>Base Fare</p><p>₹4,624</p></div><div><p>Taxes</p><p>₹2,161</p></div></aside>
<div><h4 class="nepCouponTagCode">BBDHDFC</h4><h4 class="nepCouponTagCode">CTBBD</h4></div>
<h1>Review contact details</h1><div class="contact"><p>private@example.invalid</p></div>
<h1>Review traveller details</h1><input value="PRIVATE NAME"><textarea>PRIVATE NOTES</textarea>
<button>Continue</button>'''


async def capture(page,html=REVIEW,trip=TRIP):
    await page.goto('https://www.cleartrip.com/flights/itinerary/private-booking/info?secret=private')
    await page.set_content(html)
    await page.add_script_tag(content=SCRIPT)
    return await page.evaluate('(trip)=>captureCheckout(trip)',trip)


@pytest.mark.asyncio
async def test_observed_cleartrip_review_fields_remain_explicitly_partial(page):
    result=await capture(page)
    assert result['stage']=='review' and result['status']=='review_partial'
    assert result['displayed_trip']==dict(origin='BLR',destination='LKO',departure_date='2027-02-23',
        departure_time='12:25',arrival_time='15:05',flight_number='QP1521',passenger_count=1)
    assert result['merchant_total']==6785 and result['currency']=='INR'
    assert result['published_coupon_codes']==['BBDHDFC','CTBBD']
    assert not result['criteria_match'] and result['selected_payment'] is None and result['fees']==[]
    assert not result['usable_as_final_price'] and not result['eligible_for_learning']
    assert 'Cabin has not been established on this review layout' in result['reasons']
    assert all(secret not in json.dumps(result) for secret in ['PRIVATE','private@','private-booking','secret'])


@pytest.mark.asyncio
@pytest.mark.parametrize('change',[
    {'origin':'LKO','destination':'BLR'}, {'departure_date':'2026-02-23'},
    {'flight_number':'IX-2019'}, {'departure_time':'15:05'}, {'passenger_count':2},
])
async def test_expected_values_do_not_replace_review_observations(page,change):
    result=await capture(page,trip={**TRIP,**change})
    assert not result['criteria_match']
    assert result['displayed_trip']['origin']=='BLR'
    assert any('missing or different' in reason for reason in result['reasons'])


@pytest.mark.asyncio
@pytest.mark.parametrize('date',['Tue, 23 Feb','Tue, 31 Feb 2027','Tue, 23 Feb 2026'])
async def test_full_valid_observed_year_required_and_never_inferred(page,date):
    result=await capture(page,REVIEW.replace('Tue, 23 Feb 2027',date))
    assert not result['criteria_match']
    assert 'departure_date missing or different' in result['reasons']
    if date!='Tue, 23 Feb 2026':
        assert 'departure_date' not in result['displayed_trip']


@pytest.mark.asyncio
@pytest.mark.parametrize('money',['USD 78','₹6,78','₹6785.999','₹-6785'])
async def test_review_money_must_be_unambiguous_explicit_inr(page,money):
    result=await capture(page,REVIEW.replace('₹6,785',money))
    assert result['merchant_total'] is None and result['currency'] is None


@pytest.mark.asyncio
async def test_review_rejects_duplicate_visible_total_and_ignores_hidden_codes(page):
    result=await capture(page,REVIEW+'<div><h3>Total Price</h3><h2>₹1</h2></div>')
    assert result['merchant_total'] is None
    result=await capture(page,REVIEW+'<h4 class="nepCouponTagCode" style="display:none">FAKE</h4>')
    assert result['published_coupon_codes']==['BBDHDFC','CTBBD']


@pytest.mark.asyncio
@pytest.mark.parametrize('attribute',['style="opacity:0"','aria-hidden="true"','hidden','inert'])
async def test_review_ignores_coupon_codes_hidden_by_ancestors(page,attribute):
    result=await capture(page,REVIEW+f'<div {attribute}><h4 class="nepCouponTagCode">FAKE</h4></div>')
    assert result['published_coupon_codes']==['BBDHDFC','CTBBD']


@pytest.mark.asyncio
async def test_review_capture_never_clicks_continue_or_mutates_dom(page):
    await capture(page)
    await page.evaluate("()=>{window.clicked=0;document.querySelector('button').onclick=()=>window.clicked++;}")
    before=await page.content()
    await page.evaluate('(trip)=>captureCheckout(trip)',TRIP)
    assert await page.content()==before and await page.evaluate('window.clicked')==0


@pytest.mark.asyncio
@pytest.mark.parametrize('count,accepted',[(387,True),(500,True),(501,False)])
async def test_review_uses_its_own_bounded_real_layout_capacity(page,count,accepted):
    await capture(page)
    actual=await page.evaluate('''count=>{
        const scope=document.querySelector('h1').parentElement.parentElement;
        while(scope.querySelectorAll('*').length<count)scope.appendChild(document.createElement('span'));
        return scope.querySelectorAll('*').length;
    }''',count)
    assert actual==count
    result=await page.evaluate('(trip)=>captureCheckout(trip)',TRIP)
    if accepted:
        assert result['displayed_trip']['origin']=='BLR'
        assert result['displayed_trip']['departure_date']=='2027-02-23'
    else:
        assert 'origin' not in result['displayed_trip']
        assert 'One bounded supported itinerary summary was not found' in result['reasons']
    assert not result['criteria_match'] and not result['usable_as_final_price']

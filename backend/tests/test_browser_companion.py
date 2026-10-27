"""Normal-browser companion contract tests; all documents are local fixtures."""
import json
from pathlib import Path
import pytest
import pytest_asyncio
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=(ROOT/'browser-companion'/'capture.js').read_text(encoding='utf-8').replace('export function captureCheckout','function captureCheckout',1)
TRIP=dict(origin='DEL',destination='BOM',departure_date='2026-11-25',passenger_count=1,
          cabin_class='ECONOMY',flight_number='6E-123',departure_time='08:30')
HTML='''<section id="bookingSummary">
<div>DEL–BOM</div><div>2026-11-25</div><div>08:30</div><div>6E-123</div>
<div>1 adult</div><div>Economy</div><div>Convenience fee ₹350</div><div>Total payable ₹5,350</div>
<div class="passenger"><div>PRIVATE NAME</div><div>private@example.test</div></div>
<input value="private passenger"><textarea>PRIVATE NOTES</textarea>
</section><div data-testid="selected-payment-method">Selected payment method: HDFC credit card ending 1234</div>
<button>Pay ₹5,350</button>'''


@pytest_asyncio.fixture
async def page():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        page=await browser.new_page()
        await page.route('**/*',lambda route:route.fulfill(status=200,content_type='text/html; charset=utf-8',body=HTML))
        await page.goto('https://www.easemytrip.com/fixture?private_booking=secret')
        await page.add_script_tag(content=SCRIPT)
        yield page
        await browser.close()


def test_manifest_has_no_persistent_site_or_external_access():
    manifest=json.loads((ROOT/'browser-companion'/'manifest.json').read_text(encoding='utf-8'))
    assert set(manifest['permissions'])=={'activeTab','scripting'}
    assert not any(key in manifest for key in ('host_permissions','content_scripts','background','externally_connectable'))
    assert "connect-src 'none'" in manifest['content_security_policy']['extension_pages']


@pytest.mark.asyncio
async def test_companion_returns_only_canonical_nonpersonal_evidence(page):
    result=await page.evaluate('(trip)=>captureCheckout(trip)',TRIP)
    assert result['status']=='merchant_snapshot' and result['criteria_match'],result['reasons']
    assert result['merchant_total']==5350 and result['currency']=='INR'
    assert result['selected_payment']==dict(method='CREDIT',banks=['HDFC'])
    assert result['fees']==[dict(label='convenience fee',amount=350)]
    assert not result['usable_as_final_price'] and not result['eligible_for_learning']
    text=json.dumps(result)
    assert all(secret not in text for secret in ('PRIVATE','private@','1234','private_booking','secret'))


@pytest.mark.asyncio
@pytest.mark.parametrize('change',[{'origin':'BOM','destination':'DEL'},{'departure_date':'2027-11-25'},
    {'flight_number':'6E-456'},{'departure_time':'09:30'},{'passenger_count':2},{'cabin_class':'BUSINESS'}])
async def test_companion_scope_mismatch_stays_unverified(page,change):
    result=await page.evaluate('(trip)=>captureCheckout(trip)',{**TRIP,**change})
    assert result['status']=='unverified' and not result['criteria_match'] and result['reasons']


@pytest.mark.asyncio
async def test_companion_wrong_origin_refuses_inspection(page):
    await page.goto('https://www.cleartrip.com.evil.test/fixture')
    await page.add_script_tag(content=SCRIPT)
    result=await page.evaluate('(trip)=>captureCheckout(trip)',TRIP)
    assert result['provider'] is None and result['source_origin'] is None and result['merchant_total'] is None


@pytest.mark.asyncio
async def test_companion_gateway_and_disagreeing_payment_total_are_unverified(page):
    await page.set_content(HTML.replace('Pay ₹5,350','Pay ₹5,450')+'<iframe src="about:blank"></iframe>')
    result=await page.evaluate('(trip)=>captureCheckout(trip)',TRIP)
    assert result['status']=='unverified'
    assert 'Visible payment control amount does not confirm the summary total' in result['reasons']
    assert 'Embedded gateway content has not been inspected' in result['reasons']


@pytest.mark.asyncio
async def test_companion_rejects_duplicate_summaries_hidden_and_conflicting_totals(page):
    await page.set_content(HTML+'<section class="booking-summary"><div>Total payable ₹1</div></section>')
    assert (await page.evaluate('(trip)=>captureCheckout(trip)',TRIP))['merchant_total'] is None
    await page.set_content(HTML.replace('</section>','<div>Grand total ₹1</div><div style="display:none">Total payable ₹1</div></section>'))
    result=await page.evaluate('(trip)=>captureCheckout(trip)',TRIP)
    assert result['status']=='unverified' and result['merchant_total'] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('money',['USD 65','₹5,00','₹5000.999','₹-500'])
async def test_companion_rejects_malformed_or_foreign_total(page,money):
    await page.set_content(HTML.replace('Total payable ₹5,350','Total payable '+money))
    result=await page.evaluate('(trip)=>captureCheckout(trip)',TRIP)
    assert result['status']=='unverified' and result['merchant_total'] is None


@pytest.mark.asyncio
async def test_companion_does_not_accept_review_without_selected_payment_control(page):
    await page.set_content(HTML.replace('<button>Pay ₹5,350</button>','').replace('data-testid="selected-payment-method"','data-testid="payment-options"'))
    result=await page.evaluate('(trip)=>captureCheckout(trip)',TRIP)
    assert result['status']=='unverified' and result['selected_payment'] is None


@pytest.mark.asyncio
async def test_companion_never_clicks_or_modifies_provider(page):
    await page.evaluate("()=>{window.clicked=0; document.querySelector('button').onclick=()=>window.clicked++;}")
    before=await page.content()
    await page.evaluate('(trip)=>captureCheckout(trip)',TRIP)
    assert await page.content()==before and await page.evaluate('window.clicked')==0

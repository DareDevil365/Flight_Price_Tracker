"""Adversarial DOM fixtures; never flight/coupon seed data."""
import pytest
from page_inspection import inspect_page, coupon_control
from tests.test_verified_pricing import page
from workers.cleartrip_worker import CleartripWorker


@pytest.mark.asyncio
async def test_labelled_coupon_field_without_provider_selector(page):
    await page.set_content('''<section><label for="random">Promotion code</label>
        <input id="random"><button aria-label="Apply promo code">Use discount</button></section>
        <input placeholder="Card number" value="private-card"><button id="pay">Pay now</button>
        <script>document.querySelector('button').onclick=()=>document.body.dataset.applied='yes';
        document.querySelector('#pay').onclick=()=>document.body.dataset.paid='yes';</script>''')
    await CleartripWorker().enter_coupon_code(page,'SAVE20')
    await CleartripWorker().click_apply_coupon(page)
    assert await page.input_value('#random')=='SAVE20'
    assert await page.evaluate('document.body.dataset.applied')=='yes'
    assert await page.evaluate('document.body.dataset.paid') is None
    async with inspect_page(page) as capture:
        assert capture.summary['coupon_fields']==1
        assert 'private-card' not in str(capture.summary)
    assert capture.summary=={} and capture.screenshots==[]


@pytest.mark.asyncio
@pytest.mark.parametrize('markup',[
    '<section><input placeholder="Coupon"><button>Apply</button><button>Apply code</button></section>',
    '<section><input placeholder="Coupon"><input placeholder="Promo"><button>Apply</button></section>',
    '<input placeholder="Coupon"><button>Pay and apply coupon</button>',
    '<section><input placeholder="Coupon"><button>Submit</button></section>',
])
async def test_ambiguous_or_payment_control_never_clicked(page,markup):
    await page.set_content(markup+'''<script>document.querySelectorAll('button').forEach(b=>b.onclick=()=>document.body.dataset.clicked='yes');</script>''')
    with pytest.raises(ValueError,match='missing or ambiguous'):
        await coupon_control(page,'apply')
    assert await page.evaluate('document.body.dataset.clicked') is None


@pytest.mark.asyncio
async def test_hidden_and_disabled_fields_do_not_win(page):
    await page.set_content('''<section style="visibility:hidden"><input placeholder="Coupon"><button>Apply</button></section>
        <input aria-label="Coupon" disabled><input aria-label="Coupon" readonly>
        <section><input aria-label="Promo code"><button>Apply</button></section>''')
    await coupon_control(page,'fill',code='SAVE')
    assert await page.input_value('input[aria-label="Promo code"]')=='SAVE'


@pytest.mark.asyncio
async def test_actual_emt_css_rupee_icon_is_inspectable(page):
    await page.set_content('''<div class="pr">Grand Total
        <i class="CurrncyCD_Rs" style="display:inline-block;width:8px;height:10px"></i>
        <span id="spnGrndTotal">8,395</span></div>''')
    async with inspect_page(page,screenshots=True) as capture:
        assert capture.summary['totals']==[8395]
        assert len(capture.screenshots)==1
    await page.locator('i').evaluate('(el)=>el.style.visibility="hidden"')
    async with inspect_page(page) as capture:
        assert capture.summary['totals']==[]


@pytest.mark.asyncio
async def test_visible_money_spans_and_memory_cleanup_on_exception(page):
    await page.set_content('''<aside><div>Grand total <span>₹</span><span>6,240.50</span></div>
        <div>Convenience fee <span>₹240.50</span></div></aside>
        <div style="visibility:hidden">Amount payable ₹1</div>
        <script>const privateToken='secret';</script><input value="private@example.com">''')
    with pytest.raises(RuntimeError):
        async with inspect_page(page,screenshots=True) as capture:
            assert capture.summary['totals']==[6240.5]
            assert capture.summary['fees'][0]['amount']==240.5
            assert capture.screenshots and capture.screenshots[0][:4]==b'\x89PNG'
            retained_image=capture.screenshots[0]
            assert not capture.summary['final_verified']
            assert 'secret' not in str(capture.summary)
            raise RuntimeError('cancel work')
    assert capture.summary=={} and capture.screenshots==[] and not retained_image


@pytest.mark.asyncio
@pytest.mark.parametrize('text',[
    'Grand total USD 85', 'Grand total ₹1e4', 'Grand total ₹2,00',
    'Grand total ₹5,000 per adult','Grand total ₹5,000 + ₹300',
    'Lock price ₹300','Save ₹900','Grand total ₹6000 for private@example.com',
])
async def test_no_invented_amount_or_private_row(page,text):
    await page.set_content('<div>'+text+'</div>')
    async with inspect_page(page,screenshots=True) as capture:
        assert capture.summary['totals']==[] and capture.screenshots==[]
    assert await CleartripWorker().read_checkout_total(page) is None


@pytest.mark.asyncio
async def test_conflicting_totals_and_dynamic_nodes_fail_closed(page):
    await page.set_content('<div>Grand total ₹6000</div><div>Amount payable ₹6300</div>')
    assert await CleartripWorker().read_checkout_total(page) is None
    await page.set_content('<section><input placeholder="Coupon"><button>Apply</button></section>')
    await coupon_control(page,'fill',code='SAVE')
    await page.locator('section').evaluate('(el)=>el.remove()')
    with pytest.raises(ValueError):
        await coupon_control(page,'apply')


@pytest.mark.asyncio
async def test_inspection_budget_never_certifies_partial_totals(page):
    await page.set_content('<div>Grand total ₹6000</div>'*41+'<div>Amount payable ₹9999</div>')
    async with inspect_page(page,screenshots=True) as capture:
        assert capture.summary['truncated'] and not capture.screenshots
    assert await CleartripWorker().read_checkout_total(page) is None

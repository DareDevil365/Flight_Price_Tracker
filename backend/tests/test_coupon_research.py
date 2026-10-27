"""Coupon optimizer invariants; all carts and sources below are local fixtures."""
from types import SimpleNamespace

import pytest

from coupon_brute_forcer import CouponBruteForcer
from financial_filter import FinancialFilter
from coupon_harvester import CouponHarvester
from offer_parser import published_offer
from tests.test_navigation_audit import StatefulCart, fast_coupon_waits
from tests.test_verified_pricing import database


@pytest.mark.asyncio
async def test_original_unconfirmed_coupon_is_preserved_when_candidates_cost_more(fast_coupon_waits):
    cart=StatefulCart()
    with pytest.raises(ValueError,match='original payable total'):
        await CouponBruteForcer(cart,FinancialFilter(),lambda *args:None).brute_force(
            SimpleNamespace(url='https://www.cleartrip.com/booking'),
            [{'code':'NOREDUCTION','description':'Flight discount'}],{},'isolated')
    assert cart.applied=='ORIG' and cart.total==5800


@pytest.mark.asyncio
async def test_worse_replacement_cannot_displace_a_cheaper_original_coupon(fast_coupon_waits):
    cart=StatefulCart()
    original_apply=cart.click_apply_coupon
    async def apply(page):
        await original_apply(page)
        if cart.applied=='WORSE':cart.total=5900
    cart.click_apply_coupon=apply
    with pytest.raises(ValueError,match='original payable total'):
        await CouponBruteForcer(cart,FinancialFilter(),lambda *args:None).brute_force(
            SimpleNamespace(url='https://www.cleartrip.com/booking'),
            [{'code':'WORSE','description':'Flight discount'}],{},'isolated')
    assert cart.applied=='ORIG' and cart.total==5800


@pytest.mark.asyncio
async def test_better_eligible_replacement_is_still_selected(fast_coupon_waits):
    cart=StatefulCart()
    result=await CouponBruteForcer(cart,FinancialFilter(),lambda *args:None).brute_force(
        SimpleNamespace(url='https://www.cleartrip.com/booking'),
        [{'code':'BEST','description':'Flight discount'}],{},'isolated')
    assert result['best_price']==5000 and cart.applied=='BEST'


def test_merchant_feed_keeps_explicit_codes_expiry_and_incomplete_terms():
    source='https://www.easemytrip.com/offers/offerjson/deals/flightoffers.json'
    rows=CouponHarvester.parse_emt_feed([
        {'promoCode':'FLYNOW','title':'Flight Offer','description':'Get 7% off on domestic flights',
         'validity':'Till 31st Oct, 2026','url':'https://www.easemytrip.com/offers/domestic-flight-sale.html?CouponCode=FLYNOW'},
        {'promoCode':'','title':'Flight fares from INR 1000','description':'No explicit code'},
        {'promoCode':'HOTEL20','title':'Hotel Offer','description':'20% off hotel stays'},
    ],source)
    assert len(rows)==1 and rows[0]['code']=='FLYNOW' and rows[0]['valid_until']=='2026-10-31'
    assert rows[0]['source_url']==source
    assert rows[0]['terms_url']=='https://www.easemytrip.com/offers/domestic-flight-sale.html'
    assert rows[0]['eligibility_unconfirmed'] and rows[0]['evidence_kind']=='public_http'
    assert FinancialFilter().assess(rows[0],{'selected_payment':{'method':'UPI'}}).status=='unknown'


def test_merchant_feed_does_not_follow_untrusted_or_malformed_detail_links():
    for link in ['https://evil.test/offers/x','https://www.easemytrip.com:bad/offers/x','https://user:secret@www.easemytrip.com/offers/x']:
        row=CouponHarvester.parse_emt_feed([{'promoCode':'CODE10','description':'Flight discount','url':link}],
            'https://www.easemytrip.com/offers/offerjson/deals/flightoffers.json')[0]
        assert 'terms_url' not in row


@pytest.mark.asyncio
async def test_primary_discovery_survives_aggregator_failure_without_hiding_it(monkeypatch):
    harvester=CouponHarvester(None)
    async def merchant(category,session):
        return [{'code':'SAME','description':'Merchant terms','eligibility_unconfirmed':True}]
    async def unavailable(platform,session):raise ValueError('HTTP 403')
    monkeypatch.setattr(harvester,'_crawl_emt',merchant)
    monkeypatch.setattr(harvester,'_crawl_grabon',unavailable)
    rows=await harvester._crawl_platform_deals('easemytrip',object())
    assert len(rows)==1 and rows[0]['description']=='Merchant terms'
    assert harvester.source_status['easemytrip']['GrabOn'].startswith('Unavailable:')


@pytest.mark.asyncio
async def test_public_merchant_terms_precede_duplicate_aggregator_advertisement(monkeypatch):
    harvester=CouponHarvester(None)
    async def merchant(category,session):return [{'code':'SAME','description':'Merchant restrictions'}]
    async def aggregator(platform,session):return [{'code':'SAME','description':'No restrictions advertised'}]
    monkeypatch.setattr(harvester,'_crawl_emt',merchant)
    monkeypatch.setattr(harvester,'_crawl_grabon',aggregator)
    rows=await harvester._crawl_platform_deals('easemytrip',object())
    assert rows==[{'code':'SAME','description':'Merchant restrictions'}]


def test_observed_cleartrip_optional_cashback_does_not_restrict_flat_discount():
    # Real native review card seen on 2026-10-09; this is a parser fixture, not
    # a stored live coupon or a promise about a future traveller's eligibility.
    terms='CTBBD\nApply\nFlat ₹441 off\nAdditional 5% cashback with Flipkart Axis Credit Card Know more'
    offer=published_offer('cleartrip','CTBBD',terms,'https://www.cleartrip.com/flights',native=True)
    assert offer['description']==terms
    assert offer['discount_type']=='FLAT' and offer['discount_value']==441
    assert offer['bank_restriction'] is None and offer['card_type']=='ANY'
    assert FinancialFilter().assess(offer,{'is_domestic':True,'selected_payment':{'method':'UPI'}}).status=='eligible'


@pytest.mark.parametrize('terms',[
    'Additional 5% cashback with Flipkart Axis Credit Card',
    'Avail 5% additional cashback with Flipkart Axis Bank credit card',
    '5% cashback only with Flipkart Axis Credit Card',
])
def test_cashback_only_offer_keeps_required_card(terms):
    offer=published_offer('cleartrip','CARDSAVE',terms,'https://www.cleartrip.com/flights',native=True)
    assert offer['bank_restriction']=='AXIS'
    assert FinancialFilter().assess(offer,{'selected_payment':{'method':'UPI'}}).status=='ineligible'


@pytest.mark.parametrize('restriction',[
    'Only valid with HDFC credit cards',
    'Not valid on UPI',
])
def test_removing_optional_cashback_preserves_independent_required_or_excluded_methods(restriction):
    terms='Flat ₹441 off. Additional 5% cashback with Flipkart Axis Credit Card. '+restriction
    offer=published_offer('cleartrip','CTBBD',terms,'https://www.cleartrip.com/flights',native=True)
    assert FinancialFilter().assess(offer,{'selected_payment':{'method':'UPI'}}).status=='ineligible'


@pytest.mark.parametrize('terms',[
    'Domestic flights only. International flights only.',
    'Only on domestic flights. Only on international flights.',
])
def test_conflicting_exclusive_route_terms_remain_unknown(terms):
    offer=published_offer('cleartrip','CTBBD',terms,'https://www.cleartrip.com/all-offers/domestic-sale',native=True)
    assert FinancialFilter().assess(offer,{'is_domestic':True}).status=='unknown'


def test_route_scope_is_read_from_terms_not_the_offer_url_slug():
    offer=published_offer('cleartrip','CTBBD','Flat ₹441 off domestic and international flights. All payment modes.',
        'https://www.cleartrip.com/all-offers/ct-bbd-special-offer-international/',native=True)
    assert FinancialFilter().assess(offer,{'is_domestic':True,'selected_payment':{'method':'UPI'}}).status=='eligible'


@pytest.mark.asyncio
async def test_explicit_first_refresh_initializes_cache_history(database,monkeypatch):
    harvester=CouponHarvester(database)
    async def collect(platform,session):
        from offer_parser import published_offer
        return [published_offer(platform,'REFRESH10','Flight discount',
            'https://www.easemytrip.com/offers/example.html',native=True)]
    monkeypatch.setattr(harvester,'_crawl_platform_deals',collect)
    rows=await harvester.deep_harvest(['easemytrip'])
    assert len(rows)==1
    assert not await harvester.should_harvest('easemytrip')
    assert 'discovered' in harvester.last_status['easemytrip']

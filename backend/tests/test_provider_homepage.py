"""Local airport-menu regressions; none of these are live fare evidence."""
from urllib.parse import urlencode, urlsplit, parse_qs

import pytest

from provider_homepage import _assert_search_url, _select_airport, dismiss_makemytrip_login
from quotes import search_url
from provider_status import ProviderError
from tests.test_verified_pricing import page

TRIP=dict(origin='AMD',destination='IXC',departure_date='2026-11-17',
          passenger_count=1,cabin_class='ECONOMY',is_domestic=True)


def airport_menu(options,selected='AMD'):
    return '''<label>From Ahmedabad<input id="fromCity" value="Ahmedabad">
        <p>'''+selected+''', Airport India</p></label>
        <input aria-label="From"><div role="listbox"><div role="listbox">'''+options+'''</div></div>'''


@pytest.mark.asyncio
async def test_nested_listboxes_and_nearby_airports_choose_exact_iata_option(page):
    # The old nested listbox/text query could find AMD twice. The primary option
    # also contains nearby codes: those must never become an airport selection.
    await page.set_content(airport_menu('''
        <div role="option" aria-label="AMD Ahmedabad, India">
            <span>AMD</span><div>Nearby airports: BDQ HSR</div></div>
        <div role="option" aria-label="BDQ Vadodara, India">BDQ</div>'''))
    await _select_airport(page,'From','AMD')


@pytest.mark.asyncio
async def test_duplicate_exact_airports_fail_before_click(page):
    await page.set_content(airport_menu('''
        <div role="option" aria-label="AMD Ahmedabad, India">AMD</div>
        <div role="option" aria-label="AMD Ahmedabad duplicate">AMD</div>'''))
    with pytest.raises(ValueError,match='ambiguous'):
        await _select_airport(page,'From','AMD')


@pytest.mark.asyncio
async def test_city_match_without_confirmed_iata_is_rejected(page):
    await page.set_content(airport_menu('''
        <div role="option" aria-label="AMD Ahmedabad, India">AMD</div>''',selected='BDQ'))
    with pytest.raises(ValueError,match='Selected airport'):
        await _select_airport(page,'From','AMD')


def test_exact_public_form_redirect_is_scoped_but_not_a_fare():
    assert _assert_search_url(search_url('makemytrip',TRIP),TRIP) is None


@pytest.mark.parametrize('key,value',[
    ('itinerary','IXC-AMD-17/11/2026'),('itinerary','AMD-IXC-18/11/2026'),
    ('paxType','A-2_C-0_I-0'),('paxType','A-0_C-1_I-0'),
    ('cabinClass','B'),('tripType','R'),('intl','true'),
])
def test_redirect_with_different_booking_scope_is_rejected(key,value):
    parsed=urlsplit(search_url('makemytrip',TRIP))
    query=parse_qs(parsed.query)
    query[key]=[value]
    with pytest.raises(ValueError,match='criteria'):
        _assert_search_url('https://www.makemytrip.com/flight/search?'+urlencode(query,doseq=True),TRIP)


@pytest.mark.parametrize('url',[
    'https://www.makemytrip.com.evil.example/flight/search',
    'http://www.makemytrip.com/flight/search',
    'https://www.makemytrip.com/',
])
def test_wrong_origin_or_route_is_rejected(url):
    with pytest.raises(ValueError,match='public flight search'):
        _assert_search_url(url,TRIP)


def test_duplicate_conflicting_criteria_are_not_accepted():
    with pytest.raises(ValueError,match='criteria'):
        _assert_search_url(search_url('makemytrip',TRIP)+'&cabinClass=B',TRIP)


async def mmt_local(page,html):
    await page.route('https://www.makemytrip.com/local-login-fixture',
        lambda route:route.fulfill(status=200,body=html,content_type='text/html'))
    await page.goto('https://www.makemytrip.com/local-login-fixture')


LOGIN='''<div class="loginModal" role="dialog"><h2>Login or create account</h2>
    <input placeholder="Enter Mobile number">
    <span class="commonModal__close" onclick="this.parentElement.remove()">X</span></div>'''


@pytest.mark.asyncio
async def test_verified_optional_login_is_closed_before_using_underlying_form(page):
    await mmt_local(page,LOGIN+'<button>Search</button>')
    result=await dismiss_makemytrip_login(page,wait_ms=0)
    assert result=={'status':'dismissed','dismissed':True}
    assert await page.get_by_role('dialog').count()==0
    assert await page.get_by_role('button',name='Search').is_visible()


@pytest.mark.asyncio
async def test_delayed_login_dialog_is_detected(page):
    await mmt_local(page,'<div id="late" hidden>'+LOGIN+'</div>')
    await page.evaluate("setTimeout(()=>document.querySelector('#late').hidden=false,150)")
    assert (await dismiss_makemytrip_login(page,wait_ms=600))['dismissed']


@pytest.mark.asyncio
async def test_hidden_old_close_button_does_not_mask_the_visible_login_control(page):
    await mmt_local(page,'<span hidden class="commonModal__close">Old X</span>'+LOGIN)
    assert (await dismiss_makemytrip_login(page,wait_ms=0))['dismissed']


@pytest.mark.asyncio
async def test_unrelated_cookie_or_verification_modal_is_never_closed(page):
    await mmt_local(page,'''<div class="commonModal" role="dialog">Verify you are human
        <span data-cy="closeModal" onclick="window.unwantedClick=true">X</span></div>''')
    assert (await dismiss_makemytrip_login(page,wait_ms=0))['status']=='absent'
    assert await page.evaluate('window.unwantedClick===undefined')
    assert await page.get_by_role('dialog').is_visible()


@pytest.mark.asyncio
async def test_multiple_login_close_controls_fail_without_guessing(page):
    await mmt_local(page,LOGIN+LOGIN)
    with pytest.raises(ProviderError,match='ambiguous') as error:
        await dismiss_makemytrip_login(page,wait_ms=0)
    assert error.value.code=='LOGIN_BLOCKED'
    assert await page.get_by_role('dialog').count()==2


@pytest.mark.asyncio
async def test_login_dialog_without_known_close_control_is_reported(page):
    await mmt_local(page,LOGIN.replace('class="commonModal__close"','class="unknown-X"'))
    with pytest.raises(ProviderError,match='no verified close') as error:
        await dismiss_makemytrip_login(page,wait_ms=0)
    assert error.value.code=='LOGIN_BLOCKED'


@pytest.mark.asyncio
async def test_dismissing_control_without_dismissing_dialog_is_not_success(page):
    await mmt_local(page,LOGIN.replace('this.parentElement.remove()','this.remove()'))
    with pytest.raises(ProviderError,match='remained visible') as error:
        await dismiss_makemytrip_login(page,wait_ms=0)
    assert error.value.code=='LOGIN_BLOCKED'


@pytest.mark.asyncio
async def test_ignored_close_click_is_blocked_instead_of_false_success(page):
    await mmt_local(page,LOGIN.replace('this.parentElement.remove()','window.clicked=true'))
    with pytest.raises(ProviderError,match='did not dismiss') as error:
        await dismiss_makemytrip_login(page,wait_ms=0)
    assert error.value.code=='LOGIN_BLOCKED'
    assert await page.evaluate('window.clicked===true')
    assert await page.get_by_role('dialog').is_visible()


@pytest.mark.asyncio
async def test_other_origin_cannot_use_mmt_specific_dismissal(page):
    await page.set_content(LOGIN)
    with pytest.raises(ValueError,match='exact public'):
        await dismiss_makemytrip_login(page,wait_ms=0)
    assert await page.get_by_role('dialog').is_visible()


@pytest.mark.asyncio
@pytest.mark.parametrize('challenge',[
    '<p>Verify you are human before continuing</p>',
    '<p>Please complete the security check</p>',
    '<input aria-label="Captcha" placeholder="Enter CAPTCHA">',
    '<iframe title="Security check" src="https://challenge.example/turnstile"></iframe>',
])
async def test_mixed_login_and_human_verification_does_not_click_close(page,challenge):
    html=LOGIN.replace('</h2>','</h2>'+challenge).replace('this.parentElement.remove()','window.clicked=true')
    await mmt_local(page,html)
    with pytest.raises(ProviderError,match='human-verification') as error:
        await dismiss_makemytrip_login(page,wait_ms=0)
    assert error.value.code=='ACCESS_DENIED'
    assert await page.evaluate('window.clicked===undefined')
    assert await page.get_by_role('dialog').is_visible()


@pytest.mark.asyncio
async def test_hidden_inactive_challenge_does_not_prevent_optional_login_dismissal(page):
    await mmt_local(page,LOGIN.replace('</h2>','</h2><input hidden aria-label="Captcha">'))
    assert (await dismiss_makemytrip_login(page,wait_ms=0))['dismissed']

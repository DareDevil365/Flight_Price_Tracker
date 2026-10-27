"""Candidate public homepage navigation; enable only after live worker validation."""
import re
import asyncio
from time import monotonic
from datetime import date
from urllib.parse import parse_qs, urlsplit


_LOGIN_CLOSE='.commonModal__close, [data-cy="closeModal"]'
_LOGIN_STATE='''(controls) => {
    const challenge = e => {
        const text = (e.innerText || '').slice(0,5000);
        return /verify (?:you are|that you)|human verification|unusual traffic|complete (?:the )?(?:captcha|security check)|not a robot/i.test(text)
            || Array.from(e.querySelectorAll('iframe,input,[data-sitekey],[id*="captcha" i],[class*="captcha" i]')).some(child =>
                child.checkVisibility() && /captcha|recaptcha|hcaptcha|turnstile/i.test([
                    child.id,child.className,child.getAttribute('src'),child.getAttribute('name'),
                    child.getAttribute('placeholder'),child.getAttribute('aria-label')].join(' ')));
    };
    const login = e => {
        if (!e || !e.checkVisibility() || ['BODY','HTML'].includes(e.tagName)) return false;
        const identity = e.getAttribute('role') === 'dialog' || /modal|dialog|login/i.test(e.className || '');
        const text = (e.innerText || '').slice(0,5000);
        const words = /log\\s*in|sign\\s*(?:in|up)|login or create|create (?:an? )?account/i.test(text);
        const field = Array.from(e.querySelectorAll('input')).some(i => i.checkVisibility() &&
            /mobile|phone|email/i.test([i.type,i.placeholder,i.getAttribute('aria-label')].join(' ')));
        return identity && words && field;
    };
    const indices = [];
    let blockedChallenge = false;
    controls.forEach((e,index) => {
        if (!e.checkVisibility()) return;
        for (let parent=e.parentElement,depth=0; parent && depth<5; parent=parent.parentElement,depth++) {
            if (login(parent)) {
                if (challenge(parent)) blockedChallenge = true;
                else indices.push(index);
                break;
            }
        }
    });
    const dialogs = Array.from(document.querySelectorAll('.loginModal,.modalMain,.commonModal,[role="dialog"]')).filter(login);
    const visibleLogin = dialogs.length>0;
    blockedChallenge ||= dialogs.some(challenge);
    return {indices, visibleLogin, blockedChallenge};
}'''


async def dismiss_makemytrip_login(page, wait_ms=2500):
    """Close only an identified optional login dialog, then prove it disappeared.

    Delayed hydration is bounded. No Escape, force-click, unknown modal click,
    login fields, or challenge interaction is used. The result contains facts,
    not page text; callers must separately verify search criteria and listings.
    """
    from provider_status import ProviderError
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    parsed=urlsplit(page.url)
    if parsed.scheme!='https' or parsed.hostname!='www.makemytrip.com':
        raise ValueError('Login dismissal requires the exact public MakeMyTrip origin')
    deadline=monotonic()+max(0,min(wait_ms,5000))/1000
    controls=page.locator(_LOGIN_CLOSE)
    seen=False
    while True:
        state=await controls.evaluate_all(_LOGIN_STATE)
        if state['blockedChallenge']:
            raise ProviderError('ACCESS_DENIED','MakeMyTrip displays a human-verification challenge in its login dialog. Manual provider access is needed.')
        seen=seen or state['visibleLogin'] or bool(state['indices'])
        if len(state['indices'])>1:
            raise ProviderError('LOGIN_BLOCKED','MakeMyTrip login close control is ambiguous')
        if state['indices']:
            close=controls.nth(state['indices'][0])
            try:
                await close.click(timeout=3000)
                await close.wait_for(state='hidden',timeout=3000)
            except PlaywrightTimeoutError as exc:
                raise ProviderError('LOGIN_BLOCKED','MakeMyTrip login dialog did not dismiss after its close control was clicked') from exc
            remaining=await controls.evaluate_all(_LOGIN_STATE)
            if remaining['visibleLogin'] or remaining['indices']:
                raise ProviderError('LOGIN_BLOCKED','MakeMyTrip login dialog remained visible after dismissal')
            return {'status':'dismissed','dismissed':True}
        if monotonic()>=deadline:
            if seen:
                raise ProviderError('LOGIN_BLOCKED','MakeMyTrip login dialog has no verified close control')
            return {'status':'absent','dismissed':False}
        await asyncio.sleep(min(.15,max(0,deadline-monotonic())))


async def _select_airport(page, name, code):
    """Choose an exact airport option, never a city/nearby-airport descendant."""
    await page.get_by_role('textbox',name=re.compile('^'+name+' ')).click(timeout=4000)
    await page.get_by_role('textbox',name=name,exact=True).fill(code,timeout=4000)
    option=page.get_by_role('option',name=re.compile('^'+re.escape(code)+r'\s'))
    await option.first.wait_for(state='visible',timeout=8000)
    if await option.count()!=1:
        raise ValueError('Airport choice ambiguous; no search submitted')
    await option.click(timeout=4000)
    field=page.locator('#fromCity' if name=='From' else '#toCity')
    # The visible parent label contains the selected IATA code. Input.value is
    # only a city name and cannot distinguish nearby airports in the same city.
    selected=await field.locator('..').inner_text(timeout=4000)
    if not re.search(r'(?m)^\s*'+re.escape(code)+r'\s*,',selected):
        raise ValueError('Selected airport could not be verified; no search submitted')


def _assert_search_url(url, trip):
    """A form redirect is not proof of a fare; first require exact search scope."""
    from quotes import search_url
    actual=urlsplit(url)
    expected=urlsplit(search_url('makemytrip',trip))
    if actual.scheme!='https' or actual.hostname!='www.makemytrip.com' or actual.path!='/flight/search':
        raise ValueError('Homepage search did not reach the public flight search')
    query=parse_qs(actual.query,keep_blank_values=True)
    for key,value in parse_qs(expected.query).items():
        if query.get(key)!=value:
            raise ValueError('Homepage search criteria could not be verified: '+key)


async def makemytrip_home_search(page,trip):
    if trip['passenger_count']!=1 or trip['cabin_class']!='ECONOMY':
        raise ValueError('Homepage recovery has only been validated for one adult in economy')
    await page.goto('https://www.makemytrip.com/',wait_until='domcontentloaded',timeout=35000)
    await dismiss_makemytrip_login(page)
    origin=page.get_by_role('textbox',name=re.compile(r'^From '))
    await origin.wait_for(state='visible',timeout=20000)
    for name,code in [('From',trip['origin']),('To',trip['destination'])]:
        await _select_airport(page,name,code)
    target=date.fromisoformat(trip['departure_date'])
    cell=page.get_by_role('gridcell',name=target.strftime('%a %b %d %Y'),exact=True)
    # Selecting the destination can already open the calendar. The departure
    # input's value is stale on the live site; select the actual dated gridcell.
    if not (await page.get_by_role('gridcell').count()):
        await page.get_by_text('Departure',exact=True).click(timeout=4000)
    for _ in range(13):
        if await cell.count()==1 and await cell.is_visible():
            await cell.click(timeout=4000)
            break
        await page.get_by_role('button',name='Next Month',exact=True).click(timeout=4000)
    else:
        raise ValueError('Requested date not available in the public calendar')
    await page.get_by_text('Search',exact=True).click(timeout=8000)
    await page.wait_for_url('https://www.makemytrip.com/flight/search?**',timeout=20000)
    _assert_search_url(page.url,trip)

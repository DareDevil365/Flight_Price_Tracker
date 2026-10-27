"""Published offer candidates. Only checkout trials establish actual savings."""
import re
from datetime import datetime

CODE = re.compile(r'[A-Z0-9_-]{2,40}')
NON_CODES = {'APPLY', 'REMOVE', 'COUPON', 'PROMO', 'CODE', 'GET', 'SAVE', 'OFFER', 'FLIGHTS', 'SHOW'}
BANKS = ('HDFC', 'ICICI', 'SBI', 'AXIS', 'HSBC', 'KOTAK', 'CITI', 'YES', 'BOB', 'FEDERAL', 'INDUSIND', 'IDBI', 'PNB', 'DBS', 'JNK', 'IDFC', 'AU', 'RBL','CANARA','STANDARD CHARTERED','UNION','IOB')


def payment_terms(text):
    """An optional extra cashback benefit must not restrict the base coupon."""
    pattern=(r'\b(?:Avail\s+)?(?:Additional\s+[\d.]+%\s+cashback|[\d.]+%\s+additional\s+cashback)'
        r'\s+with\s+[^.\n;|]{1,150}?\bcards?\b'
        r'|\bFlipkart\s+Axis\s+Bank\s+[\d.]+%\s+Additional\s+Cashback\b')
    primary=re.sub(pattern,'',text,flags=re.I)
    # "Additional" alone does not prove a separate universal discount. Keep
    # card restrictions for cashback-only offers and preserve raw source terms.
    if re.search(r'(?:[\d.]+%|(?:₹|INR|Rs\.?)\s*[\d,]+)\s*(?:instant\s+)?(?:off|discount)\b',primary,re.I):
        return primary
    return text


def card_product(text):
    patterns=[(r'amazon\s+icici|icici\s+amazon','AMAZON ICICI',('AMAZON','ICICI')),
        (r'flipkart\s+axis','FLIPKART AXIS',('FLIPKART','AXIS')),(r'flipkart\s+sbi','FLIPKART SBI',('FLIPKART','SBI')),
        (r'hsbc\s+travel\s*one','HSBC TRAVEL ONE',('HSBC','TRAVELONE')),
        (r'digibank\s+easemytrip\s+green','DIGIBANK EASEMYTRIP GREEN',('DIGIBANK','EASEMYTRIP','GREEN')),
        (r'bank of baroda\s+easemytrip|bob\s+easemytrip','BOB EASEMYTRIP',('EASEMYTRIP',)),
        (r'one\s*card','ONECARD',('ONECARD',))]
    for bank,name in [('HDFC','REGALIA'),('HDFC','INFINIA'),('HDFC','DINERS'),('SBI','SIMPLYSAVE'),('SBI','SIMPLYCLICK')]:
        patterns.append((bank+r'\s+'+name.replace('SIMPLY',r'SIMPLY\s*'),bank+' '+name,(bank,name)))
    for pattern,name,tokens in patterns:
        if re.search(r'\b(?:'+pattern+r')\b',text,re.I):
            return name,tokens
    return None


def published_offer(platform, code, description, source_url, native=False):
    code = (code or '').strip().upper()
    if not CODE.fullmatch(code) or code in NON_CODES:
        return None
    # Native cards separate positive and negative restrictions by line. Flattening
    # those lines made "ICICI net banking\nNot valid on credit cards" one negative
    # clause and could erase its actual requirement.
    text = '\n'.join(' '.join(line.split()) for line in (description or '').splitlines() if line.strip())
    payment_text=payment_terms(text)
    percent = re.search(r'(\d+(?:\.\d+)?)\s*%\s*(?:off|discount|cashback)', payment_text, re.I)
    flat = re.search(r'(?:₹|INR|Rs\.?)\s*([\d,]+)\s*(?:instant\s+)?(?:off|discount|cashback)', payment_text, re.I)
    minimum = re.search(r'(?:minimum (?:booking|transaction|fare|spend)(?: value)?|min\.?\s+(?:spend|booking(?: value)?)|above)\s*(?:of|:)?\s*(?:₹|INR|Rs\.?)\s*([\d,]+)', text, re.I)
    expiry = re.search(r'(?:valid (?:until|till)|expires?(?: on)?)\s*:?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}[ /-][A-Za-z]{3,9}[ /-]\d{4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})', text, re.I)
    expires = None
    if expiry:
        for fmt in ('%Y-%m-%d', '%d %b %Y', '%d %B %Y', '%b %d %Y', '%B %d %Y'):
            try:
                expires = datetime.strptime(expiry[1] if fmt == '%Y-%m-%d' else re.sub(r'[/\-,]', ' ', expiry[1]).replace('  ',' '), fmt).date().isoformat()
                break
            except ValueError:
                pass
    starts = re.search(r'(?:valid from|starts?(?: on)?)\s*:?\s*(\d{4}-\d{2}-\d{2})',text,re.I)
    begins = None
    if starts:
        try:
            begins = datetime.strptime(starts[1],'%Y-%m-%d').date().isoformat()
        except ValueError:
            pass
    from offer_rules import payment_constraints,booking_validity
    window_start,window_end,_=booking_validity(text)
    begins=begins or (window_start.isoformat() if window_start else None)
    expires=expires or (window_end.isoformat() if window_end else None)
    constraints=payment_constraints(payment_text)
    banks = constraints['banks']
    if re.search(r'\bdigibank\b',payment_text,re.I) and 'DBS' not in banks:
        banks.append('DBS')
    if re.search('Bank of Baroda',text,re.I) and 'BOB' not in banks:
        banks.append('BOB')
    if re.search('Punjab National Bank',text,re.I) and 'PNB' not in banks:
        banks.append('PNB')
    return dict(platform=platform, code=code, description=text[:2000], source='scraped',
        eligibility_unconfirmed=len(text)>2000,
        evidence_kind='public_browser' if native else 'public_http',
        source_type='platform_native' if native else 'external_crawled', source_url=source_url,
        trust_score=.95 if native else .6, discount_type='PERCENT' if percent else 'FLAT',
        discount_value=float(percent[1]) if percent else float(flat[1].replace(',', '')) if flat else 0,
        min_booking_value=float(minimum[1].replace(',', '')) if minimum else 0,
        bank_restriction='|'.join(banks) or None,
        card_type=constraints['methods'][0] if len(constraints['methods'])==1 else 'ANY',
        requires_emi=bool(re.search(r'(?:\b|EASY)EMI\b',text,re.I) or code.endswith('EMI')),
        requires_bnpl=bool(re.search(r'\b(?:BNPL|buy now pay later|pay later|Simpl|Lazypay)\b',text,re.I)),
        requires_wallet=bool(re.search(r'\bwallet\b',text,re.I)),
        app_only=bool(re.search(r'app[ -]only|only (?:on|in) (?:the )?(?:mobile )?app',text,re.I)),
        valid_from=begins, valid_until=expires, is_active=1)


async def scrape_published_offers(page, platform):
    """Never guess codes from random uppercase words, discount amounts or headings."""
    rows = await page.evaluate(r'''() => {
        const rows=[];
        const visible=el=>{
            if (!el?.getBoundingClientRect().width) return false;
            for (let parent=el;parent;parent=parent.parentElement) {
                const style=getComputedStyle(parent);
                if (style.display==='none' || style.visibility==='hidden' || style.visibility==='collapse' || style.contentVisibility==='hidden' || Number(style.opacity)===0) return false;
            }
            return true;
        };
        const cards=document.querySelectorAll('[class*="coupon" i], [class*="promo" i], .offer-card, .ofer_bx_sld, [data-code]');
        for (const card of cards) {
            if (!visible(card)) continue;
            const text=card.innerText || '';
            if (text.length>3000) continue;
            const element=card.matches('[data-code]') ? card : card.querySelector('[data-code], .couponCode, .promo-code, [class*="coupon-code" i], [class*="couponcode" i], [ng-bind="cp.cpn"]');
            const labeled=text.match(/\b(?:coupon\s+code|promo\s+code|use\s+(?:code\s*)?)\s*[:\-]?\s*([A-Z0-9_-]{2,40})\b/i);
            const code=(visible(element) ? element?.getAttribute('data-code') || element?.innerText?.trim() : null) || labeled?.[1];
            if (code) rows.push({code,description:text});
        }
        // Cleartrip labels native code nodes explicitly as uppercase beside terms.
        for (const element of document.querySelectorAll('[texttransform="uppercase"]')) {
            const card=element.parentElement?.parentElement;
            const description=card?.innerText || '';
            if (visible(element) && description.length<1000 && /\boff\b|discount|cashback/i.test(description)) {
                rows.push({code:element.innerText.trim(),description});
            }
        }
        // EaseMyTrip publishes a flight-specific offer as CODE: ... discount.
        for (const card of document.querySelectorAll('.main-bo-lis [id^="divNote"]')) {
            if (!visible(card)) continue;
            const description=card.innerText || '';
            const code=description.match(/^([A-Z0-9_-]{2,40}):\s*(?:Get|Save)/)?.[1];
            if (code) rows.push({code,description});
        }
        // EMT's booking review lists explicit native coupon radios. Hidden
        // View All Coupons entries are included only after opening that panel.
        for (const input of document.querySelectorAll('input[id^="rdoCpn"]')) {
            const card=input.closest('label');
            if (!visible(card)) continue;
            const code=card.querySelector('[ng-bind="copnLst.CouponCode"]')?.innerText?.trim();
            if (code) rows.push({code,description:'Flight booking offer: '+card.innerText});
        }
        return rows;
    }''')
    found = {}
    for row in rows:
        offer = published_offer(platform,row['code'],row['description'],page.url,native=True)
        if offer and (offer['code'] not in found or len(offer['description'])>len(found[offer['code']]['description'])):
            found[offer['code']]=offer
    return list(found.values())

"""Short-lived, local inspection of rendered checkout DOM. No page files or AI.

The browser already holds the rendered page. Read its labels and structure rather
than downloading/replaying source HTML, which omits client-rendered controls.
Only coupon controls and strict monetary rows leave the page; input values,
scripts, cookies and unrelated text do not. Never execute instructions in text.
"""
from contextlib import asynccontextmanager
from dataclasses import dataclass, field


DOM_HELPERS = r'''
const visible = el => {
    if (!el || !el.isConnected || el.closest('[hidden],[inert],[aria-hidden="true"]')) return false;
    for (let p=el;p;p=p.parentElement) {
        const s=getComputedStyle(p);
        if (s.display==='none' || s.visibility!=='visible' || Number(s.opacity)===0) return false;
    }
    const r=el.getBoundingClientRect();
    return r.width>0 && r.height>0;
};
const clean = s => (s || '').replace(/\s+/g,' ').trim();
const label = el => clean([
    el.getAttribute('aria-label'), el.placeholder,
    ...[...(el.labels || [])].map(l=>l.innerText),
    ...(el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean)
        .map(id=>document.getElementById(id)?.innerText), el.id, el.name
].join(' '));
const couponFields = () => [...document.querySelectorAll('input:not([type]),input[type=text],input[type=search],textarea')]
    .filter(el=>visible(el) && !el.disabled && !el.readOnly
        && /coupon|promo(?:tion)?(?:\s*code)?/i.test(label(el))
        && !/password|cvv|cvc|card\s*(?:number|holder)|email|phone|mobile|passport|otp/i.test(label(el)));
const buttons = root => [...root.querySelectorAll('button,a,[role=button],input[type=button],input[type=submit],span')]
    .filter(el=>visible(el) && !el.disabled && el.getAttribute('aria-disabled')!=='true');
const applyButtons = root => buttons(root).filter(el => /^(?:apply|apply coupon|apply code|apply promo code)$/i
    .test(clean(el.getAttribute('aria-label') || el.innerText || el.getAttribute('value'))));
const applyFor = input => {
    for (let parent=input.parentElement,depth=0;parent && depth<4;parent=parent.parentElement,depth++) {
        if (parent===document.body || parent===document.documentElement) break;
        const candidates=applyButtons(parent);
        if (candidates.length) return candidates.length===1 && couponFields().filter(el=>parent.contains(el)).length===1
            ? candidates[0] : null;
    }
    return null;
};
const money = text => {
    if (/\$|£|€|\bUSD\b|\bEUR\b|\bGBP\b|per\s*(?:adult|person|travell?er)|\/\s*adult/i.test(text)) return null;
    const matches=[...text.matchAll(/(?:₹|INR\b|Rs\.?)\s*(\d[\d,]*(?:\.\d+)?)/gi)];
    if (matches.length!==1) return null;
    const m=matches[0];
    if (!/^(?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3})(?:\.\d{1,2})?$/.test(m[1])) return null;
    if (/^[eE\d,.]|^\s+\d|^\s*\+/.test(text.slice(m.index+m[0].length))) return null;
    const n=Number(m[1].replace(/,/g,''));
    return Number.isFinite(n) ? n : null;
};
const totalLabel=/^(?:total payable|grand total|amount payable|net payable|total amount|total due|you pay)\b/i;
const feeLabel=/^(?:convenience|platform|service|payment|processing)\s+(?:fee|charge)s?\b/i;
const safeRow = text => /^(?:(?:total payable|grand total|amount payable|net payable|total amount|total due|you pay)|(?:(?:convenience|platform|service|payment|processing)\s+(?:fee|charge)s?))\s*[:\-]?\s*(?:₹|INR|Rs\.?)\s*[\d,.]+\s*$/i.test(text);
let inspectionTruncated=false;
const rowText = el => {
    const visibleText=[];
    const sub=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);
    let child;
    while ((child=sub.nextNode())) if (visible(child.parentElement)
        && !child.parentElement.closest('script,style,input,textarea,select,[contenteditable=true]')) visibleText.push(child.textContent);
    let rendered=clean(visibleText.join(' '));
    // EMT prints its currency using a visible rupee CSS icon, not a text glyph.
    const rupees=[...el.querySelectorAll('i.CurrncyCD_Rs')].filter(visible);
    if (rupees.length===1 && !/₹|INR|Rs\.?/i.test(rendered)) {
        rendered=rendered.replace(/(\d[\d,.]*)\s*$/, '₹ $1');
    }
    return rendered;
};
const rows = () => {
    const found=[];
    // Scope known EMT summary diagnostics to avoid its huge hidden templates.
    // Its provider adapter separately checks selected payment-total agreement.
    const summary=/^(?:www\.|flight\.)?easemytrip\.com$/i.test(location.hostname)
        ? document.querySelector('#spnGrndTotal')?.closest('.prm') : null;
    const walker=document.createTreeWalker(summary || document.body,NodeFilter.SHOW_TEXT);
    let node,visited=0;
    while ((node=walker.nextNode()) && visited++<16000) {
        const initial=clean(node.textContent),start=node.parentElement;
        if (!start || start.closest('script,style,template,input,textarea,select,[contenteditable=true]')
            || !visible(start) || !(totalLabel.test(initial) || feeLabel.test(initial))) continue;
        for (let el=start,depth=0;el && depth<3;el=el.parentElement,depth++) {
            if (el===document.body || el===document.documentElement) break;
            const text=clean(el.innerText);
            if (text.length>180) break;
            // Hidden money must not leak back through an ancestor's innerText.
            const rendered=rowText(el),amount=money(rendered);
            if (safeRow(rendered) && amount!==null && amount>=0 && visible(el)) {
                found.push({element:el,kind:totalLabel.test(rendered)?'total':'fee',
                    label:rendered.split(/₹|INR|Rs\.?/i)[0].replace(/[:\-]\s*$/,'').trim(),amount,
                    rect:el.getBoundingClientRect().toJSON()});
                break;
            }
        }
    }
    const distinct=found.filter((r,i)=>found.findIndex(x=>x.element===r.element)===i);
    inspectionTruncated=visited>=16000 || distinct.length>40;
    return distinct.slice(0,40);
};
'''


@dataclass
class Inspection:
    """Owned by a single async context; clear even on cancellation/error."""
    summary: dict = field(default_factory=dict)
    screenshots: list[bytearray] = field(default_factory=list, repr=False)

    def clear(self):
        self.summary.clear()
        for image in self.screenshots:
            image[:] = b'\0' * len(image)
            image.clear()
        self.screenshots.clear()


@asynccontextmanager
async def inspect_page(page, *, screenshots=False):
    """Inspect in memory; screenshots are opt-in monetary rows, never full page.

    No path is passed to Playwright and no disk/network/LLM sink exists. Python
    releases temporary bytes; this is lifecycle cleanup, not secure RAM erasure.
    Browser/OS caches are managed by the existing browser session separately.
    """
    inspection=Inspection()
    handles=[]
    try:
        inspection.summary=await page.evaluate('() => {'+DOM_HELPERS+r'''
            const fields=couponFields(),amounts=rows();
            const totals=[...new Set(amounts.filter(r=>r.kind==='total' && r.amount>0).map(r=>r.amount))];
            return {coupon_fields:fields.length,coupon_apply:fields.length===1 && !!applyFor(fields[0]),
                totals,fees:amounts.filter(r=>r.kind==='fee').map(({label,amount})=>({label,amount})),
                truncated:inspectionTruncated,
                final_verified:false};
        }''')
        if screenshots and not inspection.summary.get('truncated'):
            # Retain no full page HTML/screenshot. Each handle is disposed in finally.
            group=await page.evaluate_handle('() => {'+DOM_HELPERS+'return rows().map(r=>r.element).slice(0,8);}')
            handles.append(group)
            for key,handle in (await group.get_properties()).items():
                handles.append(handle)
                element=handle.as_element()
                if not key.isdigit() or element is None:
                    continue
                # A rerender could insert private text: revalidate just before capture.
                if not await element.evaluate('(el) => {'+DOM_HELPERS+'return visible(el) && safeRow(rowText(el));}'):
                    continue
                image=await element.screenshot(type='png',timeout=2500,
                    mask=[page.locator('input,textarea,select,[contenteditable],iframe')])
                inspection.screenshots.append(bytearray(image))
                del image
        yield inspection
    finally:
        inspection.clear()
        for handle in reversed(handles):
            try:
                await handle.dispose()
            except Exception:
                pass


async def coupon_control(page, action, *, code=None):
    """Resolve afresh and refuse ambiguous controls. Coupon actions only."""
    import re
    if action not in ('fill','apply','clear'):
        raise ValueError('Unsupported inspection action')
    if action=='fill' and (not isinstance(code,str) or not re.fullmatch(r'[A-Z0-9_-]{2,40}',code)):
        raise ValueError('Malformed coupon code; refusing browser interaction')
    handle=await page.evaluate_handle('(action) => {'+DOM_HELPERS+r'''
        const fields=couponFields();
        if (fields.length!==1) return null;
        return action==='apply' ? applyFor(fields[0]) : fields[0];
    }''',action)
    try:
        element=handle.as_element()
        if element is None:
            raise ValueError('Apply coupon control missing or ambiguous; no action taken' if action=='apply' else 'Coupon control missing or ambiguous; no action taken')
        if action in ('fill','clear'):
            await element.fill(code if action=='fill' else '',timeout=4000)
        else:
            # No JS click, coordinate guess, Pay/Book/Continue/Submit fallback.
            await element.click(timeout=4000)
    finally:
        await handle.dispose()

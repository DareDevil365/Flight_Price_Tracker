"""Read visible flight cards without inventing missing schedule or currency."""
LISTING_SCRIPT = r"""
(selectors) => {
  const cards = [...document.querySelectorAll(selectors)];
  const cardSet = new Set(cards), wrappers = new Set();
  for (const card of cards) {
    for (let parent=card.parentElement; parent; parent=parent.parentElement) {
      if (cardSet.has(parent)) wrappers.add(parent);
    }
  }
  const results = [];
  let candidates=0;
  const visible=node=>node.getBoundingClientRect().width>0 && node.getBoundingClientRect().height>0
    && !['hidden','collapse'].includes(getComputedStyle(node).visibility) && getComputedStyle(node).opacity!=='0';
  const moneyToken = value => {
    if (!/^(?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3})(?:\.\d{1,2})?$/.test(value)) return null;
    const amount=Number(value.replace(/,/g,''));
    return Number.isFinite(amount) && amount>0 ? amount : null;
  };
  const normalizeTime = (value) => {
    const m = value.match(/(\d{1,2}):(\d{2})\s*(AM|PM)?/i);
    if (!m) return '';
    let h = Number(m[1]);
    if (Number(m[2])>59 || (m[3] ? h<1 || h>12 : h>23)) return '';
    if (m[3]) h = h % 12 + (m[3].toUpperCase() === 'PM' ? 12 : 0);
    return String(h).padStart(2,'0')+':'+m[2];
  };
  for (const [index,card] of cards.entries()) {
    if (!visible(card)) continue;
    // A list wrapper is never one itinerary. Matching multiple selectors used
    // to combine the first fare/time with an airline elsewhere in the list.
    if (wrappers.has(card)) continue;
    candidates++;
    const text = card.innerText || '';
    if (text.length>3500) continue;
    const times = text.match(/\b\d{1,2}:\d{2}\s*(?:AM|PM)?\b/gi) || [];
    if (times.length < 2) continue;
    const flightNumbers=[...new Set((text.match(/\b(?:6E|AI|SG|QP|IX|I5|S5|2T|IC)\s*-?\s*\d{1,4}\b/gi)||[]).map(x=>x.replace(/[\s-]/g,'').toUpperCase()))];
    // Connecting cards need structured segments before they can be parsed.
    if (flightNumbers.length>1) continue;
    const lines = text.split('\n').map(x=>x.trim()).filter(Boolean);
    // Discounted/struck fares must not be selected as the current payable fare.
    const struck = new Set();
    for (const el of card.querySelectorAll('s,del,span,div')) {
      const style=getComputedStyle(el);
      if (!/line-through/.test(style.textDecorationLine) && style.opacity!=='0') continue;
      for (const m of (el.innerText || '').matchAll(/(?:₹|INR\b|Rs\.?)[\s]*([\d,]+(?:\.\d+)?)/gi)) {
        const amount=moneyToken(m[1]); if(amount) struck.add(amount);
      }
    }
    const prices = new Set();
    for (const line of lines) {
      if (/save|discount|cashback|coupon|lock|fee|tax|off\b/i.test(line)) continue;
      // India search: dollar fares cannot silently become rupees.
      if (/\$|\bUSD\b|\bEUR\b|\bGBP\b|£|€/i.test(line)) continue;
      for (const m of line.matchAll(/(?:₹|INR\b|Rs\.?)[\s]*([\d,]+(?:\.\d+)?)/gi)) {
        const amount=moneyToken(m[1]); if(amount && !struck.has(amount)) prices.add(amount);
      }
    }
    // Multiple current fare amounts without a supported fare-family reader are ambiguous.
    if (prices.size>1) continue;
    let price = prices.size===1 ? [...prices][0] : null;
    if (!price) {
      const fallbackPrices=new Set();
      for (const el of card.querySelectorAll('[id^="spnPrice"], [data-testid*="price"], .actual-price, .price, .priceSection, .fliFare, .flight-price')) {
        // EMT also uses spnPriceLock... for a deposit, not the flight fare.
        if (el.id.startsWith('spnPrice') && !/^spnPrice\d+$/i.test(el.id)) continue;
        if (!visible(el)) continue;
        let old=false;
        for(let ancestor=el;ancestor && ancestor!==card;ancestor=ancestor.parentElement) {
          const style=getComputedStyle(ancestor);
          // Floats and display:contents parents can have zero bounds while
          // their price child is painted. Only CSS hiding invalidates ancestors.
          if (ancestor.matches('s,del') || style.display==='none' || ['hidden','collapse'].includes(style.visibility)
              || style.opacity==='0' || /line-through/.test(style.textDecorationLine)) {old=true;break;}
        }
        if (old) continue;
        const scope=el.parentElement;
        const explicitINR=scope && (/₹|\bINR\b|\bRs\.?/i.test(scope.innerText)
          || [...scope.querySelectorAll('i.CurrncyCD_Rs,[data-currency="INR"]')].some(n=>n.getBoundingClientRect().width>0));
        if (explicitINR && !/\$|\bUSD\b|\bEUR\b|\bGBP\b|£|€|lock\s*price|price\s*lock|deposit|hold\s*fare/i.test(scope.innerText) && !/save|off\b/i.test(el.innerText)) {
          const m = el.innerText.trim().match(/^([\d,]+(?:\.\d+)?)$/);
          const amount=m ? moneyToken(m[1]) : null;
          if (amount && !struck.has(amount)) fallbackPrices.add(amount);
        }
      }
      if (fallbackPrices.size!==1) continue;
      price=[...fallbackPrices][0];
    }
    if (!price || !Number.isFinite(price)) continue;
    const perPerson=/per\s*(?:adult|person|travell?er)|\/\s*adult/i.test(text);
    const group=/total\s*(?:fare|price)|for\s*\d+\s*adults/i.test(text);
    let price_basis = perPerson && group ? 'unknown' : perPerson ? 'per_person' : group ? 'total' : 'unknown';
    // EMT's public fare panel explicitly labels the same amount as Grand Total.
    // Use it only when the labeled amount equals the displayed card fare.
    const grand=text.match(/Grand Total\s*(?:₹|INR\b|Rs\.?)?\s*([\d,]+(?:\.\d{1,2})?)/i);
    if (!perPerson && grand && Number(grand[1].replace(/,/g,''))===price) price_basis='total';
    const airlines = ['Air India Express','IndiGo','Air India','Akasa Air','SpiceJet','Alliance Air','Star Air','Emirates','Etihad','Qatar Airways','Singapore Airlines','British Airways','Lufthansa','Air France','KLM','Turkish Airlines','Thai Airways','AirAsia','Scoot','Fly91','FLY91'];
    const airline = airlines.find(a=>text.toLowerCase().replace(/\s/g,'').includes(a.toLowerCase().replace(/\s/g,'')));
    if (!airline) continue;
    const num = text.match(/\b(6E|AI|SG|QP|IX|I5|S5|2T|IC)\s*-?\s*(\d{1,4})\b/i);
    const stopCounts=new Set([...text.matchAll(/(\d+)\s*stops?/gi)].map(m=>Number(m[1])));
    if(/non.?stop/i.test(text))stopCounts.add(0);
    if(stopCounts.size!==1)continue;
    const stops=[...stopCounts][0];
    const duration = text.match(/\b\d+\s*h(?:rs?|ours?)?\s*(?:\d+\s*m(?:ins?|inutes?)?)?|\b\d+\s*m(?:ins?|inutes?)?/i);
    const connection_airports=[...new Set(lines.map(line=>line.match(/^\d+\s*h(?:rs?|ours?)?\s*(?:\d+\s*m(?:ins?|inutes?)?)?\s+([A-Z]{3})$/)).filter(Boolean).map(m=>m[1]))];
    const route = text.match(/\b([A-Z]{3})\s*[–—-]\s*([A-Z]{3})\b/);
    card.setAttribute('data-flight-finder-card', String(index));
    results.push({flight_number:num ? num[1].toUpperCase()+'-'+num[2] : '',airline,
      departure_time:normalizeTime(times[0]),arrival_time:normalizeTime(times[1]),
      duration:duration ? duration[0] : '',stops,base_price:price,price_basis,currency:'INR',
      origin:route ? route[1] : null,destination:route ? route[2] : null,
      connection_airports,
      nearby_airport: /departs from nearby airport|arrives at nearby airport|Navi Mumbai|Hindon|Manohar International|\(\d+\s*km from /i.test(text),
      selector:'[data-flight-finder-card="'+index+'"]'});
  }
  const source_inventory={complete:false,scope:'visible_dom_cards',candidate_cards:candidates,
    parsed_rows:results.length,rejected_cards:candidates-results.length,
    limitation:'Only supported visible cards are parsed; lazy-loaded, paginated and unsupported layouts may be absent.'};
  for(const result of results)result.source_inventory=source_inventory;
  return results;
}
"""

async def parse_cards(page,selectors):
    return await page.evaluate(LISTING_SCRIPT,selectors)

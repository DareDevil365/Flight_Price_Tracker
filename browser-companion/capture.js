export function captureCheckout(expected) {
  // Self-contained: Chrome serializes this function into an isolated tab world.
  // No input values, body text, cookies, storage, screenshots or network requests.
  const providers={'flight.easemytrip.com':'easemytrip','www.easemytrip.com':'easemytrip',
    'www.cleartrip.com':'cleartrip','www.makemytrip.com':'makemytrip'};
  const provider=providers[location.hostname];
  const result={schema_version:1,provider:provider || null,source_origin:provider ? location.origin : null,
    observed_at:new Date().toISOString(),status:'unverified',criteria_match:false,
    merchant_total:null,currency:null,selected_payment:null,fees:[],coupon_code:null,reasons:[],
    usable_as_final_price:false,eligible_for_learning:false,
    fee_scope:'Merchant display only. Later gateway or issuer charges are unconfirmed.'};
  if (!provider || location.protocol!=='https:') {result.reasons.push('Unsupported provider origin');return result;}
  const visible=el=>{
    if(!el || el.closest('[hidden],[inert],[aria-hidden="true"]') || el.getBoundingClientRect().width<=0 || el.getBoundingClientRect().height<=0)return false;
    for(let node=el;node;node=node.parentElement) {
      const style=getComputedStyle(node);
      if(style.display==='none' || ['hidden','collapse'].includes(style.visibility) || style.opacity==='0')return false;
    }
    return true;
  };
  // Cleartrip's ordinary-browser review is reachable even when a newly
  // launched browser fails booking creation. This branch reads only observed
  // semantic summary fields; it cannot certify a payment price or infer cabin.
  const reviewHeadings=[...document.querySelectorAll('h1')].filter(el=>visible(el) && el.textContent.trim()==='Review your itinerary');
  if(provider==='cleartrip' && reviewHeadings.length) {
    result.stage='review';result.status='review_partial';result.displayed_trip={};
    result.published_coupon_codes=[];
    result.fee_scope='Review display only. Convenience, payment, gateway and issuer charges are unconfirmed.';
    if(reviewHeadings.length!==1) {result.reasons.push('Review heading is ambiguous');return result;}
    const safe=el=>visible(el) && !el.closest('input,textarea,[contenteditable],[id*="passenger" i],[class*="passenger" i],[id*="contact" i],[class*="contact" i]');
    const text=el=>safe(el) ? el.textContent.trim().replace(/\s+/g,' ') : '';
    const flightPattern=/^(?:6E|AI|SG|QP|IX|I5|S5|2T|IC)\s*-?\s*\d{1,4}$/i;
    const datePattern=/^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(20\d{2})$/i;
    const routeParts=scope=>[...scope.querySelectorAll('h2')].filter(el=>safe(el) && /^\d{2}:\d{2}$/.test(text(el))).map(el=>{
      // Observed layout: time h2 and airport h2 are separate siblings in
      // one endpoint column; the airport heading contains an IATA span.
      const headings=[...el.parentElement.children].filter(node=>node.tagName==='H2' && safe(node));
      const airports=headings.filter(node=>/^[A-Z]{3}$/.test(text(node)));
      return headings.length===2 && airports.length===1 ? {time:text(el),airport:text(airports[0])} : null;
    }).filter(Boolean);
    let itinerary=null;
    for(let node=reviewHeadings[0].parentElement,depth=0;node && !node.matches('body,html') && depth<6;node=node.parentElement,depth++) {
      // The observed ordinary-browser itinerary has 387 descendants. Keep a
      // separate 500-element review bound; the payment contract below stays 300.
      if(node.querySelectorAll('*').length>500)break;
      const flights=[...node.querySelectorAll('p')].filter(el=>flightPattern.test(text(el)));
      if(flights.length===1 && routeParts(node).length===2) {itinerary=node;break;}
    }
    if(itinerary) {
      const parts=routeParts(itinerary),fields=[...itinerary.querySelectorAll('p')].map(text).filter(Boolean);
      const dates=fields.map(x=>x.match(datePattern)).filter(Boolean);
      const months=['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
      const flight=fields.find(x=>flightPattern.test(x));
      result.displayed_trip={origin:parts[0].airport,destination:parts[1].airport,
        departure_time:parts[0].time,arrival_time:parts[1].time,flight_number:flight.replace(/[\s-]/g,'').toUpperCase()};
      if(dates.length===1) {
        const [,day,month,year]=dates[0],iso=`${year}-${String(months.indexOf(month.toUpperCase())+1).padStart(2,'0')}-${day.padStart(2,'0')}`;
        const parsed=new Date(iso+'T00:00:00Z');
        if(Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0,10)===iso)result.displayed_trip.departure_date=iso;
      }
    } else result.reasons.push('One bounded supported itinerary summary was not found');
    const money=value=>{
      const match=value.match(/^(?:₹|INR\b|Rs\.?)\s*((?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3})(?:\.\d{1,2})?)$/i);
      const amount=match ? Number(match[1].replace(/,/g,'')) : null;
      return Number.isFinite(amount) && amount>0 ? amount : null;
    };
    const totalLabels=[...document.querySelectorAll('h3')].filter(el=>text(el)==='Total Price');
    if(totalLabels.length===1) {
      const row=totalLabels[0].parentElement,prices=[...row.querySelectorAll('h2')].filter(safe).map(el=>money(text(el))).filter(x=>x!==null);
      if(prices.length===1) {result.merchant_total=prices[0];result.currency='INR';}
      const publicSummary=row.parentElement;
      if(publicSummary && publicSummary.querySelectorAll('*').length<=100) {
        const adults=[...publicSummary.querySelectorAll('p')].map(text).map(x=>x.match(/^(\d+)\s+Adults?$/i)).filter(Boolean);
        if(adults.length===1)result.displayed_trip.passenger_count=Number(adults[0][1]);
      }
    }
    const codeNodes=[...document.querySelectorAll('h4[class*="nepCouponTagCode"]')];
    if(codeNodes.length<=40)result.published_coupon_codes=[...new Set(codeNodes.filter(safe).map(text).filter(x=>/^[A-Z][A-Z0-9]{1,39}$/.test(x)))].sort();
    const observed=result.displayed_trip;
    for(const key of ['origin','destination','departure_date','departure_time','passenger_count']) {
      if(observed[key]===undefined || observed[key]!==expected[key])result.reasons.push(key+' missing or different');
    }
    if(observed.flight_number!==expected.flight_number.replace(/[^A-Z0-9]/gi,'').toUpperCase())result.reasons.push('flight_number missing or different');
    // The validated real review displays a fare family, not cabin. SAVER does
    // not establish ECONOMY, and an expected value is not observed evidence.
    result.reasons.push('Cabin has not been established on this review layout');
    if(!result.merchant_total)result.reasons.push('A unique explicit INR review total was not found');
    result.reasons.push('Review price and published coupon codes have not been verified at payment');
    return result;
  }
  const scopes=[...document.querySelectorAll('[data-testid="booking-summary"],#bookingSummary,[aria-label="Booking summary"],.booking-summary')].filter(visible);
  if(scopes.length!==1) {result.reasons.push('One supported visible booking summary was not found');return result;}
  const scope=scopes[0], lines=[];
  // Leaf fields only; unknown prose, personal fields and arbitrary page text are discarded.
  const fields=scope.querySelectorAll('div,span,p,li,dt,dd');
  if(fields.length>300) {result.reasons.push('Summary exceeds bounded supported layout');return result;}
  const wanted=/^(?:[A-Z]{3}\s*[–—-]\s*[A-Z]{3}|(?:20\d{2}-\d{2}-\d{2})|\d{2}:\d{2}|[A-Z0-9]{2,3}\s*-?\s*\d{1,5}|\d+\s+adults?|(?:Adults?|Cabin|Class|Departure date|Flight number|Departure time)\s*[:\-]|Economy|Premium economy|Business|First(?: class)?|(?:Total payable|Grand total|Amount payable|Net payable|Total amount|Total due|You pay)|(?:Convenience|Platform|Service|Payment|Processing)\s+(?:fee|charge))\b/i;
  for(const el of fields) {
    if(!visible(el) || el.children.length || el.closest('input,textarea,[contenteditable],[id*="passenger" i],[class*="passenger" i],[id*="contact" i],[class*="contact" i]')) continue;
    const text=el.textContent.trim().replace(/\s+/g,' ');
    if(text.length<=100 && wanted.test(text)) lines.push(text);
  }
  const normalized=lines.map(x=>x.toUpperCase());
  const has=value=>normalized.includes(value.toUpperCase());
  const identity=[];
  if(!normalized.some(x=>x.replace(/\s/g,'')===`${expected.origin}–${expected.destination}` || x.replace(/\s/g,'')===`${expected.origin}-${expected.destination}` || x.replace(/\s/g,'')===`${expected.origin}—${expected.destination}`)) identity.push('Directed route missing or different');
  if(!has(expected.departure_date) && !has('Departure date: '+expected.departure_date)) identity.push('Full departure date missing or different');
  if(!has(expected.departure_time) && !has('Departure time: '+expected.departure_time)) identity.push('Departure time missing or different');
  const flight=expected.flight_number.replace(/[^A-Z0-9]/g,'');
  if(!normalized.some(x=>x.replace(/^FLIGHT NUMBER\s*[:\-]\s*/,'').replace(/[^A-Z0-9]/g,'')===flight)) identity.push('Flight number missing or different');
  const counts=new Set(lines.map(x=>x.match(/^(?:Adults?\s*:\s*(\d+)|(\d+)\s+adults?)$/i)).filter(Boolean).map(m=>Number(m[1] || m[2])));
  if(counts.size!==1 || !counts.has(expected.passenger_count)) identity.push('Adult count missing, conflicting or different');
  const cabins=new Set(lines.map(x=>x.match(/^(?:(?:Cabin|Class)\s*[:\-]\s*)?(Economy|Premium economy|Business|First)(?: class)?$/i)).filter(Boolean).map(m=>m[1].toUpperCase().replace(' ','_')));
  if(cabins.size!==1 || !cabins.has(expected.cabin_class)) identity.push('Cabin missing, conflicting or different');
  result.criteria_match=identity.length===0;result.reasons.push(...identity);
  const amount=text=>{
    if(/\$|USD|EUR|GBP|£|€/i.test(text)) return null;
    const match=text.match(/(?:₹|INR\b|Rs\.?)\s*((?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3})(?:\.\d{1,2})?)\s*$/i);
    if(!match)return null;
    const n=Number(match[1].replace(/,/g,''));return Number.isFinite(n) && n>=0 ? n : null;
  };
  const totals=new Set(lines.filter(x=>/^(?:Total payable|Grand total|Amount payable|Net payable|Total amount|Total due|You pay)\b/i.test(x)).map(amount).filter(x=>x>0));
  if(totals.size===1) {result.merchant_total=[...totals][0];result.currency='INR';}
  else result.reasons.push('A unique explicit INR merchant total was not found');
  for(const line of lines) {
    const match=line.match(/^(Convenience|Platform|Service|Payment|Processing)\s+(fee|charge)\b/i),fee=amount(line);
    if(match && fee!==null)result.fees.push({label:match[1].toLowerCase()+' '+match[2].toLowerCase(),amount:fee});
  }
  const paymentNodes=[...document.querySelectorAll('[data-testid="selected-payment-method"],[aria-label^="Selected payment method"]')].filter(visible);
  const methods=new Set(),banks=new Set();
  const bankNames=['HDFC','ICICI','SBI','AXIS','KOTAK','HSBC','IDFC','INDUSIND','YES','RBL'];
  for(const node of paymentNodes) {
    if(node.children.length)continue;
    const label=(node.getAttribute('aria-label') || node.textContent).slice(0,150);
    for(const [method,pattern] of [['UPI',/\bUPI\b/i],['CREDIT',/\bcredit\b/i],['DEBIT',/\bdebit\b/i],['NET_BANKING',/net\s*banking/i],['WALLET',/\bwallet\b/i]]) if(pattern.test(label))methods.add(method);
    for(const bank of bankNames)if(new RegExp('\\b'+bank+'\\b','i').test(label))banks.add(bank);
  }
  if(methods.size===1)result.selected_payment={method:[...methods][0],banks:[...banks].sort()};
  else result.reasons.push('An explicit unambiguous selected payment method was not found');
  const payAmounts=new Set([...document.querySelectorAll('button,[role="button"]')].filter(visible)
    .map(el=>el.textContent.trim()).filter(text=>/^(?:Pay(?: securely)?|Pay now)\s+(?:₹|INR\b|Rs\.?)/i.test(text)).map(amount).filter(x=>x>0));
  if(payAmounts.size!==1 || !payAmounts.has(result.merchant_total))result.reasons.push('Visible payment control amount does not confirm the summary total');
  // Presence of iframe payment does not grant inspection of the gateway origin.
  if([...document.querySelectorAll('iframe')].some(visible))result.reasons.push('Embedded gateway content has not been inspected');
  if(!result.reasons.length)result.status='merchant_snapshot';
  return result;
}

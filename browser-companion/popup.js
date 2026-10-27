import {captureCheckout} from './capture.js';
const form=document.querySelector('#capture'),status=document.querySelector('#status'),output=document.querySelector('#result');
form.addEventListener('submit',async event=>{
  event.preventDefault();output.hidden=true;
  const values=new FormData(form),expected=Object.fromEntries(values);
  for(const key of ['origin','destination','flight_number'])expected[key]=expected[key].toUpperCase();
  expected.passenger_count=Number(expected.passenger_count);
  const button=form.querySelector('button');button.disabled=true;status.textContent='Reading two snapshots, without changing the provider page…';
  try {
    const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
    if(!tab?.id)throw new Error('No active tab');
    const read=async()=>{
      const rows=await chrome.scripting.executeScript({target:{tabId:tab.id},func:captureCheckout,args:[expected]});
      if(rows.length!==1 || !rows[0].result)throw new Error('No supported top-frame response');
      return rows[0].result;
    };
    const first=await read();await new Promise(resolve=>setTimeout(resolve,1000));const second=await read();
    const fingerprint=row=>JSON.stringify({...row,observed_at:null});
    const stable=fingerprint(first)===fingerprint(second);
    if(!stable){second.status='unverified';second.reasons.push('Checkout evidence changed between snapshots');}
    second.stable_over_one_second=stable;
    output.textContent=JSON.stringify(second,null,2);output.hidden=false;
    status.textContent=second.status==='merchant_snapshot' ? 'Stable merchant evidence preview. Final payment and later charges remain unverified.'
      : second.status==='review_partial' ? 'Review evidence preview. Cabin, coupon eligibility and payment charges remain unverified.'
      : 'Incomplete evidence. Do not treat this as a verified final price.';
  } catch(error) {status.textContent='Could not read a supported provider page. No evidence was saved.';}
  finally{button.disabled=false;}
});

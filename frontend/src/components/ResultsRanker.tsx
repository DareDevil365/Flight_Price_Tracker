import { useState, useEffect, useRef } from "react";
import { useResultStore, useSearchStore, useBotStore } from "../store";
import IntelligenceCard from "./IntelligenceCard";
import GoogleBookingContext from './GoogleBookingContext';
import type { SearchResult, PublishedOffer } from "../types";

interface Props { sendMessage: (type: string, payload: Record<string, unknown>) => void }
const EMPTY_OFFERS: PublishedOffer[] = [];
const money = (value: number) => "₹" + value.toLocaleString("en-IN", {maximumFractionDigits: 2});
const verified = (r: SearchResult) => r.savings_breakdown?.verification === "checkout";
const currentReceipt = (r: SearchResult, handoff:Record<string,string>, now:number) => {
  if (!verified(r) || !r.session_id || handoff[r.session_id]!=='success') return false;
  const observed=Date.parse(r.savings_breakdown?.observed_at || '');
  return Number.isFinite(observed) && observed<=now+60_000 && now-observed<15*60_000;
};

export default function ResultsRanker({ sendMessage }: Props) {
  const results = useResultStore(s => s.results);
  const dealOptions=useResultStore(s=>s.dealOptions);
  const [feedback,setFeedback]=useState('');
  const [exploring,setExploring]=useState(false);
  const [transferEstimate,setTransferEstimate]=useState(2000);
  const alternatives=useResultStore(s=>s.alternatives);
  useEffect(()=>{
    const complete=()=>setExploring(false);
    const failed=(event:Event)=>{
      const payload=(event as CustomEvent).detail;
      if(payload?.originalType==='search:explore') setExploring(false);
      if(payload?.originalType==='coupon:refresh') useResultStore.getState().setOfferStatus('Offer refresh failed: '+(payload.message || 'Please retry.'));
    };
    const disconnected=()=>{
      setExploring(false);
      if(useResultStore.getState().offerStatus.startsWith('Refreshing')) useResultStore.getState().setOfferStatus('Offer refresh interrupted by connection loss. Reconnect and retry.');
    };
    window.addEventListener('alternatives_ready',complete);window.addEventListener('socket_disconnected',disconnected);window.addEventListener('request_error',failed);
    return()=>{window.removeEventListener('alternatives_ready',complete);window.removeEventListener('socket_disconnected',disconnected);window.removeEventListener('request_error',failed);};
  },[]);
  const suggestions = useResultStore(s => s.suggestions);
  const status = useSearchStore(s => s.status);
  const handoff = useResultStore(s => s.handoffStatus);
  const [receiptTime,setReceiptTime]=useState(Date.now);
  useEffect(()=>{
    if (!results.some(r=>verified(r) && r.session_id && handoff[r.session_id]==='success')) return;
    const timer=setInterval(()=>setReceiptTime(Date.now()),30_000);
    return()=>clearInterval(timer);
  },[results,handoff]);
  const checkoutStatus = useResultStore(s => s.checkoutStatus);
  const failures = Object.values(useBotStore(s => s.botStatuses)).filter(s => s.phase==='failed');
  const [code, setCode] = useState("");
  const [couponSite, setCouponSite] = useState("cleartrip");
  const [couponSaving,setCouponSaving]=useState(false);
  const couponPending=useRef(false);
  const [couponMessage,setCouponMessage]=useState('');
  useEffect(()=>{
    const added=(event:Event)=>{const p=(event as CustomEvent).detail;if(couponPending.current && p.platform===couponSite && p.code===code.trim()){couponPending.current=false;setCouponSaving(false);setCode('');setCouponMessage('Code saved. Actual savings still need verification.');}};
    const failed=(event:Event)=>{const p=(event as CustomEvent).detail;if(p?.originalType==='coupon:add' && couponPending.current){couponPending.current=false;setCouponSaving(false);setCouponMessage(p.message || 'Coupon could not be saved.');}};
    const disconnected=()=>{if(couponPending.current){couponPending.current=false;setCouponSaving(false);setCouponMessage('Connection lost. Check the coupon list before retrying.');}};
    window.addEventListener('coupon_added',added);window.addEventListener('request_error',failed);window.addEventListener('socket_disconnected',disconnected);
    return()=>{window.removeEventListener('coupon_added',added);window.removeEventListener('request_error',failed);window.removeEventListener('socket_disconnected',disconnected);};
  },[couponSite,code]);
  const offers = useResultStore(s=>s.offers[couponSite] || EMPTY_OFFERS);
  const couponTrackRecord=useResultStore(s=>s.couponTrackRecord[couponSite]);
  const offerStatus = useResultStore(s=>s.offerStatus);
  useEffect(()=>{ sendMessage('coupon:list',{platform:couponSite}); },[couponSite,sendMessage]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showFlagged,setShowFlagged]=useState(false);
  const flagged=results.filter(r=>r.savings_breakdown?.integrity?.status==='flagged');
  const groups = ["outbound", "inbound"].map(direction => ({
    direction,
    rows: results.filter(r => !dealOptions?.excludedResultIds.includes(r.id) && (r.savings_breakdown?.direction || "outbound") === direction && (showFlagged || r.savings_breakdown?.integrity?.status!=='flagged'))
      .sort((a,b) => Number(currentReceipt(b,handoff,Math.max(receiptTime,Date.now())))-Number(currentReceipt(a,handoff,Math.max(receiptTime,Date.now()))) || a.final_price-b.final_price)
  })).filter(g => g.rows.length);

  const open = (r: SearchResult) => {
    if (['makemytrip','easemytrip','cleartrip'].includes(r.platform)) {
      sendMessage('session:prepare', {searchId:r.search_id, resultId:r.id});
    } else if (r.session_id) {
      useResultStore.getState().setHandoffStatus(r.session_id, "pending");
      sendMessage("session:handoff", {sessionId:r.session_id});
    } else if (r.savings_breakdown?.booking_url) {
      window.open(r.savings_breakdown.booking_url, "_blank", "noopener,noreferrer");
    }
  };
  return <div className="page-container">
    <div className="page-header"><h1 className="page-title">Compare flight prices</h1>
      <p className="page-subtitle">Verified payable totals include the charges shown at checkout. Listed fares still need fee and coupon verification.</p></div>
    <div className="glass-card module-card" style={{marginBottom:20}}>
      <h3>Can’t use a deal?</h3><p>Read the payment conditions below. Tell us if a card or method is unavailable and we’ll compare the next options across websites.</p>
      <label>Deal restriction<textarea className="form-input" value={feedback} onChange={e=>setFeedback(e.target.value)} placeholder="e.g. I don’t have HDFC; exclude Flipkart Axis; no EMI; only UPI"/></label>
      <button className="btn btn-secondary" disabled={!feedback.trim() || !results.length} onClick={()=>sendMessage('search:feedback',{searchId:results[0].search_id,text:feedback})}>Find the next available deal</button>
      {dealOptions && <div><p>{dealOptions.message}</p>
        <p>{dealOptions.bestVerified ? 'Next verified payable option: '+money(dealOptions.bestVerified.final_price)+' on '+dealOptions.bestVerified.platform : 'No verified payable total is available for these restrictions yet.'}</p>
        {dealOptions.bestListed && <p>Lowest corroborated listed option: {money(dealOptions.bestListed.final_price)} on {dealOptions.bestListed.platform}. Its own fees and eligible coupons still need verification.</p>}
        <p>{dealOptions.eligibleOffers.length} conditional offers remain across the searched websites.</p>
        <details><summary>Excluded offers and reasons ({dealOptions.excludedOffers.length})</summary>
          {dealOptions.excludedOffers.map(c=><p key={c.platform+c.code}>{c.platform} · {c.code}: {c.filter_reason}</p>)}
        </details>
      </div>}
    </div>
    <div className="glass-card module-card" style={{marginBottom:20}}>
      <button className="btn btn-primary" onClick={()=>useSearchStore.getState().setActiveTab('watchlist')}>Add this trip to Red Room</button>
      <label style={{display:'block',margin:'12px 0'}}>Ground transfer estimate (₹)<input className="form-input" type="number" min="0" value={transferEstimate} onChange={e=>setTransferEstimate(Number(e.target.value))}/></label>
      <button className="btn btn-secondary" disabled={exploring || !results.length || status==='running'} onClick={()=>{
        setExploring(true);
        sendMessage('search:explore',{searchId:results[0].search_id,transferBudget:transferEstimate,hubs:['BOM','AMD']});
      }}>{exploring?'Searching real alternatives...':'Explore dates, airports & separate tickets'}</button>
      {alternatives.map((a,i)=><p key={i}><strong>{a.title}</strong> — {a.detail}</p>)}
    </div>
    {failures.length>0 && <div className="glass-card module-card" style={{marginBottom:20}}>
      <strong>Some websites could not be compared</strong>
      {failures.map(f=><p key={f.platform}>{f.platform}: {f.error || 'No usable quotes. See search logs.'} {f.manualUrl && <a href={f.manualUrl} target="_blank" rel="noopener noreferrer">Open exact search manually</a>}</p>)}
    </div>}
    {flagged.length>0 && <div className="glass-card module-card" style={{marginBottom:20}}>
      <strong>{flagged.length} suspicious result(s) quarantined</strong><p>They are excluded from recommendations and learning. A source disagreement needs investigation before booking.</p>
      <button className="btn btn-secondary" onClick={()=>setShowFlagged(!showFlagged)}>{showFlagged?'Hide':'Inspect'} flagged results</button>
    </div>}
    <div className="glass-card module-card" style={{marginBottom:20}}>
      <strong>When to buy</strong>
      {suggestions?.brain ? <IntelligenceCard report={suggestions.brain}/> : <p>{suggestions?.advice || "Search first, then verify checkout totals."}</p>}
      {suggestions?.suggestions?.map((s,i) => <p key={i}><strong>{s.title}: {money(s.saving)}</strong> — {s.detail}</p>)}
    </div>
    {results.length === 0 && <div className="glass-card module-card">
      {status === "running" ? "Searching selected websites. Results will appear as they arrive." : "No usable quotes yet. Start a search and check platform logs if a website fails."}
    </div>}
    {groups.map(group => {
      const currentVerified=(r:SearchResult)=>currentReceipt(r,handoff,Math.max(receiptTime,Date.now()));
      const best = group.rows.find(currentVerified);
      return <section key={group.direction} style={{marginBottom:24}}>
        <h2>{group.direction === "inbound" ? "Return leg (separate booking)" : "Outbound flights"}</h2>
        {best && <p>Lowest verified total among these results: <strong>{money(best.final_price)} on {best.platform}</strong>.</p>}
        {group.rows.map(r => {
          const meta = r.savings_breakdown || {};
          return <article key={r.id} className="glass-card module-card" style={{marginBottom:12}}>
            <div style={{display:"flex",flexWrap:"wrap",justifyContent:"space-between",gap:16}}>
              <div><strong>{r.airline} {r.flight_number || ""}</strong>
                <p>{meta.origin} → {meta.destination} · {r.departure_date} · {r.departure_time}–{r.arrival_time || "Unknown arrival"}</p>
                <p>{r.duration || "Duration unavailable"} · {r.stops === 0 ? "Nonstop" : r.stops+" stop(s)"} · {meta.passenger_count || 1} adult(s) · {meta.cabin_class || "Cabin unrecorded"}</p>
                {meta.layovers?.map((layover,i)=><p key={i}>Connection: {layover.airport} · {Math.floor(layover.duration/60)}h {layover.duration%60}m{layover.change_of_airport?' · airport change':''}. Confirm itinerary and terminals before booking.</p>)}
                <span className={currentVerified(r) ? "badge badge-success" : "badge badge-warning"}>{verified(r) && !currentVerified(r) ? 'Recorded checkout total — current session unconfirmed; reopen and reverify' : verified(r) ? "Checkout total verified for current session" : meta.source_freshness==='cache_age_unknown' ? "Cached price reference — age unknown" : "Listed fare — fees pending"}</span>
                <p><strong>Integrity: {meta.integrity?.status?.replaceAll('_',' ') || 'Historical result; unchecked'}</strong></p>
                {meta.integrity?.reasons?.map((reason,i)=><p key={i} style={{fontSize:12}}>{reason}</p>)}
                <p>{r.platform} · {meta.source_freshness==='cache_age_unknown' ? 'Retrieved' : 'Observed'} {meta.observed_at ? new Date(meta.observed_at).toLocaleString() : "time unknown"}</p>
                {meta.source_inventory && <details><summary>Search coverage: partial</summary>
                  <p>{meta.source_inventory.limitation}</p>
                  <p>{meta.source_inventory.parsed_rows ?? meta.source_inventory.normalized_rows ?? 0} parsed rows from {meta.source_inventory.candidate_cards ?? meta.source_inventory.returned_rows ?? 0} observed cards or returned rows. The app ranks at most 12 cheapest valid listings per website and leg.</p>
                </details>}
              </div>
              <div style={{minWidth:200,textAlign:"right"}}>
                {verified(r) && !currentVerified(r) && <p>Recorded payment total</p>}
                <div style={{fontSize:28,fontWeight:700}}>{money(r.final_price)}</div>
                {r.best_coupon_code && <p>{verified(r) && !currentVerified(r) ? 'Recorded coupon saving: ' : 'Coupon '}{r.best_coupon_code}{verified(r) && !currentVerified(r) ? ' · ' : ' saves '}{money(r.savings)}</p>}
                <p style={{maxWidth:300,fontSize:12}}>{meta.fee_status || "Historical result; rerun to verify."}</p>
                {meta.booking_problem && <p role="alert">{meta.booking_problem.message} The booking browser remains available for manual recovery.</p>}
                {verified(r) && meta.fee_scope && <p style={{maxWidth:300,fontSize:12}}>{meta.fee_scope}</p>}
                <button className="btn btn-primary" onClick={()=>open(r)} disabled={meta.integrity?.status==='flagged' || (!!r.session_id && handoff[r.session_id]==="pending")}>
                  {['makemytrip','easemytrip','cleartrip'].includes(r.platform) ? "Open booking" : "Open website"}
                </button>
                {r.session_id && handoff[r.session_id]==='success' && <p>Booking browser opened. Return here to verify the payment total.</p>}
                {r.session_id && handoff[r.session_id]==='failed' && <p>Booking session unavailable. Use Open booking to try preparing it again.</p>}
                {r.session_id && handoff[r.session_id]==='success' && ['makemytrip','easemytrip','cleartrip'].includes(r.platform) && <button className="btn btn-secondary" style={{marginLeft:8,marginTop:8}}
                  disabled={checkoutStatus[r.session_id]?.status==='running'}
                  onClick={()=>{
                    useResultStore.getState().setCheckoutStatus(r.session_id!, {status:'running',message:'Requesting cart verification…'});
                    sendMessage("session:verify",{sessionId:r.session_id});
                  }}>{checkoutStatus[r.session_id]?.status==='running'?'Testing this cart…':'Verify total & coupons'}</button>}
                {r.session_id && checkoutStatus[r.session_id] && <p role="status" style={{maxWidth:300,fontSize:12}}>{checkoutStatus[r.session_id].message}</p>}
                <GoogleBookingContext result={r} sendMessage={sendMessage}/>
              </div>
            </div>
            <button className="btn btn-secondary" onClick={()=>setExpanded(expanded===r.id ? null : r.id)}>Coupon details</button>
            {expanded===r.id && <div style={{marginTop:12}}>
              {meta.previous_checkout && <p>Previous payment observation: {money(meta.previous_checkout.price)}{meta.previous_checkout.coupon?' with '+meta.previous_checkout.coupon:''}, {meta.previous_checkout.observed_at?new Date(meta.previous_checkout.observed_at).toLocaleString():'time unavailable'}. It was withdrawn for a cart recheck and is retained only as a record.</p>}
              <p>Enter passenger details and select your intended payment method in Open booking, then return here to verify. Changing baggage, insurance, fare or payment can change the total.</p>
              {r.all_tested_coupons?.length ? r.all_tested_coupons.map((c,i)=><p key={i}><strong>{c.code}</strong>: {c.status.replaceAll("_"," ")} {c.price ? money(c.price) : ""} {c.reason || ""}</p>) : <p>No coupon has been verified for this flight.</p>}
              {meta.coupon_coverage && <p>Tested {meta.coupon_coverage.tested} of {meta.coupon_coverage.eligible} eligible codes · {meta.coupon_coverage.complete?'all eligible collected codes tested; discovery is not exhaustive':'partial or inconclusive coverage; no saving assumed for unresolved codes'}. {meta.coupon_coverage.collection}</p>}
            </div>}
          </article>
        })}
      </section>
    })}
    <div className="glass-card module-card"><h3>Published coupons &amp; bank offers</h3>
      <p>Discovered offers are candidates. Eligibility, savings and platform fees are verified on the payment page for your chosen flight.</p>
      <label>Coupon website<select aria-label="Coupon website" className="form-input" value={couponSite} disabled={couponSaving} onChange={e=>setCouponSite(e.target.value)}>
        {["makemytrip","easemytrip","cleartrip"].map(p=><option key={p}>{p}</option>)}</select></label>
      <button className="btn btn-secondary" disabled={offerStatus.startsWith('Refreshing')} onClick={()=>{
        useResultStore.getState().setOfferStatus('Refreshing public offer sources...');
        sendMessage('coupon:refresh',{platforms:[couponSite]});
      }}>Refresh offers</button>
      {offerStatus && <p>{offerStatus}</p>}
      <details><summary>Published candidates ({offers.length}) — conditions need checking</summary>
      {offers.length ? offers.map(c=><div key={c.code} style={{margin:'12px 0'}}>
        <strong>{c.code}</strong> · {c.bank_restriction || 'Read payment restrictions'} · {c.valid_until ? 'Published expiry '+c.valid_until : 'Expiry not published'}
        {dealOptions?.excludedOffers.find(x=>x.platform===c.platform && x.code===c.code) && <p>Excluded: {dealOptions.excludedOffers.find(x=>x.platform===c.platform && x.code===c.code)?.filter_reason}</p>}
        <p>{c.description || 'Read the source terms before applying.'}</p>
        {c.source_url && <a href={c.source_url} target="_blank" rel="noopener noreferrer">Offer source</a>}
      </div>) : <p>No explicit published codes cached for this website. You can add a current flight offer below.</p>}
      </details>
      <details><summary>Coupon track record ({couponTrackRecord?.length || 0} recent runs on {couponSite})</summary>
        <p>Success applies to the recorded booking, date, conditions and payment. Review trials do not verify final fees. Interrupted or pending runs are unverified; no website-wide guarantee is made.</p>
        <button className="btn btn-secondary" onClick={()=>sendMessage('coupon:list',{platform:couponSite})}>Refresh track record</button>
        {!couponTrackRecord?.length && <p>No scoped trials recorded yet. Published offers above have not been proven for your booking.</p>}
        {couponTrackRecord?.map(run=><details key={run.id} style={{margin:'12px 0'}}>
          <summary>{run.scope.origin || '?'} → {run.scope.destination || '?'} · {run.scope.departure_date || 'Date unverified'} · {run.status.replaceAll('_',' ')} · {new Date(run.started_at).toLocaleString()}</summary>
          <p>{run.scope.flight_number} · {run.scope.passenger_count || '?'} adult(s) · {run.scope.cabin_class} · {run.scope.payment?.method || 'Payment unverified'} {run.scope.payment?.banks?.join(', ')} · {run.scope.stage.replaceAll('_',' ')}</p>
          {run.summary.best_price!=null && <p>Observed total: {money(run.summary.best_price)} · {run.status==='checkout_verified'?'Best confirmed during this run: ':'Lowest observed during this unverified run (conditions still apply): '}{run.summary.best_coupon || 'No reducing code'}.</p>}
          {run.summary.coverage && <p>{run.summary.coverage.manual_review?`Manually tried ${run.summary.coverage.tested} candidate(s) at review; complete booking eligibility is unconfirmed.`:`Tested ${run.summary.coverage.tested} of ${run.summary.coverage.eligible} eligible collected codes.`} {run.summary.coverage.complete?'Discovery is not exhaustive.':'Conditional, untested or unresolved offers remain; no saving is assumed for them.'}</p>}
          {run.summary.reason && <p>{run.summary.reason}</p>}
          {run.trials.map((trial,i)=><div key={i}><strong>{trial.code}: {trial.status==='valid_match' && run.status!=='checkout_verified'?'accepted at review; payment eligibility unverified':trial.status.replaceAll('_',' ')}</strong>
            <p>{trial.price!=null ? money(trial.price) : ''} {trial.savings!=null ? ' · Saving '+money(trial.savings) : ''} · {new Date(trial.observed_at).toLocaleString()}</p>
            {trial.reason && <p>{trial.reason}</p>}
            <p>Terms seen: {trial.terms || trial.restrictions || 'No restrictions established.'}</p>
            {trial.source_host && <p>Collected from: {trial.source_host}</p>}
            {trial.valid_until && <p>Published expiry: {trial.valid_until}</p>}
            {trial.source_url && <a href={trial.source_url} target="_blank" rel="noopener noreferrer">Published offer source</a>}
          </div>)}
        </details>)}
      </details>
      <h3>Add a coupon to test</h3>
      <p>Use a code from a current offer. The app will check eligibility and test its actual checkout savings.</p>
      <div className="flex-row gap-md">
        <input aria-label="Coupon code" className="form-input" placeholder="Coupon code" value={code} disabled={couponSaving} onChange={e=>setCode(e.target.value.toUpperCase())}/>
        <button className="btn btn-primary" disabled={!code.trim() || couponSaving} onClick={()=>{
          couponPending.current=true;setCouponSaving(true);setCouponMessage('Saving code...');
          sendMessage("coupon:add",{platform:couponSite,code:code.trim(),description:"User supplied flight coupon; eligibility needs verification",discount_type:"FLAT",discount_value:0,source:"user"});
        }}>{couponSaving?'Saving...':'Save code'}</button></div>
      {couponMessage && <p role="status">{couponMessage}</p>}
    </div>
  </div>;
}

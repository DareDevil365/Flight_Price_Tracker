import { useEffect, useState } from 'react';
import { useSearchStore, useSettingsStore, useResultStore } from '../store';
import IntelligenceCard from './IntelligenceCard';
import Watchlist from './Watchlist';
import { validDate, localDate } from '../dateUtils';

export default function RedRoom({sendMessage}:{sendMessage:(type:string,payload:Record<string,unknown>)=>void}) {
  const trip=useSearchStore(s=>s.trip);
  const financial=useSettingsStore(s=>s.financial);
  const items=useResultStore(s=>s.redRoomItems);
  const notifications=useResultStore(s=>s.notifications);
  const [origin,setOrigin]=useState(trip.origin?.code || 'GOI');
  const [destination,setDestination]=useState(trip.destination?.code || 'HYD');
  const [day,setDay]=useState(trip.departureDate);
  const [target,setTarget]=useState('');
  const [hours,setHours]=useState(24);
  const [adults,setAdults]=useState(trip.passengerCount);
  const [cabin,setCabin]=useState(trip.cabinClass);
  const [maxStops,setMaxStops]=useState<number|null>(trip.maxStops ?? null);
  const [preferredTime,setPreferredTime]=useState(trip.preferredTime);
  const [explore,setExplore]=useState(false);
  const [transfer,setTransfer]=useState(2000);
  const [addPending,setAddPending]=useState(false);
  const [addError,setAddError]=useState('');
  useEffect(()=>{sendMessage('redroom:list',{});sendMessage('notifications:get',{});},[sendMessage]);
  useEffect(()=>{
    const reset=()=>setAddPending(false);
    const failed=(event:Event)=>{const p=(event as CustomEvent).detail;if(p?.originalType==='redroom:add'){setAddPending(false);setAddError(p.message || 'Request could not be saved.');}};
    const roomError=(event:Event)=>{setAddPending(false);setAddError((event as CustomEvent).detail?.message || 'Request failed. Check the backend logs.');};
    const disconnected=()=>{setAddPending(false);setAddError('Connection lost. Check saved requests after reconnecting before retrying.');};
    window.addEventListener('redroom_error',roomError);window.addEventListener('redroom_data',reset);window.addEventListener('request_error',failed);window.addEventListener('socket_disconnected',disconnected);
    return()=>{window.removeEventListener('redroom_error',roomError);window.removeEventListener('redroom_data',reset);window.removeEventListener('request_error',failed);window.removeEventListener('socket_disconnected',disconnected);};
  },[]);
  return <div className="page-container"><div className="page-header"><h1 className="page-title">Red Room</h1>
    <p className="page-subtitle">Save a future trip. The backend checks fares, published offers and market context at your chosen interval, and keeps booking recommendations here.</p></div>
    <div className="glass-card module-card">
      <p>Checks continue when this browser tab is closed, while the backend is running. Windows desktop alerts are attempted when a booking recommendation changes; alerts are also saved here. Enable automatic startup with Enable-RedRoom.ps1. Monitoring pauses while the computer is off or asleep.</p>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(150px,1fr))',gap:12}}>
        <label>Origin<input className="form-input" value={origin} onChange={e=>setOrigin(e.target.value.toUpperCase())}/></label>
        <label>Destination<input className="form-input" value={destination} onChange={e=>setDestination(e.target.value.toUpperCase())}/></label>
        <label>Departure<input className="form-input" type="date" value={day} onChange={e=>setDay(e.target.value)}/></label>
        <label>Total target (optional, ₹)<input className="form-input" type="number" min="1" value={target} onChange={e=>setTarget(e.target.value)}/></label>
        <label>Adults<input className="form-input" type="number" min="1" max="9" value={adults} onChange={e=>setAdults(Number(e.target.value))}/></label>
        <label>Cabin<select className="form-input" value={cabin} onChange={e=>setCabin(e.target.value)}>{['ECONOMY','PREMIUM_ECONOMY','BUSINESS','FIRST'].map(c=><option key={c}>{c}</option>)}</select></label>
        <label>Stops<select className="form-input" value={maxStops ?? 'ANY'} onChange={e=>setMaxStops(e.target.value==='ANY'?null:Number(e.target.value))}><option value="ANY">Any</option><option value="0">Nonstop only</option><option value="1">At most one</option><option value="2">At most two</option></select></label>
        <label>Departure time<select className="form-input" value={preferredTime} onChange={e=>setPreferredTime(e.target.value)}>{['ANY','MORNING','AFTERNOON','EVENING','NIGHT'].map(t=><option key={t}>{t}</option>)}</select></label>
        <label>Check every<select className="form-input" value={hours} onChange={e=>setHours(Number(e.target.value))}>{[6,12,24,48,168].map(h=><option key={h} value={h}>{h} hours</option>)}</select></label>
        <label>Ground-transfer estimate (₹)<input className="form-input" type="number" min="0" value={transfer} onChange={e=>setTransfer(Number(e.target.value))}/></label>
      </div>
      <label style={{display:'block',margin:'16px 0'}}><input type="checkbox" checked={explore} onChange={e=>setExplore(e.target.checked)}/> Also search adjacent dates, GOI/GOX and separate tickets via BOM/AMD (more website searches)</label>
      <p>Bank/payment preferences are copied from Settings when you save. The target applies to all adults combined. A listed-price alert still needs payment-page verification.</p>
      <button className="btn btn-primary" disabled={addPending} onClick={()=>{
        setAddError('');
        if (!/^[A-Z]{3}$/.test(origin.trim()) || !/^[A-Z]{3}$/.test(destination.trim()) || origin.trim()===destination.trim()) {setAddError('Enter two different Indian airport codes.');return;}
        if (!validDate(day) || day<=localDate()) {setAddError('Choose a future departure date.');return;}
        if (!Number.isInteger(adults) || adults<1 || adults>9) {setAddError('Choose between 1 and 9 whole adult passengers.');return;}
        if ((target && (!Number.isFinite(Number(target)) || Number(target)<=0)) || !Number.isFinite(transfer) || transfer<0) {setAddError('Enter a positive target and a nonnegative transfer estimate.');return;}
        setAddPending(true);
        sendMessage('redroom:add',{trip:{origin:origin.trim(),destination:destination.trim(),departureDate:day,passengerCount:adults,cabinClass:cabin,preferredTime,maxStops,tripType:'one_way'},financial,
          targetPrice:target ? Number(target) : null,intervalHours:hours,exploreAlternatives:explore,transferBudget:transfer,hubs:['BOM','AMD']});
      }}>{addPending?'Saving request...':'Add to Red Room'}</button>
      {addError && <p role="alert">{addError}</p>}
      <button className="btn btn-secondary" style={{marginLeft:8}} onClick={()=>{
        if ('Notification' in window) Notification.requestPermission();
      }}>Enable browser alerts</button>
    </div>
    {items.length===0 && <p>No saved booking requests. Add one to start collecting comparable history.</p>}
    {items.map(item=><article key={item.id} className="glass-card module-card" style={{marginTop:20}}>
      <h2>{item.request.trip.origin} → {item.request.trip.destination} · {item.request.trip.departureDate}</h2>
      <p>{item.request.trip.passengerCount} adult(s), {item.request.trip.cabinClass} · every {item.interval_hours} hours · {item.checking?'Checking now':item.last_checked?'Last checked '+new Date(item.last_checked).toLocaleString():'Waiting for first check'}</p>
      {item.last_error && <p role="alert">Latest check failed: {item.last_error}. Any report below is from the previous successful check.</p>}
      <p>Last successful check: {item.last_success ? new Date(item.last_success).toLocaleString() : 'No successful check recorded yet'}</p>
      <IntelligenceCard report={item.report}/>
      {item.report?.alternatives?.map((a,i)=><p key={i}><strong>{a.title}</strong> — {a.detail}</p>)}
      <button className="btn btn-secondary" disabled={item.checking} onClick={()=>sendMessage('redroom:check',{id:item.id})}>Check now</button>
      <button className="btn btn-secondary" style={{marginLeft:8}} onClick={()=>sendMessage('redroom:remove',{id:item.id})}>Remove request</button>
    </article>)}
    <div className="glass-card module-card" style={{marginTop:20}}><h2>Saved alerts</h2>
      {!notifications.length && <p>No alerts yet. Only actionable recommendation changes are saved.</p>}
      {notifications.map(n=><div key={n.id} style={{margin:'12px 0'}}><strong>{n.title}</strong><p>{n.message}</p><small>{n.created_at}</small>{!n.is_read && <button className="btn btn-secondary" onClick={()=>sendMessage('notifications:read',{id:n.id})}>Mark read</button>}</div>)}
    </div>
    <details style={{marginTop:20}}><summary>Older listed-fare watches</summary><Watchlist sendMessage={sendMessage}/></details>
  </div>;
}

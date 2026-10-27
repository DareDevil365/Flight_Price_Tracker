import { useEffect, useState, useCallback } from "react";
import { XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line, CartesianGrid, Legend } from "recharts";
import IntelligenceCard from "./IntelligenceCard";
import { useResultStore, useSearchStore } from "../store";

export default function PriceHistory({sendMessage}:{sendMessage:(type:string,payload:Record<string,unknown>)=>void}) {
  const trip = useSearchStore(s=>s.trip);
  const history = useResultStore(s=>s.historyData);
  const brain=useResultStore(s=>s.brain);
  const brainError=useResultStore(s=>s.brainError);
  const [route,setRoute]=useState(trip.origin && trip.destination ? trip.origin.code+"-"+trip.destination.code : "DEL-BOM");
  const [day,setDay]=useState(trip.departureDate);
  const query=useCallback(()=> {
    if (!/^[A-Z]{3}-[A-Z]{3}$/.test(route.trim().toUpperCase()) || !/^\d{4}-\d{2}-\d{2}$/.test(day)) return;
    const requestId=crypto.randomUUID();
    useResultStore.setState({intelligenceRequestId:requestId,brain:null,brainError:null,historyData:[],prediction:null});
    const payload={requestId,route:route.trim().toUpperCase(),date:day,passengerCount:trip.passengerCount,cabinClass:trip.cabinClass,preferredTime:trip.preferredTime,maxStops:trip.maxStops};
    sendMessage("history:get",payload); sendMessage("brain:get",payload);
  }, [route,day,trip.passengerCount,trip.cabinClass,trip.preferredTime,trip.maxStops,sendMessage]);
  useEffect(()=> {
    useResultStore.setState({intelligenceRequestId:null,brain:null,brainError:null,historyData:[]});
    const timer=setTimeout(query,400);
    return ()=>{clearTimeout(timer);useResultStore.setState({intelligenceRequestId:null,brain:null,historyData:[]});};
  }, [query]);
  // Compare daily cheapest observations for this exact travel date, cabin and count.
  const days = new Map<string,{date:string;listed?:number;checkout?:number}>();
  for (const row of history) {
    const date = row.observed_at?.slice(0,10);
    if (!date || row.price<=0) continue;
    const key=row.verification==='checkout' ? 'checkout' : 'listed';
    const entry=days.get(date) || {date};
    entry[key]=Math.min(entry[key] ?? Infinity,row.price);
    days.set(date,entry);
  }
  const data=[...days.values()].sort((a,b)=>a.date.localeCompare(b.date));
  return <div className="page-container"><div className="page-header">
    <h1 className="page-title">Price history &amp; booking advice</h1>
    <p className="page-subtitle">Actual observations for the same departure date, adult count and cabin. Listed fares and verified checkout totals are shown separately.</p></div>
    <div className="glass-card module-card">
      <div className="flex-row gap-md">
        <label>Route<input className="form-input" value={route} onChange={e=>setRoute(e.target.value)} /></label>
        <label>Departure<input className="form-input" type="date" value={day} onChange={e=>setDay(e.target.value)} /></label>
        <button className="btn btn-primary" onClick={query}>Refresh</button>
      </div><p>{trip.passengerCount} adult(s), {trip.cabinClass}, {trip.preferredTime || 'ANY'} time, {trip.maxStops == null ? 'any stops' : `at most ${trip.maxStops} stops`}. Change these in Search.</p>
      {data.length ? <div style={{height:300}}><ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}><CartesianGrid strokeDasharray="3 3"/><XAxis dataKey="date"/><YAxis domain={["auto","auto"]}/>
          <Tooltip formatter={(v)=>["₹"+Number(v).toLocaleString("en-IN"),"Fare"]}/>
          <Legend/><Line name="Listed fare (fees pending)" dataKey="listed" stroke="#fbbf24" dot connectNulls={false}/><Line name="Verified checkout total" dataKey="checkout" stroke="#818cf8" dot connectNulls={false}/></LineChart>
      </ResponsiveContainer></div> : <p>No observations for this exact trip yet. Run a search to start its price history.</p>}
    </div>
    <div className="glass-card module-card" style={{marginTop:20}}>
      {brainError ? <p role="alert">{brainError} No booking recommendation was produced. Retry when the problem is resolved.</p> : <IntelligenceCard report={brain}/>}
      <p>Historical checkout totals reflect the payment and add-on choices at that time. Refresh your search and verify your selected payment before buying. Forecasts appear only after the model passes its evidence checks.</p>
    </div>
  </div>;
}

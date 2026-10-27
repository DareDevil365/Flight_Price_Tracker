import { useEffect, useState } from "react";
import { usePlatformStore } from "../store";
export default function ManageWebsites({sendMessage}:{sendMessage:(type:string,payload:Record<string,unknown>)=>void}) {
  const platforms=usePlatformStore(s=>s.platforms);
  const [name,setName]=useState("");
  const [url,setUrl]=useState("");
  useEffect(()=>{sendMessage("platform:list",{});},[sendMessage]);
  return <div className="page-container"><div className="page-header"><h1 className="page-title">Travel websites</h1>
    <p className="page-subtitle">Search adapters are available for MakeMyTrip, EaseMyTrip, Cleartrip and Google Flights. Other websites are saved as links for manual comparison.</p></div>
    <div className="glass-card module-card">
      <form onSubmit={e=>{e.preventDefault();sendMessage("platform:add",{name:name.trim(),url:url.trim()});setName("");setUrl("");}}>
        <label className="form-label">Website name<input className="form-input" required value={name} onChange={e=>setName(e.target.value)}/></label>
        <label className="form-label">HTTPS address<input className="form-input" type="url" placeholder="https://..." required value={url} onChange={e=>setUrl(e.target.value)}/></label>
        <button className="btn btn-primary">Save website link</button>
      </form>
    </div>
    {platforms.map(p=><div className="glass-card module-card" style={{marginTop:12,display:"flex",justifyContent:"space-between",gap:12}} key={p.id}>
      <div><strong>{p.name}</strong><p>{["makemytrip","easemytrip","cleartrip","google_flights"].includes(p.id)?"Search adapter available; live accessibility varies.":"Manual comparison link"}</p></div>
      <a className="btn btn-secondary" href={p.url} target="_blank" rel="noopener noreferrer">Open website</a>
    </div>)}
  </div>;
}

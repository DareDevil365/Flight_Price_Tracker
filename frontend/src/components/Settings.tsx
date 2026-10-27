import { useState } from "react";
import { useSettingsStore } from "../store";
export default function Settings({sendMessage}:{sendMessage:(type:string,payload:Record<string,unknown>)=>void}) {
  const financial=useSettingsStore(s=>s.financial);
  const cloak=useSettingsStore(s=>s.cloak);
  const updateFinancial=useSettingsStore(s=>s.updateFinancial);
  const updateCloak=useSettingsStore(s=>s.updateCloak);
  const [saved,setSaved]=useState(false);
  return <div className="page-container"><div className="page-header"><h1 className="page-title">Preferences</h1>
    <p className="page-subtitle">Set financing preferences and browser behavior.</p></div>
    <div className="glass-card module-card">
      <p>Search first and read the deal conditions. Use the results text box to exclude unavailable cards or payment methods. No card details are needed here.</p>
      <p>Excluded banks: {financial.blacklistedBanks.join(', ') || 'None'}. Excluded cards: {financial.excludedCardNames?.join(', ') || 'None'}.</p>
      <button className="btn btn-secondary" onClick={()=>{setSaved(false);updateFinancial({blacklistedBanks:[],excludedCardNames:[],customInstructions:'',allowedCardTypes:['CREDIT','DEBIT','UPI']});}}>Reset deal exclusions</button>
      <div style={{display:"flex",gap:24,flexWrap:"wrap",margin:"20px 0"}}>
        <label><input type="checkbox" checked={financial.allowEMI} onChange={e=>{setSaved(false);updateFinancial({allowEMI:e.target.checked});}}/> Allow EMI offers</label>
        <label><input type="checkbox" checked={financial.allowBNPL} onChange={e=>{setSaved(false);updateFinancial({allowBNPL:e.target.checked});}}/> Allow pay-later offers</label>
        <label><input type="checkbox" checked={financial.allowWalletOffers} onChange={e=>{setSaved(false);updateFinancial({allowWalletOffers:e.target.checked});}}/> Allow wallet offers</label>
      </div>
      <p>EMI interest, processing fees and future rewards are not verified savings. Compare your lender's full repayment terms separately.</p>
    </div>
    <div className="glass-card module-card" style={{marginTop:20}}>
      <label><input type="checkbox" checked={!!cloak.showBrowser} onChange={e=>{setSaved(false);updateCloak({showBrowser:e.target.checked});}}/> Show browser during searches</label>
      <label className="form-label" style={{marginTop:18}}>Concurrent websites</label>
      <select className="form-input" value={Math.min(3,cloak.maxConcurrentBots)} onChange={e=>{setSaved(false);updateCloak({maxConcurrentBots:Number(e.target.value)});}}>
        {[1,2,3].map(n=><option key={n} value={n}>{n}</option>)}</select>
      <p>Each booking gets its own browser context. Sessions expire after 15 minutes; opening or verifying refreshes the timer.</p>
    </div>
    <button className="btn btn-primary" style={{marginTop:20}} onClick={()=>{
      sendMessage("settings:update",{financial:{...financial,whitelistedBanks:[],blacklistedBanks:financial.blacklistedBanks},cloak});
      setSaved(true);
    }}>Save preferences</button>{saved && <p>Preferences sent to backend. Changes apply to new searches.</p>}
  </div>;
}

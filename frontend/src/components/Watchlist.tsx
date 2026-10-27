import { useState, useEffect } from "react";
import { Plus, Trash2, RefreshCw } from "lucide-react";
import { useResultStore } from "../store";
import { observedTime, localDate } from '../dateUtils';

interface WatchlistProps {
  sendMessage: (type: string, payload: Record<string, unknown>) => void;
}

export default function Watchlist({ sendMessage }: WatchlistProps) {
  const watchlist = useResultStore((s) => s.watchlist);
  useEffect(() => { sendMessage('watchlist:list', {}); }, [sendMessage]);

  const [origin, setOrigin] = useState("");
  const [dest, setDest] = useState("");
  const [date, setDate] = useState("");
  const [price, setPrice] = useState("");

  const handleAdd = () => {
    if (!origin || !dest || !price || !date) {
      alert("Please fill in all watchlist fields.");
      return;
    }
    const item = {
      origin: origin.toUpperCase(),
      destination: dest.toUpperCase(),
      departure_date: date,
      target_price: parseFloat(price),
      check_frequency: "daily",
      is_active: true,
    };
    sendMessage("watchlist:add", item);
    setOrigin("");
    setDest("");
    setDate("");
    setPrice("");
  };

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Auto-Scout Watchlist</h1>
        <p className="page-subtitle">Monitor one adult in economy while the app is running. Listed-fare alerts still need checkout verification.</p>
      </div>

      {/* Add Form */}
      <div className="glass-card module-card" style={{ marginBottom: 20 }}>
        <span className="form-label" style={{ marginBottom: 14 }}>Watch New Route</span>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 12, alignItems: "end" }}>
          <div>
            <label className="form-label">Origin</label>
            <input type="text" className="form-input" placeholder="DEL" value={origin} onChange={(e) => setOrigin(e.target.value)} />
          </div>
          <div>
            <label className="form-label">Destination</label>
            <input type="text" className="form-input" placeholder="GOI" value={dest} onChange={(e) => setDest(e.target.value)} />
          </div>
          <div>
            <label className="form-label">Departure</label>
            <input type="date" className="form-input" value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
          <div>
            <label className="form-label">Target (₹)</label>
            <input type="number" className="form-input" placeholder="4500" value={price} onChange={(e) => setPrice(e.target.value)} />
          </div>
          <button className="btn btn-primary" onClick={handleAdd}>
            <Plus size={14} />
            Watch
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="glass-card module-card">
        {watchlist.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-desc">No active route watches scheduled.</div>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Route</th>
                <th>Departure</th>
                <th>Target</th>
                <th>Last Price</th>
                <th>Status</th>
                <th style={{ textAlign: "center" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {watchlist.map((item) => (
                <tr key={item.id}>
                  <td style={{ fontWeight: 600 }}>{item.origin} → {item.destination}</td>
                  <td>{item.departure_date}</td>
                  <td>₹{item.target_price.toLocaleString("en-IN")}</td>
                  <td>{item.last_price ? `₹${item.last_price.toLocaleString("en-IN")}` : "Not checked yet"}</td>
                  <td>
                    <span className="badge badge-success">{item.departure_date < localDate() ? 'Date passed' : item.is_active ? 'Active' : 'Paused'}</span><div style={{fontSize:11}}>{item.last_checked ? observedTime(item.last_checked) : 'Waiting for first check'}</div>
                  </td>
                  <td style={{ textAlign: "center" }}>
                    <button className="btn btn-secondary" onClick={()=>sendMessage('watchlist:check',{watchId:item.id})} aria-label={`Check ${item.origin}-${item.destination} now`}><RefreshCw size={14}/> Check now</button>
                    <button
                      className="btn-ghost"
                      style={{ color: "hsl(var(--color-error))", background: "none", border: "none", cursor: "pointer", padding: 4 }}
                      aria-label={`Remove watch for ${item.origin}-${item.destination}`}
                      onClick={() => sendMessage('watchlist:remove', {watchId:item.id})}
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

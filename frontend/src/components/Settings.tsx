import { useState, useEffect } from "react";
import { Trash2, Plus } from "lucide-react";
import { useSettingsStore, useApiStore } from "../store";

export default function Settings() {
  const financial = useSettingsStore((s) => s.financial);
  const updateFinancial = useSettingsStore((s) => s.updateFinancial);
  const cloak = useSettingsStore((s) => s.cloak);
  const updateCloak = useSettingsStore((s) => s.updateCloak);
  const apiKeys = useApiStore((s) => s.apiKeys);

  const [newBank, setNewBank] = useState("");
  const [newRate, setNewRate] = useState("");
  const [currentTime, setCurrentTime] = useState(Date.now());

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(Date.now());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const handleAddCard = () => {
    if (!newBank || !newRate) return;
    const rate = parseFloat(newRate);
    if (isNaN(rate)) return;
    updateFinancial({
      cardRewardRates: [...financial.cardRewardRates, { bank: newBank.toUpperCase(), rate }],
    });
    setNewBank("");
    setNewRate("");
  };

  const handleRemoveCard = (bank: string) => {
    updateFinancial({
      cardRewardRates: financial.cardRewardRates.filter((c) => c.bank !== bank),
    });
  };

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">System Preferences</h1>
        <p className="page-subtitle">Manage credit card reward rates, residential proxy credentials, and cache sizes.</p>
      </div>

      <div className="grid-2-1">
        {/* Card Rewards */}
        <div className="glass-card module-card">
          <h3 style={{ margin: "0 0 4px", fontSize: 15, fontWeight: 600 }}>Credit Card Reward Rates</h3>
          <p style={{ fontSize: 12, color: "hsl(var(--text-secondary))", marginBottom: 18 }}>
            Used to calculate effective pricing by subtracting reward values from checkout totals.
          </p>

          <div className="flex-col gap-sm" style={{ marginBottom: 18 }}>
            {financial.cardRewardRates.map((card) => (
              <div
                key={card.bank}
                className="flex-row"
                style={{
                  justifyContent: "space-between",
                  background: "hsl(var(--bg-primary))",
                  padding: "10px 14px",
                  borderRadius: "var(--border-radius)",
                  border: "1px solid hsl(var(--card-border))",
                }}
              >
                <span style={{ fontWeight: 600, fontSize: 13 }}>{card.bank} Card</span>
                <div className="flex-row gap-md">
                  <span style={{ color: "hsl(var(--color-success))", fontWeight: 600, fontSize: 12 }}>
                    {card.rate}% Reward
                  </span>
                  <button
                    style={{ background: "transparent", border: "none", color: "hsl(var(--color-error))", cursor: "pointer", padding: 0 }}
                    onClick={() => handleRemoveCard(card.bank)}
                    aria-label={`Remove ${card.bank} reward rate`}
                    title="Remove rate"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: 10, alignItems: "end" }}>
            <div>
              <label className="form-label">Bank Name</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. AXIS"
                value={newBank}
                onChange={(e) => setNewBank(e.target.value)}
              />
            </div>
            <div>
              <label className="form-label">Reward Rate (%)</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. 2.5"
                value={newRate}
                onChange={(e) => setNewRate(e.target.value)}
              />
            </div>
            <button className="btn btn-primary" onClick={handleAddCard}>
              <Plus size={14} />
              Add
            </button>
          </div>
        </div>

        {/* Proxy Settings */}
        <div className="glass-card module-card">
          <h3 style={{ margin: "0 0 4px", fontSize: 15, fontWeight: 600 }}>Proxy Configuration</h3>
          <p style={{ fontSize: 12, color: "hsl(var(--text-secondary))", marginBottom: 18 }}>
            Configure residential proxies to bypass geo-blocks and prevent search tracking.
          </p>

          <div className="flex-col gap-md" style={{ marginBottom: 20 }}>
            <div>
              <label className="form-label">Provider</label>
              <select className="form-input">
                <option>BrightData (Residential)</option>
                <option>Oxylabs (Residential)</option>
                <option>Smartproxy</option>
                <option>Custom SOCKS5</option>
              </select>
            </div>
            <div>
              <label className="form-label">Session Rotation</label>
              <select className="form-input">
                <option>Rotate IP per platform (Recommended)</option>
                <option>Sticky session (5 min persistence)</option>
              </select>
            </div>
          </div>

          <button className="btn btn-secondary" style={{ width: "100%" }}>
            Test Proxy Connection
          </button>
        </div>

        {/* Scraper Preferences */}
        <div className="glass-card module-card" style={{ marginTop: 20 }}>
          <h3 style={{ margin: "0 0 4px", fontSize: 15, fontWeight: 600 }}>Scraper Preferences</h3>
          <p style={{ fontSize: 12, color: "hsl(var(--text-secondary))", marginBottom: 18 }}>
            Configure scraper running visibility and concurrency constraints.
          </p>

          <div className="flex-col gap-md" style={{ marginBottom: 10 }}>
            <div className="flex-row" style={{ justifyContent: "space-between", alignItems: "center" }}>
              <label htmlFor="showBrowser" className="form-label" style={{ margin: 0, cursor: "pointer", fontSize: 13, fontWeight: 500, color: "hsl(var(--text-primary))" }}>
                Show Browser during search
              </label>
              <label className="switch">
                <input
                  type="checkbox"
                  id="showBrowser"
                  checked={cloak.showBrowser || false}
                  onChange={(e) => updateCloak({ showBrowser: e.target.checked })}
                />
                <span className="slider"></span>
              </label>
            </div>
            <p style={{ fontSize: 11, color: "hsl(var(--text-muted))", marginTop: 4, paddingLeft: 24, lineHeight: 1.4 }}>
              If checked, the scraper browser window will be displayed on your screen, allowing you to watch the agent fill forms and brute-force coupons in real-time.
            </p>
          </div>
        </div>
      </div>

      {/* API Key Rotation Pool & Cooldown Monitor */}
      <div className="glass-card module-card" style={{ marginTop: 24 }}>
        <div className="flex-row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <div>
            <h3 style={{ margin: "0 0 4px", fontSize: 15, fontWeight: 600 }}>API Rotation Pool & Limits</h3>
            <p style={{ fontSize: 12, color: "hsl(var(--text-secondary))", margin: 0 }}>
              Centralized Gemini/OpenAI key rotation. Load-balances brute-force actions on Flash models and thinking actions on Pro models.
            </p>
          </div>
          <div className="flex-row gap-sm">
            <span style={{ background: "rgba(16, 185, 129, 0.1)", color: "hsl(var(--color-success))", fontWeight: 600, fontSize: 11, padding: "4px 8px", borderRadius: 4 }}>
              {apiKeys.filter(k => k.status === "ACTIVE").length} Active
            </span>
            <span style={{ background: "rgba(239, 68, 68, 0.1)", color: "hsl(var(--color-danger))", fontWeight: 600, fontSize: 11, padding: "4px 8px", borderRadius: 4 }}>
              {apiKeys.filter(k => k.status === "EXHAUSTED").length} Cooldown
            </span>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12 }}>
          {apiKeys.map((key) => {
            const isExhausted = key.status === "EXHAUSTED";
            const timeRemaining = isExhausted && key.exhausted_until 
              ? Math.max(0, Math.ceil((new Date(key.exhausted_until).getTime() - currentTime) / 1000))
              : 0;

            return (
              <div
                key={key.index}
                style={{
                  background: "hsl(var(--bg-primary))",
                  border: "1px solid " + (isExhausted ? "rgba(239, 68, 68, 0.3)" : "hsl(var(--card-border))"),
                  borderRadius: "var(--border-radius)",
                  padding: 12,
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                  position: "relative"
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 12, fontWeight: 700, fontFamily: "var(--font-mono)", color: isExhausted ? "hsl(var(--text-secondary))" : "hsl(var(--text-primary))" }}>
                    #{key.index + 1}: {key.masked}
                  </span>
                  <span
                    style={{
                      fontSize: 10,
                      fontWeight: 700,
                      padding: "2px 6px",
                      borderRadius: 4,
                      background: isExhausted ? "rgba(239, 68, 68, 0.1)" : "rgba(16, 185, 129, 0.1)",
                      color: isExhausted ? "hsl(var(--color-danger))" : "hsl(var(--color-success))"
                    }}
                  >
                    {isExhausted ? `COOLING (${timeRemaining}s)` : "READY"}
                  </span>
                </div>

                <div style={{ display: "flex", gap: 12, fontSize: 11, color: "hsl(var(--text-secondary))" }}>
                  <div>
                    Uses: <strong style={{ color: "hsl(var(--text-primary))" }}>{key.use_count}</strong>
                  </div>
                  <div>
                    Limits Hit: <strong style={{ color: key.failed_count > 0 ? "hsl(var(--color-danger))" : "hsl(var(--text-primary))" }}>{key.failed_count}</strong>
                  </div>
                </div>

                {key.last_used && (
                  <div style={{ fontSize: 10, color: "hsl(var(--text-muted))", borderTop: "1px solid hsl(var(--card-border))", paddingTop: 4 }}>
                    Last Active: {new Date(key.last_used).toLocaleTimeString()}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

import { useState, useEffect } from "react";
import { TrendingDown, TrendingUp, Activity, Calendar, MapPin, Clock, Sun } from "lucide-react";
import {
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Area, AreaChart
} from "recharts";
import { useResultStore, useSearchStore } from "../store";

interface PriceHistoryProps {
  sendMessage: (type: string, payload: any) => void;
}

const MOCK_HISTORY = [
  { name: "05-15", price: 5600 },
  { name: "05-20", price: 5400 },
  { name: "05-25", price: 5800 },
  { name: "05-30", price: 5200 },
  { name: "06-05", price: 5000 },
  { name: "06-10", price: 5100 },
  { name: "Today", price: 4700 },
];

export default function PriceHistory({ sendMessage }: PriceHistoryProps) {
  const historyData = useResultStore((s) => s.historyData);
  const prediction = useResultStore((s) => s.prediction);
  const trip = useSearchStore((s) => s.trip);

  const [historyRoute, setHistoryRoute] = useState("DEL-BOM");

  const fetchHistory = (route: string) => {
    if (!route.trim()) return;
    const formatted = route.trim().toUpperCase();
    sendMessage("history:get", { route: formatted, days: 30 });
    const dateStr = trip.departureDate || new Date().toISOString().split("T")[0];
    sendMessage("predict:get", { route: formatted, date: dateStr });
  };

  useEffect(() => {
    fetchHistory(historyRoute);
  }, []);

  const chartData = historyData.length > 0
    ? historyData.map((d: any) => ({
        name: d.recorded_at ? d.recorded_at.split("T")[0].slice(5) : (d.departure_date || "").slice(5),
        price: d.price,
      })).filter((d) => d.price > 0)
    : MOCK_HISTORY;

  // Stats
  const prices = chartData.map((d) => d.price);
  const lowestPrice = prices.length > 0 ? Math.min(...prices) : 4700;
  const avgPrice = prices.length > 0 ? Math.round(prices.reduce((a, b) => a + b, 0) / prices.length) : 5180;

  const volatility = (() => {
    if (prices.length < 2) return { text: "Low", pct: 0, color: "hsl(var(--color-success))" };
    const diffs = prices.map((p) => Math.abs(p - avgPrice));
    const avgDiff = diffs.reduce((a, b) => a + b, 0) / diffs.length;
    const pct = Math.round((avgDiff / avgPrice) * 100);
    if (pct > 15) return { text: "High", pct, color: "hsl(var(--color-error))" };
    if (pct > 5) return { text: "Medium", pct, color: "hsl(var(--color-warning))" };
    return { text: "Low", pct, color: "hsl(var(--color-success))" };
  })();

  // Prediction
  const pred = prediction || {
    decision: { signal: "BOOK_NOW", confidence: 0.80 },
    forecast: { direction: "FALLING" },
    risk_flags: ["ℹ️ Route price history stable."],
    price_context: { vs_90d_average: -11.4 },
  };

  const signal = pred.decision?.signal || pred.prediction || "BUY_NOW";
  const confidence = pred.decision?.confidence ? Math.round(pred.decision.confidence * 100) : (pred.confidence ? Math.round(pred.confidence * 100) : 80);
  const reasoning = pred.decision?.reasoning || pred.reasoning || "Current price appears favorable.";
  const nearbyAdvice = pred.optimal_booking_strategy?.best_day_to_book || pred.nearbyDatesAdvice || "Tuesday or Wednesday bookings are typically 8-15% cheaper.";

  const signalColor = signal.includes("BUY") || signal.includes("BOOK")
    ? "hsl(var(--color-success))"
    : signal === "WAIT" ? "hsl(var(--color-warning))" : "hsl(var(--color-primary))";

  const seasonality = pred.price_context?.price_bracket || "TYPICAL";
  const fuelTrend = pred.forecast?.direction || "STABLE";

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Price Intelligence</h1>
        <p className="page-subtitle">Monitor historical price trends and AI-powered booking recommendations.</p>
      </div>

      {/* Chart Card */}
      <div className="glass-card module-card" style={{ marginBottom: 20 }}>
        <div className="flex-row gap-md" style={{ marginBottom: 18 }}>
          <div style={{ width: 150 }}>
            <label className="form-label">Route</label>
            <input
              type="text"
              className="form-input"
              value={historyRoute}
              onChange={(e) => setHistoryRoute(e.target.value)}
              placeholder="e.g. DEL-GOI"
            />
          </div>
          <button
            className="btn btn-secondary"
            style={{ marginTop: 18 }}
            onClick={() => fetchHistory(historyRoute)}
          >
            Refresh
          </button>
        </div>

        <div style={{ height: 280 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#6366f1" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#6366f1" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(228 14% 18%)" opacity={0.4} />
              <XAxis dataKey="name" stroke="hsl(215 15% 45%)" style={{ fontSize: 10 }} />
              <YAxis stroke="hsl(215 15% 45%)" domain={["auto", "auto"]} style={{ fontSize: 10 }} />
              <Tooltip
                formatter={(value: number) => [`₹${value.toLocaleString("en-IN")}`, "Price"]}
                contentStyle={{ background: "hsl(228 18% 10%)", border: "1px solid hsl(228 14% 18%)", borderRadius: 6, color: "hsl(210 40% 98%)", fontSize: 11 }}
              />
              <Area type="monotone" dataKey="price" stroke="#6366f1" strokeWidth={2} fill="url(#priceGrad)" dot={{ r: 3, fill: "#6366f1" }} activeDot={{ r: 5, fill: "#818cf8" }} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* AI Savings Optimizer — Flight Alternatives */}
      {pred && pred.smart_suggestions && pred.smart_suggestions.length > 0 && (
        <div style={{ marginBottom: 25 }}>
          <div className="flex-row gap-sm" style={{ alignItems: "center", marginBottom: 12 }}>
            <Activity size={18} style={{ color: "hsl(var(--color-primary))" }} />
            <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: "hsl(var(--text-primary))" }}>
              AI Savings Optimizer — Flight Alternatives
            </h3>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16 }}>
            {pred.smart_suggestions.map((alt: any, idx: number) => {
              let IconComponent = Clock;
              let iconColor = "hsl(var(--color-primary))";
              if (alt.type === "DATE_SHIFT") {
                IconComponent = Calendar;
                iconColor = "hsl(var(--color-success))";
              } else if (alt.type === "AIRPORT_ALT") {
                IconComponent = MapPin;
                iconColor = "hsl(var(--color-warning))";
              } else if (alt.type === "TIME_SHIFT") {
                IconComponent = Sun;
                iconColor = "#38bdf8"; // Light Blue/Sky
              }

              return (
                <div key={idx} className="glass-card module-card" style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", padding: 16, margin: 0 }}>
                  <div>
                    <div className="flex-row gap-xs" style={{ alignItems: "center", marginBottom: 10 }}>
                      <IconComponent size={14} style={{ color: iconColor }} />
                      <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "hsl(var(--text-muted))" }}>
                        {alt.type.replace("_", " ")}
                      </span>
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "hsl(var(--text-primary))", marginBottom: 4, lineHeight: 1.3 }}>
                      {alt.title}
                    </div>
                    <p style={{ margin: 0, fontSize: 11, color: "hsl(var(--text-secondary))", lineHeight: 1.4 }}>
                      {alt.detail}
                    </p>
                  </div>
                  <div style={{ marginTop: 12, paddingTop: 8, borderTop: "1px dashed hsl(var(--card-border))", display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                    <span style={{ fontSize: 10, color: "hsl(var(--text-muted))" }}>Net Savings</span>
                    <span style={{ fontSize: 14, fontWeight: 700, color: "hsl(var(--color-success))" }}>
                      ₹{(alt.net_saving || alt.saving).toLocaleString("en-IN")}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="grid-2-1">
        {/* Route Insights */}
        <div className="glass-card module-card">
          <h4 style={{ margin: "0 0 14px", fontSize: 14, fontWeight: 600 }}>Route Insights & Macro Factors</h4>
          <div className="flex-col gap-md" style={{ fontSize: 13 }}>
            <div className="flex-row" style={{ justifyContent: "space-between" }}>
              <span style={{ color: "hsl(var(--text-secondary))" }}>30-Day Lowest</span>
              <span style={{ color: "hsl(var(--color-success))", fontWeight: 600 }}>₹{lowestPrice.toLocaleString("en-IN")}</span>
            </div>
            <div className="flex-row" style={{ justifyContent: "space-between" }}>
              <span style={{ color: "hsl(var(--text-secondary))" }}>30-Day Average</span>
              <span>₹{avgPrice.toLocaleString("en-IN")}</span>
            </div>
            <div className="flex-row" style={{ justifyContent: "space-between" }}>
              <span style={{ color: "hsl(var(--text-secondary))" }}>Volatility</span>
              <span style={{ color: volatility.color, fontWeight: 600 }}>{volatility.text} ({volatility.pct}%)</span>
            </div>
            <div className="divider" />
            <div className="flex-row" style={{ justifyContent: "space-between" }}>
              <span style={{ color: "hsl(var(--text-secondary))" }}>Price Bracket</span>
              <span className={`badge ${seasonality === "LOW" ? "badge-success" : seasonality === "HIGH" ? "badge-error" : "badge-primary"}`}>
                {seasonality}
              </span>
            </div>
            <div className="flex-row" style={{ justifyContent: "space-between" }}>
              <span style={{ color: "hsl(var(--text-secondary))" }}>Trend Direction</span>
              <span style={{ color: fuelTrend === "RISING" ? "hsl(var(--color-error))" : fuelTrend === "FALLING" ? "hsl(var(--color-success))" : "hsl(var(--text-muted))", fontWeight: 600 }}>
                {fuelTrend}
              </span>
            </div>
          </div>
        </div>

        {/* AI Signal */}
        <div className="glass-card module-card" style={{ display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          <div>
            <h4 style={{ margin: "0 0 12px", fontSize: 14, fontWeight: 600 }}>AI Buy Signal</h4>
            <div className="flex-row gap-md" style={{ alignItems: "flex-start", marginBottom: 14 }}>
              <div style={{ marginTop: 2 }}>
                {signal === "WAIT" ? (
                  <TrendingUp size={26} color="hsl(var(--color-warning))" />
                ) : signal.includes("BUY") || signal.includes("BOOK") ? (
                  <TrendingDown size={26} color="hsl(var(--color-success))" />
                ) : (
                  <Activity size={26} color="hsl(var(--color-primary))" />
                )}
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 15, color: signalColor }}>
                  {signal.replace("_", " ")} — {confidence}% Confidence
                </div>
                <p style={{ margin: "4px 0 0", fontSize: 12, color: "hsl(var(--text-secondary))", lineHeight: 1.5 }}>
                  {reasoning}
                </p>
              </div>
            </div>
          </div>

          <div style={{ borderTop: "1px solid hsl(var(--card-border))", paddingTop: 12, marginTop: 8 }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: "hsl(var(--color-primary))", textTransform: "uppercase", marginBottom: 6, letterSpacing: "0.08em" }}>
              Date Shifting Advice
            </div>
            <div style={{ fontSize: 12, color: "hsl(var(--text-primary))", lineHeight: 1.5 }}>
              {nearbyAdvice}
            </div>

            {/* Risk Flags */}
            {pred.risk_flags?.length > 0 && (
              <div style={{ marginTop: 12 }}>
                {pred.risk_flags.slice(0, 3).map((flag: string, i: number) => (
                  <div key={i} style={{
                    fontSize: 11,
                    color: flag.startsWith("⚠️") ? "hsl(var(--color-warning))" : "hsl(var(--text-secondary))",
                    marginBottom: 4,
                    lineHeight: 1.4,
                  }}>
                    {flag}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

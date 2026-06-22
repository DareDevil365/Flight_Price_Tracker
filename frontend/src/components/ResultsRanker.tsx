import { useState } from "react";
import {
  CheckCircle2, Tag, ChevronRight, Activity, Calendar, MapPin, Clock, Sun, Brain
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell
} from "recharts";
import { useResultStore, useSearchStore } from "../store";
import type { SearchResult } from "../types";

interface ResultsRankerProps {
  sendMessage: (type: string, payload: any) => void;
}

export default function ResultsRanker({ sendMessage }: ResultsRankerProps) {
  const results = useResultStore((s) => s.results);
  const handoffStatus = useResultStore((s) => s.handoffStatus);
  const setHandoffStatus = useResultStore((s) => s.setHandoffStatus);
  const prediction = useResultStore((s) => s.prediction);
  const suggestions = useResultStore((s) => s.suggestions);
  const dateAlternatives = useResultStore((s) => s.dateAlternatives);
  const highlightedFlightId = useResultStore((s) => s.highlightedFlightId);
  const setHighlightedFlightId = useResultStore((s) => s.setHighlightedFlightId);
  const updateTrip = useSearchStore((s) => s.updateTrip);
  const setActiveTab = useSearchStore((s) => s.setActiveTab);
  const searchStatus = useSearchStore((s) => s.status);

  // Combine suggestions from store or fall back to legacy prediction-based suggestions
  const activeSuggestions = suggestions ? {
    suggestions: suggestions.suggestions || [],
    timing_advice: {
      advice: suggestions.verdict || "MONITOR",
      text: suggestions.advice || "Hold or monitor prices."
    }
  } : (prediction ? {
    suggestions: prediction.smart_suggestions || [],
    timing_advice: {
      advice: prediction.decision?.signal || prediction.prediction || "MONITOR",
      text: prediction.decision?.reasoning || prediction.reasoning || "Hold or monitor prices."
    }
  } : null);


  const [selectedResult, setSelectedResult] = useState<SearchResult | null>(null);
  const [activeSuggestionId, setActiveSuggestionId] = useState<number | null>(null);

  const comboSuggestion = activeSuggestions?.suggestions?.find((s: any) => s.type === "COMBO");
  const filteredSuggestions = activeSuggestions?.suggestions?.filter((s: any) => s.type !== "COMBO") || [];

  const handleHandoff = (sessionId: string) => {
    setHandoffStatus(sessionId, "pending");
    sendMessage("session:handoff", { sessionId });
    if (activeSuggestionId) {
      sendMessage("suggestion:accept", { suggestionId: activeSuggestionId });
      setActiveSuggestionId(null);
    }
  };

  const getSignalInfo = () => {
    const p = prediction;
    if (!p) return { signal: "BUY_NOW", confidence: 80, reasoning: "Current price appears favorable based on historical trends.", color: "hsl(var(--color-success))" };
    const sig = p.decision?.signal || p.prediction || "BUY_NOW";
    const conf = p.decision?.confidence ? Math.round(p.decision.confidence * 100) : (p.confidence ? Math.round(p.confidence * 100) : 80);
    const reason = p.decision?.reasoning || p.reasoning || "Analysis complete.";
    const color = sig === "BOOK_NOW" || sig === "BUY_NOW" ? "hsl(var(--color-success))" : sig === "WAIT" ? "hsl(var(--color-warning))" : "hsl(var(--color-primary))";
    return { signal: sig, confidence: conf, reasoning: reason, color };
  };

  const signalInfo = getSignalInfo();

  if (results.length === 0) {
    return (
      <div className="page-container">
        <div className="page-header">
          <h1 className="page-title">Verified Flight Results</h1>
          <p className="page-subtitle">True Cost comparison: final verified checkout price including convenience fees, coupons, and payment rewards.</p>
        </div>
        {searchStatus === "running" ? (
          <div className="grid-2-1 animate-fade-in">
            <div className="flex-col gap-md">
              {/* Shimmer Skeletons for flight cards */}
              {[1, 2, 3].map((i) => (
                <div key={i} className="skeleton-card">
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div className="glass-skeleton skeleton-title" style={{ width: "30%", height: 18 }}></div>
                    <div className="glass-skeleton" style={{ width: "15%", height: 16 }}></div>
                  </div>
                  <div className="glass-skeleton skeleton-subtitle" style={{ width: "60%", height: 12, marginTop: 10 }}></div>
                  <div className="divider-dashed" style={{ margin: "14px 0 10px" }} />
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div className="glass-skeleton" style={{ width: "45%", height: 12 }}></div>
                    <div className="glass-skeleton" style={{ width: "20%", height: 12 }}></div>
                  </div>
                </div>
              ))}
            </div>
            <div className="flex-col gap-md">
              {/* Shimmer Skeleton for details/matrix */}
              <div className="skeleton-card" style={{ height: 380, display: "flex", flexDirection: "column" }}>
                <div className="glass-skeleton skeleton-title" style={{ width: "50%", height: 18 }}></div>
                <div className="glass-skeleton skeleton-subtitle" style={{ width: "80%", height: 12, marginTop: 10, marginBottom: 24 }}></div>
                <div style={{ flex: 1, display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 12, paddingBottom: 10 }}>
                  {[60, 40, 80, 50, 90, 70].map((h, idx) => (
                    <div key={idx} className="glass-skeleton" style={{ width: "14%", height: `${h}%`, borderRadius: "4px 4px 0 0" }}></div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="glass-card empty-state">
            <Activity size={36} className="empty-state-icon" />
            <div className="empty-state-title">No Verified Results</div>
            <div className="empty-state-desc">Run a flight search from the Cockpit tab to dispatch agents and collect savings.</div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Verified Flight Results</h1>
        <p className="page-subtitle">True Cost comparison: final verified checkout price including convenience fees, coupons, and payment rewards.</p>
      </div>

      <div className="grid-2-1">
        {/* LEFT — Results List */}
        <div className="flex-col gap-md stagger">
          {/* AI Signal Banner */}
          <div className={`glass-card module-card ${signalInfo.signal.includes("BUY") || signalInfo.signal.includes("BOOK") ? "signal-buy" : signalInfo.signal === "WAIT" ? "signal-wait" : "signal-monitor"}`}>
            <div className="flex-row" style={{ justifyContent: "space-between" }}>
              <div className="flex-row gap-sm">
                <CheckCircle2 size={16} style={{ color: signalInfo.color }} />
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>AI Price Advisor</div>
                  <div style={{ fontSize: 10, color: "hsl(var(--text-muted))" }}>Ensemble Model Output</div>
                </div>
              </div>
              <span className={`badge ${signalInfo.signal.includes("BUY") || signalInfo.signal.includes("BOOK") ? "badge-success" : signalInfo.signal === "WAIT" ? "badge-warning" : "badge-primary"}`}>
                {signalInfo.signal.replace("_", " ")} • {signalInfo.confidence}%
              </span>
            </div>
            <p style={{ fontSize: 12, color: "hsl(var(--text-secondary))", marginTop: 8, lineHeight: 1.5 }}>
              {signalInfo.reasoning}
            </p>
          </div>

          {/* Flight Cards */}
          {results.map((result) => {
            const isSelected = selectedResult?.id === result.id;
            const dealText = result.deal_score >= 85 ? "EXCEPTIONAL" : result.deal_score >= 70 ? "GOOD" : "AVERAGE";
            const dealClass = result.deal_score >= 85 ? "exceptional" : result.deal_score >= 70 ? "good" : "average";

            return (
              <div
                key={result.id}
                id={"flight-card-" + result.id}
                className={`glass-card module-card interactive ${isSelected ? "selected" : ""} ${result.id === highlightedFlightId ? "highlighted-pulse" : ""}`}
                onClick={() => {
                  setSelectedResult(result);
                  setHighlightedFlightId(null);
                }}
              >
                <div className="flex-row" style={{ justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                  <div>
                    <span className="badge badge-neutral" style={{ marginBottom: 6, display: "inline-block" }}>
                      {result.platform.toUpperCase()}
                    </span>
                    <h3 style={{ margin: "4px 0 2px", fontSize: 15, fontWeight: 600 }}>
                      {result.airline} {result.flight_number} {result.departure_date && <span style={{ fontSize: 11, color: "hsl(var(--text-muted))", fontWeight: 400, marginLeft: 8 }}>({result.departure_date})</span>}
                    </h3>
                    <span style={{ fontSize: 11, color: "hsl(var(--text-muted))" }}>
                      {result.departure_time} – {result.arrival_time} • {result.duration} ({result.stops === 0 ? "Direct" : `${result.stops} Stop`})
                    </span>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div className={`deal-score ${dealClass}`} style={{ marginBottom: 4 }}>
                      {result.deal_score}/100 ({dealText})
                    </div>
                    <div className="price-original">
                      ₹{result.base_price.toLocaleString("en-IN")}
                    </div>
                    <div className="price-final">
                      ₹{result.effective_price.toLocaleString("en-IN")}
                    </div>
                  </div>
                </div>

                <div className="divider-dashed" style={{ margin: "0 0 10px" }} />

                <div className="flex-row" style={{ justifyContent: "space-between", fontSize: 12 }}>
                  <span className="flex-row gap-sm" style={{ color: "hsl(var(--text-secondary))" }}>
                    <Tag size={12} style={{ color: "hsl(var(--text-muted))" }} />
                    Coupon: {result.best_coupon_code || "None"}
                  </span>
                  <span className="price-savings">
                    Saved ₹{((result.savings || 0) + (result.savings_breakdown?.total_stacking_savings || 0)).toLocaleString("en-IN")}
                  </span>
                </div>
              </div>
            );
          })}

          {/* Comparison Table */}
          <div className="glass-card module-card">
            <span className="form-label" style={{ marginBottom: 10 }}>Competitor Matrix</span>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Platform</th>
                  <th>Base</th>
                  <th>Coupon</th>
                  <th>Checkout</th>
                  <th>True Cost</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r) => (
                  <tr key={r.id}>
                    <td style={{ fontWeight: 600 }}>{r.platform.toUpperCase()}</td>
                    <td>₹{r.base_price.toLocaleString("en-IN")}</td>
                    <td style={{ color: "hsl(var(--color-success))", fontWeight: 500 }}>{r.best_coupon_code || "—"}</td>
                    <td>₹{r.final_price.toLocaleString("en-IN")}</td>
                    <td style={{ color: "hsl(var(--color-success))", fontWeight: 600 }}>₹{r.effective_price.toLocaleString("en-IN")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* How to Save More (Stacked Strategy Card) */}
          {comboSuggestion && (
            <div className="glass-card module-card combo-savings-card" style={{
              background: "linear-gradient(135deg, hsl(var(--color-primary-dark) / 0.2) 0%, hsl(var(--color-success-dark) / 0.1) 100%)",
              border: "1px solid hsl(var(--color-success) / 0.3)",
              padding: 16,
              borderRadius: "var(--border-radius)",
              position: "relative",
              overflow: "hidden",
              cursor: "pointer"
            }}
            onClick={() => {
              if (comboSuggestion.id) {
                sendMessage("suggestion:click", { suggestionId: comboSuggestion.id });
                sendMessage("suggestion:accept", { suggestionId: comboSuggestion.id });
              }
              alert("Stacked savings strategy activated! Follow the step-by-step breakdown below.");
            }}>
              <div style={{
                position: "absolute",
                top: -50,
                right: -50,
                width: 120,
                height: 120,
                background: "hsl(var(--color-success) / 0.15)",
                filter: "blur(40px)",
                borderRadius: "50%",
                pointerEvents: "none"
              }} />

              <div className="flex-row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <div className="flex-row gap-sm" style={{ alignItems: "center" }}>
                  <Brain size={18} style={{ color: "hsl(var(--color-success))" }} />
                  <h3 style={{ margin: 0, fontSize: 13, fontWeight: 700, color: "hsl(var(--text-primary))", letterSpacing: "0.02em" }}>
                    How to Save More (Stacked Strategy)
                  </h3>
                </div>
                <span className="badge badge-success" style={{ padding: "4px 8px", fontSize: 9 }}>
                  RECOMMENDED
                </span>
              </div>

              <div className="flex-col gap-sm">
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 6 }}>
                  {(() => {
                    const match = comboSuggestion.detail.match(/combining steps: (.*?)\./);
                    const steps = match ? match[1].split(" + ") : [comboSuggestion.title];
                    return steps.map((step: string, idx: number) => (
                      <span key={idx} style={{
                        fontSize: 9,
                        fontWeight: 600,
                        padding: "3px 6px",
                        background: "hsl(var(--bg-primary) / 0.7)",
                        border: "1px solid hsl(var(--card-border))",
                        borderRadius: 4,
                        color: "hsl(var(--text-primary))"
                      }}>
                        {step}
                      </span>
                    ));
                  })()}
                </div>

                <div className="flex-row" style={{ justifyContent: "space-between", alignItems: "flex-end" }}>
                  <div style={{ flex: 1, marginRight: 16 }}>
                    <p style={{ margin: 0, fontSize: 11, color: "hsl(var(--text-secondary))", lineHeight: 1.4 }}>
                      {comboSuggestion.detail}
                    </p>
                  </div>
                  <div style={{ textAlign: "right", minWidth: 100 }}>
                    <span style={{ fontSize: 8, color: "hsl(var(--text-muted))", display: "block", textTransform: "uppercase" }}>Stacked Savings</span>
                    <span style={{ fontSize: 16, fontWeight: 800, color: "hsl(var(--color-success))" }}>
                      ₹{comboSuggestion.net_saving.toLocaleString("en-IN")}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Smart Travel Advice Card */}
          {activeSuggestions && (
            <div className="glass-card module-card" style={{ marginTop: 0 }}>
              <div className="flex-row gap-sm" style={{ alignItems: "center", marginBottom: 12 }}>
                <Activity size={18} style={{ color: "hsl(var(--color-primary))" }} />
                <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: "hsl(var(--text-primary))" }}>
                  Smart Travel Advice
                </h3>
              </div>
              
              <div className="flex-col gap-md">
                {/* Timing Advice */}
                {activeSuggestions.timing_advice && (
                  <div style={{
                    padding: 12,
                    borderRadius: "var(--border-radius)",
                    background: "hsl(var(--bg-secondary))",
                    border: "1px solid hsl(var(--card-border))"
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
                      <span style={{ fontSize: 10, fontWeight: 600, color: "hsl(var(--text-muted))" }}>TIMING VERDICT</span>
                      <span className={`badge ${
                        activeSuggestions.timing_advice.advice.includes("BOOK") || activeSuggestions.timing_advice.advice.includes("BUY")
                          ? "badge-success" 
                          : activeSuggestions.timing_advice.advice === "WAIT"
                          ? "badge-warning"
                          : "badge-primary"
                      }`}>
                        {activeSuggestions.timing_advice.advice.replace("_", " ")}
                      </span>
                    </div>
                    <p style={{ margin: "0 0 8px 0", fontSize: 11, color: "hsl(var(--text-secondary))", lineHeight: 1.4 }}>
                      {activeSuggestions.timing_advice.text}
                    </p>
                    
                    {/* Confidence Meter */}
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
                      <span style={{ fontSize: 9, color: "hsl(var(--text-muted))", fontWeight: 500 }}>CONFIDENCE</span>
                      <div style={{ flex: 1, height: 4, background: "hsl(var(--bg-elevated))", borderRadius: 2, overflow: "hidden" }}>
                        <div style={{ height: "100%", width: `${signalInfo.confidence}%`, background: signalInfo.color }} />
                      </div>
                      <span style={{ fontSize: 9, fontWeight: 600, color: signalInfo.color }}>{signalInfo.confidence}%</span>
                    </div>
                  </div>
                )}

                {/* Specific Advice Items */}
                {filteredSuggestions && filteredSuggestions.map((alt: any, idx: number) => {
                  let IconComponent = Clock;
                  let iconColor = "hsl(var(--color-primary))";
                  let categoryName = "Alternative Strategy";
                  
                  if (alt.type === "DATE_SHIFT") {
                    IconComponent = Calendar;
                    iconColor = "hsl(var(--color-success))";
                    categoryName = "Date Flexibility";
                  } else if (alt.type === "AIRPORT_ALT") {
                    IconComponent = MapPin;
                    iconColor = "hsl(var(--color-warning))";
                    categoryName = "Airport Alternative";
                  } else if (alt.type === "LAYOVER") {
                    IconComponent = Clock;
                    iconColor = "#a855f7";
                    categoryName = "Stops & Layovers";
                  } else if (alt.type === "TIME_SHIFT") {
                    IconComponent = Sun;
                    iconColor = "#38bdf8";
                    categoryName = "Timing Shift";
                  } else if (alt.type === "CASHBACK") {
                    IconComponent = Tag;
                    iconColor = "hsl(var(--color-success))";
                    categoryName = "Payment Offer";
                  }

                  const savingsValue = alt.net_saving !== undefined ? alt.net_saving : alt.saving;

                  return (
                    <div 
                      key={idx} 
                      style={{
                        display: "flex",
                        flexDirection: "row",
                        justifyContent: "space-between",
                        alignItems: "flex-start",
                        background: "hsl(var(--bg-secondary))",
                        padding: 12,
                        borderRadius: "var(--border-radius)",
                        border: "1px solid hsl(var(--card-border))",
                        gap: 12,
                        cursor: (alt.type === "LAYOVER" || alt.type === "TIME_SHIFT" || alt.type === "DATE_SHIFT") ? "pointer" : "default"
                      }}
                      onClick={() => {
                        if (alt.id) {
                          sendMessage("suggestion:click", { suggestionId: alt.id });
                          setActiveSuggestionId(alt.id);
                        }
                        
                        if ((alt.type === "LAYOVER" || alt.type === "TIME_SHIFT" || alt.type === "DATE_SHIFT") && alt.flight_id) {
                          const matchingFlight = results.find(r => r.id === alt.flight_id);
                          if (matchingFlight) {
                            setSelectedResult(matchingFlight);
                            setHighlightedFlightId(alt.flight_id);
                            setTimeout(() => {
                              const el = document.getElementById("flight-card-" + alt.flight_id);
                              if (el) {
                                el.scrollIntoView({ behavior: "smooth", block: "center" });
                              }
                            }, 50);
                            return;
                          }
                        }
                        
                        if (alt.type === "DATE_SHIFT" && alt.date) {
                          if (alt.id) {
                            sendMessage("suggestion:accept", { suggestionId: alt.id });
                          }
                          updateTrip({ departureDate: alt.date });
                          setActiveTab("search");
                        }
                      }}
                    >
                      <div style={{ display: "flex", padding: 6, borderRadius: 6, background: "hsl(var(--bg-tertiary))", marginTop: 2 }}>
                        <IconComponent size={16} style={{ color: iconColor }} />
                      </div>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 3 }}>
                          <div>
                            <span style={{ fontSize: 9, fontWeight: 600, color: "hsl(var(--text-muted))", display: "block", textTransform: "uppercase" }}>
                              {categoryName}
                            </span>
                            <span style={{ fontSize: 13, fontWeight: 600 }}>{alt.title}</span>
                          </div>
                          {savingsValue > 0 && (
                            <span style={{ fontSize: 13, fontWeight: 700, color: "hsl(var(--color-success))", whiteSpace: "nowrap", marginLeft: 8 }}>
                              Save ₹{savingsValue.toLocaleString("en-IN")}
                            </span>
                          )}
                        </div>
                        <p style={{ margin: 0, fontSize: 11, color: "hsl(var(--text-secondary))", lineHeight: 1.4 }}>
                          {alt.detail}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Nearby Dates Price Comparison Matrix */}
          {dateAlternatives && dateAlternatives.length > 0 && (
            <div className="glass-card module-card" style={{ marginTop: 0 }}>
              <div className="flex-row gap-sm" style={{ alignItems: "center", marginBottom: 12 }}>
                <Calendar size={18} style={{ color: "hsl(var(--color-success))" }} />
                <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: "hsl(var(--text-primary))" }}>
                  Nearby Dates Price Comparison
                </h3>
              </div>
              <div style={{ display: "flex", gap: "8px", justifyContent: "space-between", flexWrap: "wrap" }}>
                {dateAlternatives.map((alt: any, idx: number) => {
                  let formattedDate = alt.date;
                  try {
                    const parts = alt.date.split("-");
                    if (parts.length === 3) {
                      const dt = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
                      formattedDate = dt.toLocaleDateString("en-IN", { month: "short", day: "numeric" });
                    }
                  } catch (e) {}

                  return (
                    <div key={idx} style={{
                      textAlign: "center",
                      padding: "10px 8px",
                      background: "hsl(var(--bg-secondary))",
                      borderRadius: "var(--border-radius)",
                      border: "1px solid hsl(var(--card-border))",
                      flex: "1 1 20%",
                      minWidth: 80
                    }}>
                      <div style={{ fontSize: 10, color: "hsl(var(--text-muted))", marginBottom: 4 }}>{formattedDate}</div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "hsl(var(--text-primary))" }}>
                        ₹{alt.price.toLocaleString("en-IN")}
                      </div>
                      {alt.savings > 0 ? (
                        <div style={{ fontSize: 9, color: "hsl(var(--color-success))", fontWeight: 600, marginTop: 2 }}>
                          -₹{alt.savings.toLocaleString("en-IN")}
                        </div>
                      ) : alt.savings < 0 ? (
                        <div style={{ fontSize: 9, color: "hsl(var(--color-error))", fontWeight: 600, marginTop: 2 }}>
                          +₹{Math.abs(alt.savings).toLocaleString("en-IN")}
                        </div>
                      ) : (
                        <div style={{ fontSize: 9, color: "hsl(var(--text-muted))", marginTop: 2 }}>Base</div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* RIGHT — Waterfall */}
        <div className="flex-col gap-md">
          {selectedResult ? (
            <div className="glass-card module-card animate-fade-in">
              <h3 style={{ margin: "0 0 4px", fontSize: 15, fontWeight: 600 }}>Savings Waterfall</h3>
              <p style={{ fontSize: 12, color: "hsl(var(--text-secondary))", marginBottom: 20 }}>
                How the listed price drops through coupon, cashback, and card rewards.
              </p>

              {/* Chart */}
              <div style={{ height: 200, marginBottom: 20 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={[
                      { name: "Base", amount: selectedResult.base_price },
                      { name: "Coupon", amount: -selectedResult.savings },
                      { name: "Fee", amount: selectedResult.savings_breakdown?.convenience_fee || 0 },
                      { name: "Cashback", amount: -(selectedResult.savings_breakdown?.cashback_portal?.amount || 0) },
                      { name: "Card", amount: -(selectedResult.savings_breakdown?.payment_method?.amount || 0) },
                      { name: "Final", amount: selectedResult.effective_price },
                    ]}
                    margin={{ top: 10, right: 10, left: 10, bottom: 5 }}
                  >
                    <XAxis dataKey="name" stroke="hsl(var(--text-muted))" style={{ fontSize: 10 }} />
                    <YAxis stroke="hsl(var(--text-muted))" style={{ fontSize: 10 }} />
                    <Tooltip
                      formatter={(value: number) => [`₹${Math.abs(value).toLocaleString("en-IN")}`]}
                      contentStyle={{ background: "hsl(var(--bg-tertiary))", border: "1px solid hsl(var(--card-border))", borderRadius: 6, color: "hsl(var(--text-primary))", fontSize: 11 }}
                    />
                    <Bar dataKey="amount" radius={[4, 4, 0, 0]}>
                      {["#64748b", "#f87171", "#f59e0b", "#6366f1", "#4f46e5", "#34d399"].map((fill, i) => (
                        <Cell key={i} fill={fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Line Items */}
              <div className="flex-col gap-md" style={{ marginBottom: 20 }}>
                <div className="flex-row" style={{ justifyContent: "space-between", fontSize: 13 }}>
                  <span style={{ color: "hsl(var(--text-secondary))" }}>Base Listed Price</span>
                  <span>₹{selectedResult.base_price.toLocaleString("en-IN")}</span>
                </div>
                {selectedResult.savings > 0 && (
                  <div className="flex-row" style={{ justifyContent: "space-between", fontSize: 13, color: "hsl(var(--color-error))" }}>
                    <span>Coupon ({selectedResult.best_coupon_code})</span>
                    <span>- ₹{selectedResult.savings.toLocaleString("en-IN")}</span>
                  </div>
                )}
                {selectedResult.savings_breakdown?.convenience_fee !== undefined && selectedResult.savings_breakdown.convenience_fee > 0 && (
                  <div className="flex-row" style={{ justifyContent: "space-between", fontSize: 13, color: "hsl(var(--color-warning))" }}>
                    <span>Convenience Fee</span>
                    <span>+ ₹{selectedResult.savings_breakdown.convenience_fee.toLocaleString("en-IN")}</span>
                  </div>
                )}
                {selectedResult.savings_breakdown?.cashback_portal?.amount !== undefined && selectedResult.savings_breakdown.cashback_portal.amount > 0 && (
                  <div className="flex-row" style={{ justifyContent: "space-between", fontSize: 13, color: "hsl(var(--color-primary))" }}>
                    <span>Cashback ({selectedResult.savings_breakdown.cashback_portal.provider})</span>
                    <span>- ₹{selectedResult.savings_breakdown.cashback_portal.amount.toLocaleString("en-IN")}</span>
                  </div>
                )}
                {selectedResult.savings_breakdown?.payment_method?.amount !== undefined && selectedResult.savings_breakdown.payment_method.amount > 0 && (
                  <div className="flex-row" style={{ justifyContent: "space-between", fontSize: 13, color: "hsl(var(--color-primary))" }}>
                    <span>Card Rewards ({selectedResult.savings_breakdown.payment_method.provider})</span>
                    <span>- ₹{selectedResult.savings_breakdown.payment_method.amount.toLocaleString("en-IN")}</span>
                  </div>
                )}
                <div className="divider" />
                <div className="flex-row" style={{ justifyContent: "space-between", fontSize: 15, fontWeight: 700 }}>
                  <span>Effective True Price</span>
                  <span style={{ color: "hsl(var(--color-success))" }}>₹{selectedResult.effective_price.toLocaleString("en-IN")}</span>
                </div>
              </div>

              {/* Claim Guide */}
              {selectedResult.savings_breakdown?.instructions !== undefined && selectedResult.savings_breakdown.instructions.length > 0 && (
                <div style={{ background: "hsl(var(--bg-primary))", padding: 14, borderRadius: "var(--border-radius)", border: "1px solid hsl(var(--card-border))", marginBottom: 20 }}>
                  <span className="form-label" style={{ marginBottom: 8 }}>How to claim this price</span>
                  <div style={{ fontSize: 12, color: "hsl(var(--text-secondary))", lineHeight: 1.6 }}>
                    {selectedResult.savings_breakdown.instructions.map((inst, i) => (
                      <div key={i} style={{ marginBottom: 3 }}>{inst}</div>
                    ))}
                  </div>
                </div>
              )}

              {/* Handoff Button */}
              {handoffStatus[selectedResult.session_id] === "success" ? (
                <div className="badge badge-success" style={{ width: "100%", padding: 14, justifyContent: "center", fontSize: 13 }}>
                  ✓ Browser focused — complete payment in the active window.
                </div>
              ) : (
                <button
                  className="btn btn-primary btn-launch"
                  onClick={() => handleHandoff(selectedResult.session_id)}
                  disabled={handoffStatus[selectedResult.session_id] === "pending"}
                >
                  {handoffStatus[selectedResult.session_id] === "pending"
                    ? "Focusing Browser..."
                    : "Book Now — Open Handoff Session"}
                </button>
              )}
            </div>
          ) : (
            <div className="glass-card empty-state">
              <ChevronRight size={24} style={{ transform: "rotate(90deg)", color: "hsl(var(--text-dim))", marginBottom: 8 }} />
              <div className="empty-state-desc">
                Select a flight option to inspect the Savings Waterfall and activate booking handoff.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

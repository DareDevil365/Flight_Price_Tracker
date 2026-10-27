import { useEffect, useState } from "react";
import {
  Calendar, User, XCircle, AlertCircle, Clock, Plane, ArrowRight, RefreshCw, Tag, ShieldCheck, HelpCircle
} from "lucide-react";
import { useHistoryStore } from "../store";
import type { SearchHistoryItem, SearchResult } from "../types";

interface SearchHistoryProps {
  sendMessage: (type: string, payload: Record<string, unknown>) => void;
}

export default function SearchHistory({ sendMessage }: SearchHistoryProps) {
  const history = useHistoryStore((s) => s.history);
  const searchResultsMap = useHistoryStore((s) => s.searchResults);
  const [selectedSearchId, setSelectedSearchId] = useState<string | null>(null);
  const selectedSearch = history.find(search=>search.id===selectedSearchId) || null;
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    sendMessage("search:history:get", {});
  }, [sendMessage]);

  const handleRefresh = () => {
    setRefreshing(true);
    sendMessage("search:history:get", {});
    if (selectedSearch) {
      sendMessage("search:history:results:get", { searchId: selectedSearch.id });
    }
    setTimeout(() => setRefreshing(false), 800);
  };

  const handleSelectSearch = (search: SearchHistoryItem) => {
    setSelectedSearchId(search.id);
    sendMessage("search:history:results:get", { searchId: search.id });
  };

  const handleHandoff = (sessionId: string) => {
    sendMessage("session:handoff", { sessionId });
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "completed":
        return <span className="badge badge-success">SUCCESS</span>;
      case "failed":
        return <span className="badge badge-error">FAILED</span>;
      case "cancelled":
        return <span className="badge badge-warning">CANCELLED</span>;
      case "running":
        return <span className="badge badge-primary">RUNNING</span>;
      default:
        return <span className="badge badge-neutral">{status.toUpperCase()}</span>;
    }
  };

  const formatDuration = (ms: number | null) => {
    if (ms === null || ms === undefined) return "N/A";
    return `${(ms / 1000).toFixed(1)}s`;
  };

  const formatDate = (dateStr: string | null | undefined) => {
    if (!dateStr) return "N/A";
    try {
      return new Date(dateStr).toLocaleString("en-IN", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit"
      });
    } catch {
      return dateStr;
    }
  };

  const selectedResults: SearchResult[] = selectedSearch ? searchResultsMap[selectedSearch.id] || [] : [];

  return (
    <div className="page-container">
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1 className="page-title">Search & Execution History</h1>
          <p className="page-subtitle">Review recorded flight searches, listed fares and checkout coupon evidence.</p>
        </div>
        <button
          className="btn btn-secondary flex-row gap-xs"
          onClick={handleRefresh}
          disabled={refreshing}
          style={{ height: 38 }}
        >
          <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
          <span>Refresh</span>
        </button>
      </div>

      <div className="grid-2-1" style={{ gridTemplateColumns: "1.2fr 1.8fr" }}>
        {/* LEFT — History List */}
        <div className="flex-col gap-md">
          <span className="form-label">Past Searches</span>
          <div className="flex-col gap-sm" style={{ maxHeight: "calc(100vh - 210px)", overflowY: "auto", paddingRight: 6 }}>
            {history.length === 0 ? (
              <div className="glass-card empty-state" style={{ padding: "30px 20px" }}>
                <Clock size={32} className="text-muted" style={{ marginBottom: 10 }} />
                <div style={{ fontWeight: 600, fontSize: 14 }}>No History Yet</div>
                <div style={{ fontSize: 11, color: "hsl(var(--text-muted))" }}>Searches you run will appear here.</div>
              </div>
            ) : (
              history.map((item) => {
                const isSelected = selectedSearch?.id === item.id;
                return (
                  <div
                    key={item.id}
                    className={`glass-card module-card interactive ${isSelected ? "selected" : ""}`}
                    onClick={() => handleSelectSearch(item)}
                    style={{ padding: "12px 16px", borderLeft: isSelected ? "4px solid hsl(var(--color-primary))" : undefined }}
                  >
                    <div className="flex-row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                      <div className="flex-row gap-xs" style={{ fontWeight: 600, fontSize: 14 }}>
                        <span>{item.origin}</span>
                        <ArrowRight size={12} className="text-muted" />
                        <span>{item.destination}</span>
                      </div>
                      {getStatusBadge(item.status)}
                    </div>
                    <div className="flex-row" style={{ justifyContent: "space-between", fontSize: 11, color: "hsl(var(--text-secondary))" }}>
                      <div className="flex-row gap-sm">
                        <span className="flex-row gap-xs">
                          <Calendar size={10} />
                          {item.departure_date}
                        </span>
                        <span className="flex-row gap-xs">
                          <User size={10} />
                          {item.passenger_count} Pax
                        </span>
                      </div>
                      <span>{formatDuration(item.total_duration_ms)}</span>
                    </div>
                    <div className="divider-dashed" style={{ margin: "8px 0" }} />
                    <div className="flex-row" style={{ justifyContent: "space-between", fontSize: 10, color: "hsl(var(--text-muted))" }}>
                      <span>ID: {item.id.slice(0, 8)}...</span>
                      <span>{formatDate(item.created_at || item.started_at)}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* RIGHT — Search Details & Results */}
        <div className="flex-col gap-md">
          <span className="form-label">Execution Details</span>
          {!selectedSearch ? (
            <div className="glass-card empty-state" style={{ height: "100%", minHeight: 300, display: "flex", justifyContent: "center", alignItems: "center" }}>
              <HelpCircle size={36} className="empty-state-icon" style={{ opacity: 0.5 }} />
              <div className="empty-state-title">No Search Selected</div>
              <div className="empty-state-desc">Select a search log from the list to view the compiled coupon test results and verified deals.</div>
            </div>
          ) : (
            <div className="flex-col gap-md stagger" style={{ maxHeight: "calc(100vh - 210px)", overflowY: "auto", paddingRight: 6 }}>
              {/* Summary Card */}
              <div className="glass-card module-card">
                <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.5, color: "hsl(var(--text-muted))", fontWeight: 600 }}>
                  Search Parameters
                </div>
                <h2 style={{ fontSize: 20, margin: "6px 0", fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
                  <span>{selectedSearch.origin}</span>
                  <Plane size={18} className="text-primary" />
                  <span>{selectedSearch.destination}</span>
                </h2>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px 20px", marginTop: 12, fontSize: 13 }}>
                  <div>
                    <span className="text-muted" style={{ fontSize: 10, display: "block" }}>Departure Date</span>
                    <strong style={{ color: "hsl(var(--text-primary))" }}>{selectedSearch.departure_date}</strong>
                  </div>
                  <div>
                    <span className="text-muted" style={{ fontSize: 10, display: "block" }}>Cabin Class</span>
                    <strong style={{ color: "hsl(var(--text-primary))" }}>{selectedSearch.cabin_class}</strong>
                  </div>
                  <div>
                    <span className="text-muted" style={{ fontSize: 10, display: "block" }}>Passenger Count</span>
                    <strong style={{ color: "hsl(var(--text-primary))" }}>{selectedSearch.passenger_count} Pax</strong>
                  </div>
                  <div>
                    <span className="text-muted" style={{ fontSize: 10, display: "block" }}>Execution Duration</span>
                    <strong style={{ color: "hsl(var(--text-primary))" }}>{formatDuration(selectedSearch.total_duration_ms)}</strong>
                  </div>
                </div>
                <div className="divider" style={{ margin: "14px 0" }} />
                <div className="flex-row" style={{ justifyContent: "space-between", alignItems: "center", fontSize: 12 }}>
                  <span className="text-muted">Target Platforms:</span>
                  <div className="flex-row gap-xs">
                    {selectedSearch.platforms && Array.isArray(selectedSearch.platforms) ? (
                      selectedSearch.platforms.map((p) => (
                        <span key={p} className="badge badge-neutral">{p.toUpperCase()}</span>
                      ))
                    ) : (
                      <span className="badge badge-neutral">—</span>
                    )}
                  </div>
                </div>
              </div>

              {/* Flight Results */}
              <div className="flex-col gap-sm">
                <span className="form-label" style={{ fontSize: 11 }}>Recorded flight results ({selectedResults.length}) · {selectedResults.filter(r=>r.savings_breakdown?.verification==='checkout').length} recorded checkout totals</span>
                
                {selectedSearch.status === "running" && (
                  <div className="glass-card flex-row gap-sm" style={{ padding: 16, borderLeft: "4px solid hsl(var(--color-primary))" }}>
                    <RefreshCw size={16} className="animate-spin text-primary" />
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>Search execution in progress...</div>
                      <div style={{ fontSize: 11, color: "hsl(var(--text-secondary))" }}>Agents are currently scanning websites. Click Refresh above for updates.</div>
                    </div>
                  </div>
                )}

                {selectedSearch.status === "failed" && selectedResults.length === 0 && (
                  <div className="glass-card flex-row gap-sm" style={{ padding: 16, borderLeft: "4px solid hsl(var(--color-error))" }}>
                    <XCircle size={16} className="text-error" />
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>Search failed</div>
                      <div style={{ fontSize: 11, color: "hsl(var(--text-secondary))" }}>
                        No usable results were recorded. Review the search logs for the actual error before retrying.
                      </div>
                    </div>
                  </div>
                )}

                {selectedSearch.status === "cancelled" && selectedResults.length === 0 && (
                  <div className="glass-card flex-row gap-sm" style={{ padding: 16, borderLeft: "4px solid hsl(var(--color-warning))" }}>
                    <AlertCircle size={16} className="text-warning" />
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>Search Cancelled by User</div>
                      <div style={{ fontSize: 11, color: "hsl(var(--text-secondary))" }}>Execution was aborted before workers could complete.</div>
                    </div>
                  </div>
                )}

                {selectedResults.length === 0 && selectedSearch.status === "completed" && (
                  <div className="glass-card flex-row gap-sm" style={{ padding: 16, borderLeft: "4px solid hsl(var(--color-error))" }}>
                    <AlertCircle size={16} className="text-error" />
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>No Flight Deals Found</div>
                      <div style={{ fontSize: 11, color: "hsl(var(--text-secondary))" }}>No matching flights or discount savings could be parsed.</div>
                    </div>
                  </div>
                )}

                {selectedResults.map((result) => {
                  const verified = result.savings_breakdown?.verification === 'checkout';
                  
                  return (
                    <div key={result.id} className="glass-card module-card" style={{ padding: 16 }}>
                      <div className="flex-row" style={{ justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                        <div>
                          <span className="badge badge-neutral" style={{ marginBottom: 4, display: "inline-block" }}>
                            {result.platform.toUpperCase()}
                          </span>
                          <h3 style={{ margin: "4px 0 2px", fontSize: 15, fontWeight: 600 }}>
                            {result.airline} {result.flight_number}
                          </h3>
                          <span style={{ fontSize: 11, color: "hsl(var(--text-muted))" }}>
                            {result.departure_time} – {result.arrival_time} • {result.duration} ({result.stops === 0 ? "Direct" : `${result.stops} Stop`})
                          </span>
                        </div>
                        <div style={{ textAlign: "right" }}>
                          <div className="badge badge-neutral" style={{ marginBottom: 4 }}>
                            {verified ? 'Recorded checkout total' : 'Listed or legacy fare — reverify'}
                          </div>
                          <div className="price-original">
                            ₹{result.base_price.toLocaleString("en-IN")}
                          </div>
                          <div className="price-final">
                            ₹{result.final_price.toLocaleString("en-IN")}
                          </div>
                        </div>
                      </div>

                      <div className="divider-dashed" style={{ margin: "0 0 10px" }} />

                      <div className="flex-row" style={{ justifyContent: "space-between", alignItems: "center", fontSize: 12 }}>
                        <span className="flex-row gap-xs" style={{ color: "hsl(var(--text-secondary))" }}>
                          <Tag size={12} style={{ color: "hsl(var(--text-muted))" }} />
                          Coupon: <strong style={{ color: "hsl(var(--color-success))" }}>{result.best_coupon_code || "None"}</strong>
                        </span>
                        <span className="price-savings">
                          Saved ₹{result.savings.toLocaleString("en-IN")}
                        </span>
                      </div>

                      {/* Stacking Instructions Summary */}
                      {result.savings_breakdown && result.savings_breakdown.instructions && result.savings_breakdown.instructions.length > 0 && (
                        <div style={{ marginTop: 10, padding: 8, background: "hsl(228 14% 18% / 0.4)", borderRadius: 6, fontSize: 11 }}>
                          <div style={{ fontWeight: 600, color: "hsl(var(--text-secondary))", marginBottom: 4 }}>Handoff Steps:</div>
                          <ul style={{ paddingLeft: 16, margin: 0, color: "hsl(var(--text-muted))", lineHeight: 1.4 }}>
                            {result.savings_breakdown.instructions.map((inst, index) => (
                              <li key={index}>{inst}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Handoff Button */}
                      {result.session_id && (
                        <div style={{ marginTop: 12, display: "flex", justifyContent: "flex-end" }}>
                          <button
                            className="btn btn-primary flex-row gap-xs"
                            onClick={() => handleHandoff(result.session_id)}
                            style={{ padding: "6px 12px", fontSize: 12, height: 30 }}
                          >
                            <ShieldCheck size={13} />
                            <span>Handoff to Browser</span>
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

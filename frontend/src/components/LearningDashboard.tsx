import { useState, useEffect } from "react";
import {
  Brain, Clock, TrendingUp, RefreshCw,
  Zap, BookOpen, MousePointerClick, ShieldAlert,
  Activity, Server, HelpCircle
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend
} from "recharts";
import { useLearningStore } from "../store";

interface LearningDashboardProps {
  sendMessage: (type: string, payload: any) => void;
}

type SubTab = "overview" | "suggestions" | "journal";

export default function LearningDashboard({ sendMessage }: LearningDashboardProps) {
  const dashboardData = useLearningStore((s) => s.dashboardData);
  const journal = useLearningStore((s) => s.journal);
  const [activeSubTab, setActiveSubTab] = useState<SubTab>("overview");
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchDashboardData = () => {
    setIsRefreshing(true);
    sendMessage("learning:dashboard:get", {});
    sendMessage("learning:journal:get", {});
    setTimeout(() => setIsRefreshing(false), 800);
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  if (!dashboardData) {
    return (
      <div className="page-container">
        <div className="page-header">
          <h1 className="page-title">System Intelligence</h1>
          <p className="page-subtitle">Autonomous learning, pipeline health optimization, and decision logs.</p>
        </div>
        <div className="glass-card empty-state">
          <Brain size={48} className="empty-state-icon animate-pulse-slow" style={{ color: "hsl(var(--color-primary))" }} />
          <div className="empty-state-title">Initializing Intelligence Dashboard...</div>
          <div className="empty-state-desc">Waiting for WebSocket response from the Python self-learning engine.</div>
          <button className="btn btn-primary" onClick={fetchDashboardData} style={{ marginTop: 16 }}>
            <RefreshCw size={14} style={{ marginRight: 8 }} /> Retry Connection
          </button>
        </div>
      </div>
    );
  }

  // Format suggestion statistics for Recharts
  const suggestionChartData = Object.entries(dashboardData.suggestion_stats || {}).map(([type, stats]) => ({
    name: type.replace("_", " "),
    Shown: stats.shown,
    Clicked: stats.clicked,
    Accepted: stats.accepted,
  }));

  // Combine and deduplicate journal sources
  const activeJournal = journal.length > 0 ? journal : (dashboardData.recent_journal || []);

  const getJournalCategoryStyles = (category: string) => {
    switch (category) {
      case "COUPON_LEARNING":
        return {
          bg: "hsl(var(--color-secondary-dark) / 0.2)",
          border: "hsl(var(--color-secondary) / 0.3)",
          text: "hsl(var(--color-secondary))"
        };
      case "PREDICTION_ACCURACY":
        return {
          bg: "hsl(var(--color-primary-dark) / 0.2)",
          border: "hsl(var(--color-primary) / 0.3)",
          text: "hsl(var(--color-primary))"
        };
      case "PIPELINE_HEALTH":
        return {
          bg: "hsl(var(--color-warning-dark) / 0.2)",
          border: "hsl(var(--color-warning) / 0.3)",
          text: "hsl(var(--color-warning))"
        };
      case "SUGGESTION_TUNING":
        return {
          bg: "hsl(var(--color-success-dark) / 0.2)",
          border: "hsl(var(--color-success) / 0.3)",
          text: "hsl(var(--color-success))"
        };
      default:
        return {
          bg: "hsl(var(--bg-primary) / 0.6)",
          border: "hsl(var(--card-border))",
          text: "hsl(var(--text-secondary))"
        };
    }
  };

  return (
    <div className="page-container">
      {/* Page Header */}
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h1 className="page-title">System Intelligence</h1>
          <p className="page-subtitle">Autonomous learning, pipeline health optimization, and decision logs.</p>
        </div>
        <button 
          className={`btn btn-secondary ${isRefreshing ? "loading" : ""}`} 
          onClick={fetchDashboardData} 
          disabled={isRefreshing}
          style={{ display: "flex", alignItems: "center", gap: 8 }}
        >
          <RefreshCw size={14} className={isRefreshing ? "animate-spin" : ""} />
          <span>{isRefreshing ? "Refreshing..." : "Refresh Stats"}</span>
        </button>
      </div>

      {/* Overview Cards */}
      <div className="grid-4 stagger" style={{ marginBottom: 24 }}>
        {/* Card 1: Cycles */}
        <div className="glass-card stat-card" style={{ position: "relative", overflow: "hidden" }}>
          <div style={{ position: "absolute", top: -10, right: -10, opacity: 0.05 }}>
            <Brain size={80} />
          </div>
          <div style={{ fontSize: 11, color: "hsl(var(--text-muted))", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>Learning Cycles</div>
          <div style={{ fontSize: 24, fontWeight: 800, margin: "6px 0", color: "hsl(var(--text-primary))" }}>
            #{dashboardData.cycle_count}
          </div>
          <div style={{ fontSize: 10, color: "hsl(var(--text-muted))" }}>Runs automatically every 6 hours</div>
        </div>

        {/* Card 2: Improvements */}
        <div className="glass-card stat-card" style={{ position: "relative", overflow: "hidden" }}>
          <div style={{ position: "absolute", top: -10, right: -10, opacity: 0.05 }}>
            <Zap size={80} />
          </div>
          <div style={{ fontSize: 11, color: "hsl(var(--text-muted))", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>Improvements Applied</div>
          <div style={{ fontSize: 24, fontWeight: 800, margin: "6px 0", color: "hsl(var(--color-success))" }}>
            {dashboardData.improvements_count}
          </div>
          <div style={{ fontSize: 10, color: "hsl(var(--text-muted))" }}>Autonomous database tuning logs</div>
        </div>

        {/* Card 3: MAPE */}
        <div className="glass-card stat-card" style={{ position: "relative", overflow: "hidden" }}>
          <div style={{ position: "absolute", top: -10, right: -10, opacity: 0.05 }}>
            <TrendingUp size={80} />
          </div>
          <div style={{ fontSize: 11, color: "hsl(var(--text-muted))", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>Forecaster Error (MAPE)</div>
          <div style={{ fontSize: 24, fontWeight: 800, margin: "6px 0", color: "hsl(var(--color-primary))" }}>
            {(dashboardData.prediction_accuracy?.avg_mape * 100).toFixed(2)}%
          </div>
          <div style={{ fontSize: 10, color: "hsl(var(--text-muted))" }}>Based on {dashboardData.prediction_accuracy?.total_audited} audited forecasts</div>
        </div>

        {/* Card 4: Coupons */}
        <div className="glass-card stat-card" style={{ position: "relative", overflow: "hidden" }}>
          <div style={{ position: "absolute", top: -10, right: -10, opacity: 0.05 }}>
            <ShieldAlert size={80} />
          </div>
          <div style={{ fontSize: 11, color: "hsl(var(--text-muted))", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>Dead Coupons Shelved</div>
          <div style={{ fontSize: 24, fontWeight: 800, margin: "6px 0", color: "hsl(var(--color-warning))" }}>
            {dashboardData.coupon_stats?.dead_coupons} / {dashboardData.coupon_stats?.total_tracked}
          </div>
          <div style={{ fontSize: 10, color: "hsl(var(--text-muted))" }}>Avg Success: {(dashboardData.coupon_stats?.avg_success_rate * 100).toFixed(1)}%</div>
        </div>
      </div>

      {/* Sub navigation tabs */}
      <div className="flex-row gap-sm" style={{ borderBottom: "1px solid hsl(var(--card-border))", paddingBottom: 8, marginBottom: 20 }}>
        <button 
          className={`btn ${activeSubTab === "overview" ? "btn-primary" : "btn-secondary"}`}
          onClick={() => setActiveSubTab("overview")}
          style={{ padding: "6px 12px", fontSize: 12 }}
        >
          <Server size={14} style={{ marginRight: 6 }} /> Scraper Pipelines & Health
        </button>
        <button 
          className={`btn ${activeSubTab === "suggestions" ? "btn-primary" : "btn-secondary"}`}
          onClick={() => setActiveSubTab("suggestions")}
          style={{ padding: "6px 12px", fontSize: 12 }}
        >
          <MousePointerClick size={14} style={{ marginRight: 6 }} /> Suggestion Effectiveness
        </button>
        <button 
          className={`btn ${activeSubTab === "journal" ? "btn-primary" : "btn-secondary"}`}
          onClick={() => setActiveSubTab("journal")}
          style={{ padding: "6px 12px", fontSize: 12 }}
        >
          <BookOpen size={14} style={{ marginRight: 6 }} /> Process Journal ({activeJournal.length})
        </button>
      </div>

      {/* TAB CONTENT: Pipelines */}
      {activeSubTab === "overview" && (
        <div className="flex-col gap-md animate-fade-in">
          {/* Section explanation */}
          <div className="glass-card" style={{ padding: 16, background: "hsl(228 14% 18% / 0.15)" }}>
            <div className="flex-row gap-sm" style={{ alignItems: "center" }}>
              <HelpCircle size={16} style={{ color: "hsl(var(--color-primary))" }} />
              <span style={{ fontSize: 12, fontWeight: 600 }}>About Pipeline Monitoring</span>
            </div>
            <p style={{ margin: "6px 0 0 0", fontSize: 11, color: "hsl(var(--text-secondary))", lineHeight: 1.5 }}>
              The system tracks scraper outcomes in real time. Platforms that trigger CAPTCHAs, timeout issues, or DOM modifications drop in reliability score. If a platform drops below 40% success rate, the self-learning engine automatically flags it and adjusts scrapers to use longer delays, proxy rotation, or stops hitting it to save resources.
            </p>
          </div>

          {/* Grid of Pipelines */}
          <div className="grid-2 gap-md">
            {Object.entries(dashboardData.pipeline_health || {}).map(([platform, metrics]) => {
              const isUnreliable = metrics.success_rate < 0.40;
              const barColor = isUnreliable ? "hsl(var(--color-error))" : metrics.success_rate < 0.75 ? "hsl(var(--color-warning))" : "hsl(var(--color-success))";
              return (
                <div key={platform} className="glass-card module-card hover-glow" style={{ padding: 16 }}>
                  <div className="flex-row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                    <div>
                      <span className="badge badge-neutral" style={{ textTransform: "uppercase", fontSize: 10 }}>
                        {platform}
                      </span>
                    </div>
                    <span className={`badge ${isUnreliable ? "badge-error" : metrics.success_rate < 0.75 ? "badge-warning" : "badge-success"}`} style={{ fontSize: 9 }}>
                      {isUnreliable ? "UNRELIABLE" : metrics.success_rate < 0.75 ? "DEGRADED" : "HEALTHY"}
                    </span>
                  </div>

                  {/* Circular/Linear progress bar */}
                  <div className="flex-col gap-sm">
                    <div className="flex-row" style={{ justifyContent: "space-between", fontSize: 11 }}>
                      <span style={{ color: "hsl(var(--text-secondary))" }}>Scrape Success Rate</span>
                      <span style={{ fontWeight: 700, color: barColor }}>{(metrics.success_rate * 100).toFixed(1)}%</span>
                    </div>
                    <div style={{ width: "100%", height: 6, background: "hsl(228 14% 18%)", borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${metrics.success_rate * 100}%`, height: "100%", background: barColor, borderRadius: 3 }} />
                    </div>

                    <div className="grid-2" style={{ marginTop: 8, gap: 12 }}>
                      <div style={{ background: "hsl(228 14% 18% / 0.3)", padding: 8, borderRadius: 6 }}>
                        <span style={{ fontSize: 9, color: "hsl(var(--text-muted))", display: "block" }}>TOTAL SCRAPES</span>
                        <span style={{ fontSize: 12, fontWeight: 700 }}>{metrics.successes} / {metrics.total}</span>
                      </div>
                      <div style={{ background: "hsl(228 14% 18% / 0.3)", padding: 8, borderRadius: 6 }}>
                        <span style={{ fontSize: 9, color: "hsl(var(--text-muted))", display: "block" }}>AVG LATENCY</span>
                        <span style={{ fontSize: 12, fontWeight: 700, display: "flex", alignItems: "center", gap: 4 }}>
                          <Clock size={12} style={{ color: "hsl(var(--text-muted))" }} />
                          {(metrics.avg_latency_ms / 1000).toFixed(2)}s
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* TAB CONTENT: Suggestions */}
      {activeSubTab === "suggestions" && (
        <div className="flex-col gap-md animate-fade-in">
          {/* Explanation */}
          <div className="glass-card" style={{ padding: 16, background: "hsl(228 14% 18% / 0.15)" }}>
            <div className="flex-row gap-sm" style={{ alignItems: "center" }}>
              <HelpCircle size={16} style={{ color: "hsl(var(--color-primary))" }} />
              <span style={{ fontSize: 12, fontWeight: 600 }}>Suggestion Acceptance Analytics</span>
            </div>
            <p style={{ margin: "6px 0 0 0", fontSize: 11, color: "hsl(var(--text-secondary))", lineHeight: 1.5 }}>
              This chart captures user responsiveness to saving recommendations. Clicks represent attention, while Accepts represent confirmed bookings routed through a given recommendation. The self-learning engine de-prioritizes recommendations that consistently yield under 5% acceptance after 50+ impressions.
            </p>
          </div>

          {/* Chart Card */}
          <div className="glass-card module-card">
            <h3 style={{ margin: "0 0 16px 0", fontSize: 14, fontWeight: 600 }}>Conversion Funnel by Suggestion Type</h3>
            {suggestionChartData.length > 0 ? (
              <div style={{ height: 300 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={suggestionChartData} margin={{ top: 10, right: 10, left: -20, bottom: 5 }}>
                    <XAxis dataKey="name" stroke="hsl(var(--text-muted))" style={{ fontSize: 10 }} />
                    <YAxis stroke="hsl(var(--text-muted))" style={{ fontSize: 10 }} />
                    <Tooltip
                      contentStyle={{ background: "hsl(228 18% 10%)", border: "1px solid hsl(228 14% 18%)", borderRadius: 6, color: "hsl(210 40% 98%)", fontSize: 11 }}
                    />
                    <Legend wrapperStyle={{ fontSize: 10, marginTop: 10 }} />
                    <Bar dataKey="Shown" fill="#64748b" name="Shown to User" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="Clicked" fill="hsl(var(--color-primary))" name="Clicked Detail" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="Accepted" fill="hsl(var(--color-success))" name="Accepted / Booked" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="empty-state" style={{ padding: "40px 0" }}>
                <Activity size={32} className="empty-state-icon" />
                <div style={{ fontSize: 12, color: "hsl(var(--text-muted))" }}>No suggestion tracking logs captured yet. Run a search to populate.</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB CONTENT: Process Journal */}
      {activeSubTab === "journal" && (
        <div className="flex-col gap-md animate-fade-in">
          {/* Explanation */}
          <div className="glass-card" style={{ padding: 16, background: "hsl(228 14% 18% / 0.15)" }}>
            <div className="flex-row gap-sm" style={{ alignItems: "center" }}>
              <HelpCircle size={16} style={{ color: "hsl(var(--color-primary))" }} />
              <span style={{ fontSize: 12, fontWeight: 600 }}>About the Process Journal</span>
            </div>
            <p style={{ margin: "6px 0 0 0", fontSize: 11, color: "hsl(var(--text-secondary))", lineHeight: 1.5 }}>
              The Process Journal is the audit log of all decisions automatically taken by the Self-Learning engine. It logs changes in prediction weights, coupon trust rankings, pipeline health adjustments, and suggestions tuning. It represents full transparency in how the engine adapts over time.
            </p>
          </div>

          {/* Timeline */}
          <div className="glass-card module-card flex-col gap-md" style={{ padding: 20 }}>
            <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>Chronological Intelligence Log</h3>
            <div className="divider" style={{ margin: "8px 0" }} />

            {activeJournal.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 16, maxHeight: 500, overflowY: "auto", paddingRight: 8 }}>
                {activeJournal.map((entry: any, index: number) => {
                  const style = getJournalCategoryStyles(entry.category);
                  const formattedTime = new Date(entry.recorded_at || entry.timestamp).toLocaleString("en-IN", {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit"
                  });

                  return (
                    <div key={index} style={{
                      display: "flex",
                      gap: 12,
                      alignItems: "flex-start",
                      position: "relative",
                      paddingBottom: index === activeJournal.length - 1 ? 0 : 16,
                    }}>
                      {/* Timeline line */}
                      {index !== activeJournal.length - 1 && (
                        <div style={{
                          position: "absolute",
                          top: 24,
                          left: 11,
                          width: 2,
                          bottom: 0,
                          background: "hsl(var(--card-border))"
                        }} />
                      )}

                      {/* Icon Bullet */}
                      <div style={{
                        width: 24,
                        height: 24,
                        borderRadius: "50%",
                        background: style.bg,
                        border: `1px solid ${style.border}`,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        zIndex: 1,
                        flexShrink: 0
                      }}>
                        <Brain size={12} style={{ color: style.text }} />
                      </div>

                      {/* Content Card */}
                      <div className="glass-card" style={{ 
                        flex: 1, 
                        padding: 12, 
                        background: "hsl(228 14% 18% / 0.2)",
                        border: "1px solid hsl(var(--card-border))"
                      }}>
                        <div className="flex-row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 6, gap: 12 }}>
                          <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 6px", background: style.bg, border: `1px solid ${style.border}`, borderRadius: 4, color: style.text }}>
                            {entry.category.replace("_", " ")}
                          </span>
                          <span style={{ fontSize: 10, color: "hsl(var(--text-muted))" }}>{formattedTime}</span>
                        </div>

                        <div style={{ fontSize: 12, fontWeight: 600, color: "hsl(var(--text-primary))", marginBottom: 4 }}>
                          {entry.action}
                        </div>

                        <p style={{ margin: 0, fontSize: 11, color: "hsl(var(--text-secondary))", lineHeight: 1.4 }}>
                          <span style={{ fontWeight: 600, color: "hsl(var(--text-muted))" }}>Reason:</span> {entry.reason}
                        </p>

                        {(entry.before_value || entry.after_value) && (
                          <div style={{ 
                            marginTop: 8, 
                            padding: 8, 
                            background: "hsl(228 14% 12% / 0.5)", 
                            borderRadius: 4,
                            border: "1px solid hsl(var(--card-border) / 0.5)",
                            fontSize: 10,
                            fontFamily: "monospace"
                          }}>
                            {entry.before_value && (
                              <div style={{ color: "hsl(var(--color-error))", marginBottom: 2 }}>
                                - Before: {entry.before_value}
                              </div>
                            )}
                            {entry.after_value && (
                              <div style={{ color: "hsl(var(--color-success))" }}>
                                + After: {entry.after_value}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="empty-state" style={{ padding: "40px 0" }}>
                <BookOpen size={32} className="empty-state-icon" />
                <div style={{ fontSize: 12, color: "hsl(var(--text-muted))" }}>No process journal audit entries recorded yet.</div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

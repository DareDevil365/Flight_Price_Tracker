import { Plane, Search, Tag, History, List, Settings, TrendingUp, Globe } from "lucide-react";

interface SidebarProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  connected: boolean;
  resultCount: number;
}

export default function Sidebar({ activeTab, onTabChange, connected, resultCount }: SidebarProps) {
  const navItems = [
    { id: "search", label: "Search Cockpit", icon: Search },
    { id: "results", label: "Results Ranker", icon: Tag, badge: resultCount > 0 ? resultCount : undefined },
    { id: "history", label: "Search History", icon: History },
    { id: "price_intel", label: "Price Intelligence", icon: TrendingUp },
    { id: "watchlist", label: "Red Room", icon: List },
    { id: "websites", label: "Manage Websites", icon: Globe },
  ];


  return (
    <div className="sidebar">
      <div className="logo">
        <div className="logo-icon">
          <Plane size={14} color="black" />
        </div>
        <span>FLIGHT FINDER</span>
      </div>

      <div className="sidebar-nav-container">
        <nav>
          {navItems.map((item) => (
            <button
              key={item.id}
              className={`nav-link ${activeTab === item.id ? "active" : ""}`}
              aria-label={item.label}
              title={item.label}
              onClick={() => onTabChange(item.id)}
            >
              <item.icon size={16} />
              <span>{item.label}</span>
              {item.badge !== undefined && (
                <span className="nav-badge">{item.badge}</span>
              )}
            </button>
          ))}
        </nav>
      </div>

      <div className="sidebar-footer" style={{ borderTop: "1px solid rgba(255, 255, 255, 0.06)", paddingTop: 14, marginTop: 14 }}>
        <button
          className={`nav-link ${activeTab === "settings" ? "active" : ""}`}
          aria-label="Settings"
          title="Settings"
          onClick={() => onTabChange("settings")}
          style={{ width: "100%", textAlign: "left" }}
        >
          <Settings size={16} />
          <span>Settings</span>
        </button>

        <div className="connection-indicator" style={{ marginTop: 14 }}>
          <span className={`connection-dot ${connected ? "online" : "offline"}`} />
          <span>Backend: {connected ? "Connected" : "Disconnected"}</span>
        </div>
      </div>
    </div>
  );
}

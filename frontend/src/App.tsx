import { useEffect } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { useSearchStore, useResultStore } from "./store";

import Sidebar from "./components/Sidebar";
import SearchCockpit from "./components/SearchCockpit";
import ResultsRanker from "./components/ResultsRanker";
import SearchHistory from "./components/SearchHistory";
import PriceHistory from "./components/PriceHistory";
import Watchlist from "./components/Watchlist";
import ManageWebsites from "./components/ManageWebsites";
import Settings from "./components/Settings";

import LearningDashboard from "./components/LearningDashboard";

type Tab = "search" | "results" | "history" | "price_intel" | "watchlist" | "websites" | "settings" | "learning";

export default function App() {
  const { connected, sendMessage } = useWebSocket();
  const activeTab = useSearchStore((s) => s.activeTab) as Tab;
  const setActiveTab = (tab: Tab) => useSearchStore.getState().setActiveTab(tab);

  const searchStatus = useSearchStore((s) => s.status);
  const results = useResultStore((s) => s.results);

  // Auto-switch to results when search completes
  useEffect(() => {
    if (searchStatus === "completed" && results.length > 0) {
      setActiveTab("results");
    }
  }, [searchStatus, results]);

  const renderTab = () => {
    switch (activeTab) {
      case "search":
        return <SearchCockpit sendMessage={sendMessage} />;
      case "results":
        return <ResultsRanker sendMessage={sendMessage} />;
      case "history":
        return <SearchHistory sendMessage={sendMessage} />;
      case "price_intel":
        return <PriceHistory sendMessage={sendMessage} />;
      case "watchlist":
        return <Watchlist sendMessage={sendMessage} />;
      case "learning":
        return <LearningDashboard sendMessage={sendMessage} />;
      case "websites":
        return <ManageWebsites sendMessage={sendMessage} />;
      case "settings":
        return <Settings />;
      default:
        return <SearchCockpit sendMessage={sendMessage} />;
    }
  };


  return (
    <div className="app-container">
      <div className="backdrop-glow">
        <div className="blob blob-1"></div>
        <div className="blob blob-2"></div>
        <div className="blob blob-3"></div>
      </div>
      <Sidebar
        activeTab={activeTab}
        onTabChange={(tab) => setActiveTab(tab as Tab)}
        connected={connected}
        resultCount={results.length}
      />
      <div className="content-area">
        {renderTab()}
      </div>
    </div>
  );
}

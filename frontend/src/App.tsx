import { lazy, Suspense, useEffect, useRef } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { useSearchStore, useResultStore } from "./store";

import Sidebar from "./components/Sidebar";
import SearchCockpit from "./components/SearchCockpit";
import ResultsRanker from "./components/ResultsRanker";
import SearchHistory from "./components/SearchHistory";
const PriceHistory = lazy(() => import("./components/PriceHistory"));
const RedRoom = lazy(() => import("./components/RedRoom"));
const ManageWebsites = lazy(() => import("./components/ManageWebsites"));
const Settings = lazy(() => import("./components/Settings"));
const LearningDashboard = lazy(() => import("./components/LearningDashboard"));

type Tab = "search" | "results" | "history" | "price_intel" | "watchlist" | "websites" | "settings" | "learning";

export default function App() {
  const { connected, sendMessage } = useWebSocket();
  const activeTab = useSearchStore((s) => s.activeTab) as Tab;
  const setActiveTab = (tab: Tab) => useSearchStore.getState().setActiveTab(tab);

  const searchStatus = useSearchStore((s) => s.status);
  const searchId = useSearchStore(s => s.searchId);
  const shownSearch = useRef<string | null>(null);
  const results = useResultStore((s) => s.results);

  // Auto-switch to results when search completes
  useEffect(() => {
    if (searchId && searchStatus === "completed" && results.length > 0 && shownSearch.current !== searchId) {
      shownSearch.current = searchId;
      setActiveTab("results");
    }
  }, [searchStatus, searchId, results]);

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
        return <RedRoom sendMessage={sendMessage} />;
      case "learning":
        return <LearningDashboard sendMessage={sendMessage} />;
      case "websites":
        return <ManageWebsites sendMessage={sendMessage} />;
      case "settings":
        return <Settings sendMessage={sendMessage} />;
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
        <Suspense fallback={<p>Loading…</p>}>{renderTab()}</Suspense>
      </div>
    </div>
  );
}

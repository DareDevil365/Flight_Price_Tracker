import { useEffect, useRef, useState, useCallback } from "react";
import { useSearchStore, useBotStore, useResultStore, useSettingsStore, useApiStore, useHistoryStore, usePlatformStore, useLearningStore } from "../store";

export function useWebSocket() {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);


  // Get store triggers
  const setSearchId = useSearchStore((state) => state.setSearchId);
  const setSearchStatus = useSearchStore((state) => state.setStatus);
  
  const addLog = useBotStore((state) => state.addLog);
  const updateBotStatus = useBotStore((state) => state.updateBotStatus);
  const updateScreenshot = useBotStore((state) => state.updateScreenshot);
  
  const addResult = useResultStore((state) => state.addResult);
  const setHandoffStatus = useResultStore((state) => state.setHandoffStatus);
  const setHistoryData = useResultStore((state) => state.setHistoryData);
  const setPrediction = useResultStore((state) => state.setPrediction);
  const setSuggestions = useResultStore((state) => state.setSuggestions);
  const setDateAlternatives = useResultStore((state) => state.setDateAlternatives);

  
  const loadSettings = useSettingsStore((state) => state.loadSettings);
  const setApiKeys = useApiStore((state) => state.setApiKeys);
  const setHistory = useHistoryStore((state) => state.setHistory);
  const setSearchResults = useHistoryStore((state) => state.setSearchResults);
  const setPlatforms = usePlatformStore((state) => state.setPlatforms);

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;

    console.log("Connecting to Flight Finder backend WebSocket...");
    const ws = new WebSocket("ws://localhost:8765/ws");

    ws.onopen = () => {
      console.log("WebSocket connection established!");
      setConnected(true);
      
      // Request initial settings on connect
      ws.send(JSON.stringify({ type: "settings:get", payload: {} }));
      ws.send(JSON.stringify({ type: "api:status:get", payload: {} }));
      ws.send(JSON.stringify({ type: "platform:list", payload: {} }));
    };

    ws.onclose = () => {
      console.log("WebSocket connection closed. Reconnecting in 3 seconds...");
      setConnected(false);
      setTimeout(connect, 3000);
    };

    ws.onerror = (err) => {
      console.error("WebSocket error: ", err);
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        const { type, payload } = message;

        // Route WS messages to Zustand actions
        switch (type) {
          case "search:started":
            setSearchId(payload.searchId);
            setSearchStatus("running");
            break;
          case "search:completed":
            setSearchStatus("completed");
            break;
          case "search:failed":
            setSearchStatus("failed");
            addLog({
              platform: "system",
              level: "error",
              message: `Search failed: ${payload.error}`,
              timestamp: new Date().toISOString()
            });
            break;
          case "search:cancelled":
            setSearchStatus("cancelled");
            break;
          case "bot:status":
            updateBotStatus(payload);
            break;
          case "bot:log":
            addLog(payload);
            break;
          case "bot:screenshot":
            updateScreenshot(payload);
            break;
          case "search:results":
            // Usually returns single results as they arrive
            addResult(payload);
            break;
          case "session:handoff:ack":
            setHandoffStatus(payload.sessionId, payload.status === "success" ? "success" : "failed");
            addLog({
              platform: "system",
              level: payload.status === "success" ? "success" : "error",
              message: `Handoff notification: ${payload.message}`,
              timestamp: new Date().toISOString()
            });
            break;
          case "session:warning":
            addLog({
              platform: "system",
              level: "warning",
              message: `Warning: ${payload.message}`,
              timestamp: new Date().toISOString()
            });
            break;
          case "session:expired":
            setHandoffStatus(payload.sessionId, "failed");
            addLog({
              platform: "system",
              level: "error",
              message: `Inactivity timeout: ${payload.message}`,
              timestamp: new Date().toISOString()
            });
            break;
          case "settings:data":
            loadSettings(payload);
            break;
          case "history:data":
            setHistoryData(payload.history || []);
            break;
          case "predict:result":
            setPrediction(payload);
            break;
          case "search:suggestions":
            setSuggestions(payload);
            break;
          case "search:date_alternatives":
            setDateAlternatives(payload.dateAlternatives || []);
            break;
          case "learning:dashboard:data":
            useLearningStore.getState().setDashboardData(payload);
            break;
          case "learning:journal:data":
            useLearningStore.getState().setJournal(payload);
            break;
          case "search:nlp_parsed":
            const nlp = payload;
            if (nlp.origin && nlp.destination) {
              useSearchStore.getState().updateTrip({
                origin: { code: nlp.origin, name: nlp.origin },
                destination: { code: nlp.destination, name: nlp.destination },
                departureDate: nlp.departureDate || new Date().toISOString().split("T")[0],
                cabinClass: nlp.cabinClass || "ECONOMY",
                passengerCount: nlp.passengerCount || 1,
              });
              addLog({
                platform: "system",
                level: "success",
                message: `AI parsed: ${nlp.origin} → ${nlp.destination} on ${nlp.departureDate}. Fields auto-populated.`,
                timestamp: new Date().toISOString()
              });
            } else {
              addLog({
                platform: "system",
                level: "error",
                message: `AI couldn't understand the query. Please provide valid cities/dates.`,
                timestamp: new Date().toISOString()
              });
            }
            window.dispatchEvent(new Event("nlp_parsed"));
            break;


          case "api:status:data":
          case "api:status:update":
            setApiKeys(payload);
            break;
          case "search:history:data":
            setHistory(payload);
            break;
          case "search:history:results:data":
            setSearchResults(payload.searchId, payload.results);
            break;
          case "platform:list:data":
            setPlatforms(payload);
            break;
          case "error":
            addLog({
              platform: "system",
              level: "error",
              message: payload.message || "An error occurred.",
              timestamp: new Date().toISOString()
            });
            alert(`Error: ${payload.message || "An error occurred."}`);
            break;
          default:
            console.log("Unhandled WebSocket event: ", type, payload);
        }
      } catch (err) {
        console.error("Failed to parse WebSocket message:", err);
      }
    };

    wsRef.current = ws;
  }, [setSearchId, setSearchStatus, addLog, updateBotStatus, updateScreenshot, addResult, setHandoffStatus, loadSettings, setHistoryData, setPrediction, setSuggestions, setDateAlternatives, setApiKeys, setHistory, setSearchResults, setPlatforms]);

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  const sendMessage = useCallback((type: string, payload: any) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, payload }));
    } else {
      console.error("Cannot send message: WebSocket is not connected.");
    }
  }, []);

  return { connected, sendMessage };
}

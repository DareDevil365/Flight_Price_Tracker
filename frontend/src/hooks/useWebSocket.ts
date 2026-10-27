import { useEffect, useRef, useState, useCallback } from "react";
import { useSearchStore, useBotStore, useResultStore, useSettingsStore, useApiStore, useHistoryStore, usePlatformStore, useLearningStore } from "../store";

export function useWebSocket() {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const disposed = useRef(false);
  const reconnect = useRef<ReturnType<typeof setTimeout> | null>(null);


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

  const connect = useCallback(function connectSocket() {
    if (disposed.current || (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN)) return;

    console.log("Connecting to Flight Finder backend WebSocket...");
    const ws = new WebSocket("ws://localhost:8765/ws");

    ws.onopen = () => {
      console.log("WebSocket connection established!");
      setConnected(true);
      
      // Request initial settings on connect
      ws.send(JSON.stringify({ type: "settings:get", payload: {} }));
      ws.send(JSON.stringify({ type: "api:status:get", payload: {} }));
      ws.send(JSON.stringify({ type: "platform:list", payload: {} }));
      ws.send(JSON.stringify({ type: "watchlist:list", payload: {} }));
      ws.send(JSON.stringify({ type: "redroom:list", payload: {} }));
      ws.send(JSON.stringify({ type: "notifications:get", payload: {} }));
    };

    ws.onclose = () => {
      if (wsRef.current !== ws || disposed.current) return;
      wsRef.current = null;
      console.log("WebSocket connection closed. Reconnecting in 3 seconds...");
      setConnected(false);
      if (useResultStore.getState().offerStatus.startsWith('Refreshing')) {
        useResultStore.getState().setOfferStatus('Offer refresh interrupted by connection loss. Reconnect and retry.');
      }
      if (useSearchStore.getState().status === 'running') {
        useSearchStore.getState().setStatus('failed');
        useBotStore.getState().addLog({platform:'system',level:'error',message:'Connection lost during search. Displayed results may be incomplete; check saved history or run a fresh search after reconnecting.',timestamp:new Date().toISOString()});
      }
      window.dispatchEvent(new Event('socket_disconnected'));
      if (useResultStore.getState().intelligenceRequestId) {
        useResultStore.setState({intelligenceRequestId:null, brain:null, brainError:'Connection lost while retrieving booking advice. Reconnect and refresh.'});
      }
      for (const [sessionId, state] of Object.entries(useResultStore.getState().checkoutStatus)) {
        if (state.status==='running') useResultStore.getState().setCheckoutStatus(sessionId, {
          status:'failed', message:'Connection lost during verification. The cart may still be processing; reconnect and check it again.'
        });
      }
      reconnect.current = setTimeout(connectSocket, 3000);
    };

    ws.onerror = (err) => {
      console.error("WebSocket error: ", err);
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        const { type, payload } = message;
        const currentId = useSearchStore.getState().searchId;
        const eventId = payload?.searchId || payload?.search_id;
        if ((type.startsWith('search:') || type.startsWith('bot:')) &&
            !['search:started','search:history:data','search:history:results:data','search:nlp_parsed'].includes(type) &&
            eventId && eventId !== currentId) return;

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
          case 'search:booking-context':
            useResultStore.getState().setGoogleBooking(payload);
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
          case "settings:saved":
            alert('Preferences saved. They apply to new searches.');
            break;
          case "watchlist:data":
            useResultStore.getState().setWatchlist(payload.items || []);
            break;
          case "redroom:data":
            useResultStore.getState().setRedRoom(payload.items || []);
            window.dispatchEvent(new Event('redroom_data'));
            break;
          case "brain:data":
            if (payload.requestId && payload.requestId===useResultStore.getState().intelligenceRequestId) useResultStore.getState().setBrain(payload);
            break;
          case 'brain:error':
            if (payload.requestId && payload.requestId===useResultStore.getState().intelligenceRequestId) useResultStore.setState({brain:null,brainError:payload.message || 'Booking advice is unavailable.'});
            break;
          case "notifications:data":
            useResultStore.getState().setNotifications(payload.items || []);
            break;
          case "search:alternatives":
            useResultStore.getState().setAlternatives(payload.alternatives || []);
            window.dispatchEvent(new Event('alternatives_ready'));
            if (payload.error) alert(payload.error);
            else if (!(payload.alternatives || []).length) alert('No cheaper dates or safely timed separate-ticket combinations were returned.');
            break;
          case "redroom:alert":
            ws.send(JSON.stringify({type:'notifications:get',payload:{}}));
            if ('Notification' in window && Notification.permission==='granted') new Notification('Red Room booking advice',{body:payload.message});
            break;
          case "redroom:error":
            window.dispatchEvent(new CustomEvent('redroom_error', {detail:payload}));
            addLog({platform:'system',level:'error',message:payload.message,timestamp:new Date().toISOString()});
            break;
          case "watchlist:checking":
            addLog({platform:"system",level:"info",message:'Checking saved watch '+payload.watchId,timestamp:new Date().toISOString()});
            break;
          case "watchlist:checked":
            addLog({platform:"system",level:payload.status==='failed'?'error':'success',message:payload.message,timestamp:new Date().toISOString()});
            break;
          case "coupon:refresh:completed":
            for (const platform of Object.keys(payload.status || {})) ws.send(JSON.stringify({type:'coupon:list',payload:{platform}}));
            useResultStore.getState().setOfferStatus(Object.entries(payload.status as Record<string,string>).map(([site,status])=>site+': '+status).join(' · '));
            break;
          case 'deal:options': {
            if (payload.searchId===useSearchStore.getState().searchId) {
              useResultStore.getState().setDealOptions(payload);
              useSettingsStore.getState().updateFinancial({blacklistedBanks:payload.rules.blacklisted_banks,excludedCardNames:payload.rules.excluded_card_names,allowedCardTypes:payload.rules.allowed_card_types,allowEMI:payload.rules.allow_emi,allowBNPL:payload.rules.allow_bnpl});
            }
            break;
          }
          case "coupon:list:result":
            useResultStore.getState().setOffers(payload.platform,payload.coupons || []);
            useResultStore.getState().setCouponTrackRecord(payload.platform,payload.trackRecord || []);
            break;
          case 'session:verification':
            useResultStore.getState().setCheckoutStatus(payload.sessionId, {status: payload.status, message: payload.message});
            if (payload.status !== 'running' && payload.platform) {
              ws.send(JSON.stringify({type:'coupon:list',payload:{platform:payload.platform}}));
            }
            break;
          case "session:verify:ack":
            if (payload.sessionId) {
              useResultStore.getState().setCheckoutStatus(payload.sessionId, {status: payload.inProgress?'running':payload.status, message: payload.message});
            }
            addLog({platform:'system', level:payload.status === 'failed' ? 'error' : 'success', message:payload.message, timestamp:new Date().toISOString()});
            alert(payload.message);
            break;
          case "watchlist:alert":
            addLog({platform:"system", level:payload.status === 'failed' ? 'error' : 'success', message:payload.message, timestamp:new Date().toISOString()});
            alert(payload.message);
            break;
          case "coupon:added":
            window.dispatchEvent(new CustomEvent('coupon_added', {detail:payload}));
            ws.send(JSON.stringify({type:'coupon:list',payload:{platform:payload.platform}}));
            addLog({platform:"system",level:"success",message:'Coupon '+payload.code+' saved for the next verification.',timestamp:new Date().toISOString()});
            break;
          case "history:data":
            if (payload.requestId && payload.requestId===useResultStore.getState().intelligenceRequestId) setHistoryData(payload.history || []);
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
          case "search:nlp_parsed": {
            const nlp = payload;
            if (nlp.origin && nlp.destination && nlp.departureDate) {
              useSearchStore.getState().updateTrip({
                origin: { code: nlp.origin, name: nlp.origin },
                destination: { code: nlp.destination, name: nlp.destination },
                departureDate: nlp.departureDate,
                cabinClass: nlp.cabinClass || "ECONOMY",
                passengerCount: nlp.passengerCount || 1,
                maxStops: nlp.maxStops ?? null,
                preferredTime: nlp.preferredTime || "ANY",
                returnDate: nlp.returnDate || undefined,
                tripType: nlp.returnDate ? "round_trip" : "one_way",
                specificFlightNumber: nlp.specificFlightNumber || "",
              });
              addLog({
                platform: "system",
                level: "success",
                message: `Parsed: ${nlp.origin} → ${nlp.destination} on ${nlp.departureDate}. Fields auto-populated.`,
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
          }
          case "ai:result": {
            const vision = payload;
            if (vision.success && vision.origin && vision.destination && vision.departureDate) {
              useSearchStore.getState().updateTrip({
                origin: vision.origin,
                destination: vision.destination,
                departureDate: vision.departureDate,
                returnDate: vision.returnDate,
                cabinClass: vision.cabinClass || "ECONOMY",
                passengerCount: vision.passengerCount || 1,
                specificFlightNumber: vision.specificFlightNumber || "",
                tripType: vision.returnDate ? 'round_trip' : 'one_way',
                maxStops: vision.maxStops ?? null,
                preferredTime: vision.preferredTime || 'ANY',
              });
              addLog({
                platform: "system",
                level: "success",
                message: `Vision AI parsed screenshot: ${vision.origin.code} → ${vision.destination.code} on ${vision.departureDate}. Fields auto-populated.`,
                timestamp: new Date().toISOString()
              });
            } else {
              addLog({
                platform: "system",
                level: "error",
                message: `Vision AI couldn't parse the itinerary screenshot. ${vision.message || ""}`,
                timestamp: new Date().toISOString()
              });
            }
            window.dispatchEvent(new Event("vision_parsed"));
            break;
          }


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
            if (payload.originalType==='coupon:refresh') useResultStore.getState().setOfferStatus('Offer refresh failed: '+(payload.message || 'Please retry.'));
            window.dispatchEvent(new CustomEvent('request_error', {detail:payload}));
            if (payload.originalType==='brain:get' && payload.requestId===useResultStore.getState().intelligenceRequestId) useResultStore.setState({brain:null,brainError:payload.message || 'Booking advice is unavailable.'});
            if (payload.originalType?.startsWith('redroom:')) window.dispatchEvent(new Event('redroom_error'));
            if (payload.originalType === 'search:start') setSearchStatus('failed');
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
    disposed.current = false;
    connect();
    return () => {
      disposed.current = true;
      if (reconnect.current) clearTimeout(reconnect.current);
      const ws = wsRef.current;
      wsRef.current = null;
      ws?.close();
    };
  }, [connect]);

  const sendMessage = useCallback((type: string, payload: Record<string, unknown>) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, payload }));
    } else {
      if (type==='coupon:refresh') useResultStore.getState().setOfferStatus('Offer refresh unavailable: Backend disconnected. Reconnect and retry.');
      window.dispatchEvent(new CustomEvent('request_error', {detail:{originalType:type,message:'Backend disconnected. Reconnect and retry.'}}));
      if (type === 'search:start') useSearchStore.getState().setStatus('failed');
      if (type === 'brain:get') useResultStore.setState({brain:null,brainError:'Backend disconnected. Reconnect and refresh booking advice.'});
      if (type === 'session:handoff' && typeof payload.sessionId==='string') useResultStore.getState().setHandoffStatus(payload.sessionId, 'failed');
      if (type === 'session:verify' && typeof payload.sessionId==='string') useResultStore.getState().setCheckoutStatus(payload.sessionId, {
        status:'failed', message:'Backend disconnected. Reconnect before verifying this cart.'
      });
      useBotStore.getState().addLog({platform:'system',level:'error',message:'Backend disconnected. Start the backend and retry.',timestamp:new Date().toISOString()});
    }
  }, []);

  return { connected, sendMessage };
}

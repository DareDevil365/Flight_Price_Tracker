import { useState, useEffect, useRef } from "react";
import {
  Plane, Wallet, Sparkles, Activity, Check, Terminal, Eye, Tag, Plus
} from "lucide-react";
import { useSearchStore, useBotStore, useSettingsStore, usePlatformStore, useResultStore } from "../store";


interface SearchCockpitProps {
  sendMessage: (type: string, payload: any) => void;
}



const BANKS = ["SBI", "HDFC", "ICICI", "AXIS", "KOTAK", "AMEX"];

const INDIAN_AIRPORTS = [
  { code: "DEL", city: "Delhi / New Delhi", name: "Indira Gandhi International Airport" },
  { code: "BOM", city: "Mumbai", name: "Chhatrapati Shivaji Maharaj International Airport" },
  { code: "BLR", city: "Bengaluru", name: "Kempegowda International Airport" },
  { code: "CCU", city: "Kolkata", name: "Netaji Subhash Chandra Bose International Airport" },
  { code: "MAA", city: "Chennai", name: "Chennai International Airport" },
  { code: "HYD", city: "Hyderabad", name: "Rajiv Gandhi International Airport" },
  { code: "GOI", city: "Goa (Dabolim)", name: "Dabolim Airport" },
  { code: "GOX", city: "Goa (Mopa)", name: "Manohar International Airport" },
  { code: "COK", city: "Kochi / Cochin", name: "Cochin International Airport" },
  { code: "AMD", city: "Ahmedabad", name: "Sardar Vallabhbhai Patel International Airport" },
  { code: "PNQ", city: "Pune", name: "Pune Airport" },
  { code: "ATQ", city: "Amritsar", name: "Sri Guru Ram Dass Jee International Airport" },
  { code: "IXC", city: "Chandigarh", name: "Shaheed Bhagat Singh International Airport" },
  { code: "LKO", city: "Lucknow", name: "Chaudhary Charan Singh International Airport" },
  { code: "PAT", city: "Patna", name: "Jayprakash Narayan Airport" },
  { code: "JAI", city: "Jaipur", name: "Jaipur International Airport" },
  { code: "TRV", city: "Trivandrum", name: "Trivandrum International Airport" },
  { code: "GAU", city: "Guwahati", name: "Lokpriya Gopinath Bordoloi International Airport" },
  { code: "VTZ", city: "Visakhapatnam", name: "Visakhapatnam International Airport" },
  { code: "BBI", city: "Bhubaneswar", name: "Biju Patnaik International Airport" },
  { code: "IXB", city: "Bagdogra", name: "Bagdogra Airport" },
  { code: "JDH", city: "Jodhpur", name: "Jodhpur Airport" },
  { code: "UDR", city: "Udaipur", name: "Maharana Pratap Airport" },
  { code: "NAG", city: "Nagpur", name: "Dr. Babasaheb Ambedkar International Airport" },
  { code: "IXR", city: "Ranchi", name: "Birsa Munda Airport" },
  { code: "RPR", city: "Raipur", name: "Swami Vivekananda Airport" },
  { code: "IXZ", city: "Port Blair", name: "Veer Savarkar International Airport" },
  { code: "BDQ", city: "Vadodara", name: "Vadodara Airport" },
  { code: "SXR", city: "Srinagar", name: "Sheikh ul-Alam International Airport" },
  { code: "IXJ", city: "Jammu", name: "Jammu Airport" },
  { code: "IMF", city: "Imphal", name: "Imphal Airport" },
  { code: "HND", city: "Hindon (Ghaziabad)", name: "Hindon Airport" }
];

const DEFAULT_PLATFORMS = [
  { id: "makemytrip", name: "MakeMyTrip", desc: "makemytrip.com" },
  { id: "easemytrip", name: "EaseMyTrip", desc: "easemytrip.com" },
  { id: "cleartrip", name: "Cleartrip", desc: "cleartrip.com" },
  { id: "yatra", name: "Yatra", desc: "yatra.com" },
  { id: "ixigo", name: "Ixigo", desc: "ixigo.com" },
  { id: "paytm", name: "Paytm Flights", desc: "tickets.paytm.com" },
  { id: "google_flights", name: "Google Flights", desc: "google.com/flights" }
];

export default function SearchCockpit({ sendMessage }: SearchCockpitProps) {
  const dbPlatforms = usePlatformStore((s) => s.platforms);
  const platformsLoaded = usePlatformStore((s) => s.loaded);
  
  const allPlatforms = [
    { id: "mock", name: "MockBooking.com", desc: "Local Mock Engine" },
    ...(platformsLoaded
      ? dbPlatforms
          .filter((p) => p.id !== "mock")
          .map((p) => ({
            id: p.id,
            name: p.name,
            desc: p.url.replace("https://", "").replace("www.", "").split("/")[0]
          }))
      : DEFAULT_PLATFORMS)
  ];

  const searchId = useSearchStore((s) => s.searchId);
  const searchStatus = useSearchStore((s) => s.status);
  const trip = useSearchStore((s) => s.trip);
  const platforms = useSearchStore((s) => s.platforms);
  const updateTrip = useSearchStore((s) => s.updateTrip);
  const togglePlatform = useSearchStore((s) => s.togglePlatform);
  const setSearchStatus = useSearchStore((s) => s.setStatus);

  const botStatuses = useBotStore((s) => s.botStatuses);
  const botLogs = useBotStore((s) => s.botLogs);
  const botScreenshots = useBotStore((s) => s.botScreenshots);
  const clearBotData = useBotStore((s) => s.clearBotData);

  const financial = useSettingsStore((s) => s.financial);
  const cloak = useSettingsStore((s) => s.cloak);
  const updateFinancial = useSettingsStore((s) => s.updateFinancial);

  const handoffStatus = useResultStore((s) => s.handoffStatus);
  const setHandoffStatus = useResultStore((s) => s.setHandoffStatus);

  const handleHandoff = (sessionId: string) => {
    setHandoffStatus(sessionId, "pending");
    sendMessage("session:handoff", { sessionId });
  };

  const [nlpQuery, setNlpQuery] = useState("");
  const [nlpExtracting, setNlpExtracting] = useState(false);

  // Custom Promo / Coupon Input States
  const [customCode, setCustomCode] = useState("");
  const [customPlatform, setCustomPlatform] = useState("");
  const [customBank, setCustomBank] = useState("ANY");
  const [customValue, setCustomValue] = useState("500");
  const [couponStatus, setCouponStatus] = useState("");

  const handleAddCustomCoupon = () => {
    setCouponStatus("");
    if (!customCode.trim()) {
      setCouponStatus("Error: Code is required");
      return;
    }
    if (!customPlatform) {
      setCouponStatus("Error: Platform is required");
      return;
    }
    
    sendMessage("coupon:add", {
      platform: customPlatform,
      code: customCode.trim().toUpperCase(),
      description: `User-defined code for ${customPlatform}`,
      bank_restriction: customBank === "ANY" ? null : customBank,
      discount_value: parseFloat(customValue) || 500.0,
      discount_type: "FLAT",
      card_type: "ANY"
    });
    
    setCouponStatus("Success: Coupon saved to test registry!");
    setCustomCode("");
    setCustomValue("500");
    setCustomBank("ANY");
    setTimeout(() => setCouponStatus(""), 3000);
  };

  // Autocomplete & Validation States
  const [originInput, setOriginInput] = useState("");
  const [destInput, setDestInput] = useState("");
  const [showOriginDropdown, setShowOriginDropdown] = useState(false);
  const [showDestDropdown, setShowDestDropdown] = useState(false);
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});

  const originContainerRef = useRef<HTMLDivElement>(null);
  const destContainerRef = useRef<HTMLDivElement>(null);

  // Click outside to close dropdowns and listen to nlp_parsed
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (originContainerRef.current && !originContainerRef.current.contains(event.target as Node)) {
        setShowOriginDropdown(false);
      }
      if (destContainerRef.current && !destContainerRef.current.contains(event.target as Node)) {
        setShowDestDropdown(false);
      }
    }
    const handleNlpDone = () => {
      setNlpExtracting(false);
      setNlpQuery("");
    };
    document.addEventListener("mousedown", handleClickOutside);
    window.addEventListener("nlp_parsed", handleNlpDone);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      window.removeEventListener("nlp_parsed", handleNlpDone);
    };
  }, []);

  // Sync inputs with trip changes (e.g. from AI parsing)
  useEffect(() => {
    if (trip.origin) {
      const matched = INDIAN_AIRPORTS.find((a) => a.code === trip.origin?.code);
      setOriginInput(matched ? `${matched.city} (${matched.code})` : trip.origin.code);
    } else {
      setOriginInput("");
    }
  }, [trip.origin]);

  useEffect(() => {
    if (trip.destination) {
      const matched = INDIAN_AIRPORTS.find((a) => a.code === trip.destination?.code);
      setDestInput(matched ? `${matched.city} (${matched.code})` : trip.destination.code);
    } else {
      setDestInput("");
    }
  }, [trip.destination]);

  const clearResults = () => {
    import("../store").then((m) => m.useResultStore.getState().clearResults());
  };

  const handleNlpSearch = () => {
    if (!nlpQuery.trim()) return;
    setNlpExtracting(true);
    sendMessage("search:nlp_parse", { text: nlpQuery });
  };

  const validateInputs = () => {
    const newErrors: Record<string, string> = {};

    // 1. Origin validation
    if (!trip.origin?.code) {
      newErrors.origin = "Origin airport is required";
    } else {
      const isValidOrigin = INDIAN_AIRPORTS.some((a) => a.code === trip.origin?.code);
      if (!isValidOrigin) {
        newErrors.origin = `Invalid airport. Please select from dropdown.`;
      }
    }

    // 2. Destination validation
    if (!trip.destination?.code) {
      newErrors.destination = "Destination airport is required";
    } else {
      const isValidDest = INDIAN_AIRPORTS.some((a) => a.code === trip.destination?.code);
      if (!isValidDest) {
        newErrors.destination = `Invalid airport. Please select from dropdown.`;
      }
    }

    // 3. Same airport check
    if (trip.origin?.code && trip.destination?.code && trip.origin.code === trip.destination.code) {
      newErrors.destination = "Origin and destination cannot be the same";
    }

    // 4. Departure Date validation
    if (!trip.departureDate) {
      newErrors.departureDate = "Departure date is required";
    } else {
      const parsedDate = new Date(trip.departureDate);
      if (isNaN(parsedDate.getTime())) {
        newErrors.departureDate = "Please select a valid date";
      } else {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        if (parsedDate < today) {
          newErrors.departureDate = "Departure date cannot be in the past";
        }
        
        const year = parsedDate.getFullYear();
        if (year < today.getFullYear() || year > 2099) {
          newErrors.departureDate = "Please enter a reasonable year (e.g. 2026-2099)";
        }
      }
    }

    // 5. Passengers validation
    if (!trip.passengerCount || trip.passengerCount < 1 || trip.passengerCount > 9) {
      newErrors.passengerCount = "Must be between 1 and 9";
    }

    // 6. Platforms validation
    if (platforms.length === 0) {
      newErrors.platforms = "Please select at least one platform";
    }

    setValidationErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleLaunch = () => {
    if (!validateInputs()) {
      return;
    }
    clearBotData();
    clearResults();
    setSearchStatus("running");
    sendMessage("search:start", { trip, financial, cloak, platforms });
  };

  const handleCancel = () => {
    if (searchId) sendMessage("search:cancel", { searchId });
  };

  const getFilteredAirports = (searchVal: string) => {
    if (!searchVal) return [];
    const searchClean = searchVal.split(" (")[0].trim().toLowerCase();
    if (!searchClean) return [];

    return INDIAN_AIRPORTS.filter(
      (a) =>
        a.code.toLowerCase().includes(searchClean) ||
        a.city.toLowerCase().includes(searchClean) ||
        a.name.toLowerCase().includes(searchClean)
    ).slice(0, 5);
  };

  const handleOriginChange = (val: string) => {
    setOriginInput(val);
    setShowOriginDropdown(true);
    const cleanVal = val.trim().toUpperCase();
    const matched = INDIAN_AIRPORTS.find((a) => a.code === cleanVal || a.city.toUpperCase() === cleanVal);
    if (matched) {
      updateTrip({ origin: { code: matched.code, name: matched.city } });
    } else {
      updateTrip({ origin: { code: cleanVal.slice(0, 3), name: "" } });
    }
  };

  const handleDestChange = (val: string) => {
    setDestInput(val);
    setShowDestDropdown(true);
    const cleanVal = val.trim().toUpperCase();
    const matched = INDIAN_AIRPORTS.find((a) => a.code === cleanVal || a.city.toUpperCase() === cleanVal);
    if (matched) {
      updateTrip({ destination: { code: matched.code, name: matched.city } });
    } else {
      updateTrip({ destination: { code: cleanVal.slice(0, 3), name: "" } });
    }
  };

  const handleSelectOrigin = (airport: typeof INDIAN_AIRPORTS[0]) => {
    updateTrip({ origin: { code: airport.code, name: airport.city } });
    setOriginInput(`${airport.city} (${airport.code})`);
    setShowOriginDropdown(false);
    setValidationErrors((prev) => {
      const next = { ...prev };
      delete next.origin;
      return next;
    });
  };

  const handleSelectDest = (airport: typeof INDIAN_AIRPORTS[0]) => {
    updateTrip({ destination: { code: airport.code, name: airport.city } });
    setDestInput(`${airport.city} (${airport.code})`);
    setShowDestDropdown(false);
    setValidationErrors((prev) => {
      const next = { ...prev };
      delete next.destination;
      return next;
    });
  };

  const isRunning = searchStatus === "running";

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Flight Search & Analytics</h1>
        <p className="page-subtitle">
          Configure routing parameters, payment constraints, and dispatch parallel stealth workers.
        </p>
      </div>

      {/* AI NLP Input */}
      <div className="glass-card module-card" style={{ marginBottom: 20 }}>
        <div className="flex-row gap-sm" style={{ marginBottom: 10 }}>
          <Sparkles size={14} className="module-icon" />
          <span style={{ fontSize: 11, fontWeight: 600, color: "hsl(var(--color-primary))", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            AI Conversational Input
          </span>
        </div>
        <div className="flex-row gap-md">
          <div style={{ flex: 1, position: "relative" }}>
            <input
              type="text"
              className={`form-input ${nlpExtracting ? "analyzing" : ""}`}
              placeholder='e.g. "Delhi to Goa next Friday, evening flight, non-stop, economy for 2"'
              value={nlpQuery}
              onChange={(e) => setNlpQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleNlpSearch()}
              style={{ paddingLeft: 14 }}
            />
          </div>
          <button className="btn btn-secondary" onClick={handleNlpSearch} disabled={nlpExtracting}>
            {nlpExtracting ? "Extracting..." : "Analyze"}
          </button>
        </div>
      </div>

      <div className="grid-2-1">
        {/* LEFT COLUMN */}
        <div className="flex-col gap-lg">
          {/* Flight Details */}
          <div className="glass-card module-card">
            <div className="module-header">
              <Plane size={15} className="module-icon" />
              <span className="module-title">Flight Details</span>
            </div>
            <div className="grid-2" style={{ marginBottom: 12 }}>
              <div>
                <label className="form-label">Origin Airport</label>
                <div className="autocomplete-container" ref={originContainerRef}>
                  <input
                    type="text"
                    className={`form-input ${validationErrors.origin ? "invalid" : ""}`}
                    placeholder="Search city or code..."
                    value={originInput}
                    onChange={(e) => handleOriginChange(e.target.value)}
                    onFocus={() => setShowOriginDropdown(true)}
                  />
                  {showOriginDropdown && getFilteredAirports(originInput).length > 0 && (
                    <div className="autocomplete-dropdown">
                      {getFilteredAirports(originInput).map((a) => (
                        <div
                          key={a.code}
                          className="autocomplete-item"
                          onClick={() => handleSelectOrigin(a)}
                        >
                          <span className="autocomplete-item-city">
                            {a.city} ({a.code})
                          </span>
                          <span className="autocomplete-item-airport">{a.name}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                {validationErrors.origin && (
                  <div className="validation-error">{validationErrors.origin}</div>
                )}
              </div>
              <div>
                <label className="form-label">Destination Airport</label>
                <div className="autocomplete-container" ref={destContainerRef}>
                  <input
                    type="text"
                    className={`form-input ${validationErrors.destination ? "invalid" : ""}`}
                    placeholder="Search city or code..."
                    value={destInput}
                    onChange={(e) => handleDestChange(e.target.value)}
                    onFocus={() => setShowDestDropdown(true)}
                  />
                  {showDestDropdown && getFilteredAirports(destInput).length > 0 && (
                    <div className="autocomplete-dropdown">
                      {getFilteredAirports(destInput).map((a) => (
                        <div
                          key={a.code}
                          className="autocomplete-item"
                          onClick={() => handleSelectDest(a)}
                        >
                          <span className="autocomplete-item-city">
                            {a.city} ({a.code})
                          </span>
                          <span className="autocomplete-item-airport">{a.name}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                {validationErrors.destination && (
                  <div className="validation-error">{validationErrors.destination}</div>
                )}
              </div>
            </div>
            <div className="grid-2">
              <div>
                <label className="form-label">Departure Date</label>
                <input
                  type="date"
                  className={`form-input ${validationErrors.departureDate ? "invalid" : ""}`}
                  value={trip.departureDate}
                  onChange={(e) => {
                    updateTrip({ departureDate: e.target.value });
                    setValidationErrors((prev) => {
                      const next = { ...prev };
                      delete next.departureDate;
                      return next;
                    });
                  }}
                />
                {validationErrors.departureDate && (
                  <div className="validation-error">{validationErrors.departureDate}</div>
                )}
              </div>
              <div>
                <label className="form-label">Passengers</label>
                <input
                  type="number"
                  className={`form-input ${validationErrors.passengerCount ? "invalid" : ""}`}
                  min="1"
                  max="9"
                  value={trip.passengerCount}
                  onChange={(e) => {
                    const val = parseInt(e.target.value) || 1;
                    updateTrip({ passengerCount: val });
                    setValidationErrors((prev) => {
                      const next = { ...prev };
                      delete next.passengerCount;
                      return next;
                    });
                  }}
                />
                {validationErrors.passengerCount && (
                  <div className="validation-error">{validationErrors.passengerCount}</div>
                )}
              </div>
            </div>
          </div>

          {/* Platform Selection */}
          <div className="glass-card module-card">
            <div className="module-header">
              <Activity size={15} className="module-icon" />
              <span className="module-title">Target Platforms</span>
            </div>
            <div className="grid-2">
              {allPlatforms.filter((p) => p.id !== "mock").map((p) => {
                const active = platforms.includes(p.id);
                return (
                  <div
                    key={p.id}
                    className={`platform-card ${active ? "active" : ""}`}
                    onClick={() => {
                      togglePlatform(p.id);
                      setValidationErrors((prev) => {
                        const next = { ...prev };
                        delete next.platforms;
                        return next;
                      });
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 600, color: active ? "rgba(0, 0, 0, 0.9)" : "inherit" }}>{p.name}</div>
                      <div style={{ fontSize: 10, color: active ? "rgba(0, 0, 0, 0.6)" : "hsl(var(--text-muted))", marginTop: 2 }}>{p.desc}</div>
                    </div>
                    {active && <Check size={14} color="black" />}
                  </div>
                );
              })}
            </div>
            {validationErrors.platforms && (
              <div className="validation-error" style={{ marginTop: 10 }}>{validationErrors.platforms}</div>
            )}
          </div>

          {/* Add Custom Promo Code / Bank Offer */}
          <div className="glass-card module-card">
            <div className="module-header">
              <Tag size={15} className="module-icon" style={{ color: "hsl(var(--color-success))" }} />
              <span className="module-title">Add Promo Code or Bank Offer</span>
            </div>
            <div className="flex-col gap-sm">
              <div className="grid-2" style={{ gap: 10 }}>
                <div>
                  <label className="form-label" style={{ fontSize: 11 }}>Promo Code</label>
                  <input
                    type="text"
                    placeholder="e.g. FLYNEW, HDFC10"
                    className="form-input"
                    value={customCode}
                    onChange={(e) => setCustomCode(e.target.value.toUpperCase())}
                  />
                </div>
                <div>
                  <label className="form-label" style={{ fontSize: 11 }}>Platform</label>
                  <select
                    className="form-input"
                    value={customPlatform}
                    onChange={(e) => setCustomPlatform(e.target.value)}
                  >
                    <option value="">Select Website...</option>
                    {allPlatforms.filter((p) => p.id !== "mock").map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid-2" style={{ gap: 10 }}>
                <div>
                  <label className="form-label" style={{ fontSize: 11 }}>Bank Restriction (Optional)</label>
                  <select
                    className="form-input"
                    value={customBank}
                    onChange={(e) => setCustomBank(e.target.value)}
                  >
                    <option value="ANY">None (Universal)</option>
                    {BANKS.map((b) => (
                      <option key={b} value={b}>
                        {b}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="form-label" style={{ fontSize: 11 }}>Est. Discount Value (₹)</label>
                  <input
                    type="number"
                    placeholder="e.g. 500"
                    className="form-input"
                    value={customValue}
                    onChange={(e) => setCustomValue(e.target.value)}
                  />
                </div>
              </div>

              {couponStatus && (
                <div style={{ fontSize: 11, color: couponStatus.includes("Error") ? "hsl(var(--color-error))" : "hsl(var(--color-success))", marginTop: 4 }}>
                  {couponStatus}
                </div>
              )}

              <button
                className="btn btn-secondary flex-row gap-xs"
                onClick={handleAddCustomCoupon}
                style={{ width: "100%", justifyContent: "center", marginTop: 6 }}
              >
                <Plus size={14} />
                <span>Save Promo Code</span>
              </button>
            </div>
          </div>

          {/* Stealth Engine
          <div className="glass-card module-card">
            <div className="module-header">
              <Shield size={15} className="module-icon" />
              <span className="module-title">Stealth Engine</span>
            </div>
            <div className="grid-2" style={{ marginBottom: 12 }}>
              <div>
                <label className="form-label">Residential Proxies</label>
                <select
                  className="form-input"
                  value={cloak.proxyMode}
                  onChange={(e) => updateCloak({ proxyMode: e.target.value as "OFF" | "ON" })}
                >
                  <option value="OFF">Disabled (Direct IP)</option>
                  <option value="ON">Enabled (Rotate India IPs)</option>
                </select>
              </div>
              <div>
                <label className="form-label">Browser Engine</label>
                <select
                  className="form-input"
                  value={cloak.engine}
                  onChange={(e) => updateCloak({ engine: e.target.value as "playwright" | "camoufox" })}
                >
                  <option value="playwright">Playwright Chromium</option>
                  <option value="camoufox">Camoufox Firefox</option>
                </select>
              </div>
            </div>
            <div>
              <label className="form-label">
                Parallel Workers: {cloak.maxConcurrentBots}
              </label>
              <input
                type="range"
                min="1"
                max="6"
                value={cloak.maxConcurrentBots}
                onChange={(e) => updateCloak({ maxConcurrentBots: parseInt(e.target.value) })}
                style={{ width: "100%" }}
              />
            </div>
          </div>
          */}

          {/* Launch Button */}
          {isRunning ? (
            <button className="btn btn-danger btn-launch" onClick={handleCancel}>
              Cancel Search Execution
            </button>
          ) : (
            <button className="btn btn-primary btn-launch" onClick={handleLaunch}>
              🚀 Launch Analytics Agent
            </button>
          )}
        </div>

        {/* RIGHT COLUMN */}
        <div className="flex-col gap-lg">
          {/* Financial Constraints */}
          <div className="glass-card module-card">
            <div className="module-header">
              <Wallet size={15} className="module-icon" />
              <span className="module-title">Financial Constraints</span>
            </div>

            <div className="grid-2" style={{ marginBottom: 14 }}>
              <div className="flex-col gap-sm">
                <span className="form-label">Financing</span>
                <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "hsl(var(--text-secondary))", cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    checked={financial.allowEMI}
                    onChange={(e) => updateFinancial({ allowEMI: e.target.checked })}
                  />
                  Allow EMI Offers
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "hsl(var(--text-secondary))", cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    checked={financial.allowBNPL}
                    onChange={(e) => updateFinancial({ allowBNPL: e.target.checked })}
                  />
                  Allow BNPL (Pay Later)
                </label>
              </div>
              <div>
                <span className="form-label">Preferred Banks</span>
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4 }}>
                  {BANKS.map((bank) => {
                    const active = financial.whitelistedBanks.includes(bank);
                    return (
                      <button
                        key={bank}
                        className={`bank-chip ${active ? "active" : ""}`}
                        onClick={() =>
                          updateFinancial({
                            whitelistedBanks: active
                              ? financial.whitelistedBanks.filter((b) => b !== bank)
                              : [...financial.whitelistedBanks, bank],
                          })
                        }
                      >
                        {bank}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            <div>
              <label className="form-label">Custom Rules (Natural Language)</label>
              <textarea
                className="form-input"
                rows={2}
                placeholder="e.g., I hold HDFC Regalia and SBI Simply Save. Ignore Yes Bank."
                value={financial.customInstructions}
                onChange={(e) => updateFinancial({ customInstructions: e.target.value })}
              />
            </div>
          </div>

          {/* Live Monitor */}
          {isRunning && (
            <div className="glass-card module-card animate-fade-in" style={{ flex: 1, display: "flex", flexDirection: "column" }}>
              <div className="module-header" style={{ borderBottom: "none", marginBottom: 8 }}>
                <Activity size={15} className="module-icon animate-pulse" />
                <span className="module-title">Live Search Monitor</span>
              </div>

              {/* Bot Status Cards */}
              <div className="flex-col gap-sm" style={{ marginBottom: 14 }}>
                {Object.values(botStatuses).map((status) => (
                  <div
                    key={status.platform}
                    style={{
                      background: "hsl(var(--bg-primary))",
                      padding: "8px 12px",
                      borderRadius: "var(--border-radius)",
                      border: "1px solid hsl(var(--card-border))",
                      borderLeft: `3px solid ${
                        status.phase === "completed"
                          ? "hsl(var(--color-success))"
                          : status.phase === "failed"
                          ? "hsl(var(--color-error))"
                          : "hsl(var(--color-primary))"
                      }`,
                    }}
                  >
                    <div className="flex-row" style={{ justifyContent: "space-between", marginBottom: 4 }}>
                      <span style={{ fontSize: 12, fontWeight: 600 }}>
                        {status.platform.toUpperCase()}
                      </span>
                      <span style={{ fontSize: 10, color: "hsl(var(--text-muted))" }}>
                        {status.phase.replace("_", " ").toUpperCase()} • {status.progress}%
                      </span>
                    </div>
                    <div className="progress-bar-track">
                      <div
                        className={`progress-bar-fill ${
                          status.phase === "completed" ? "completed" : status.phase === "failed" ? "failed" : "running"
                        }`}
                        style={{ width: `${status.progress}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>

              {/* Browser Screenshots */}
              {Object.keys(botScreenshots).length > 0 && (
                <div style={{ marginBottom: 14 }}>
                  <span className="form-label">Live Browser Stream</span>
                  <div className="flex-row gap-sm" style={{ overflowX: "auto", paddingBottom: 4 }}>
                    {Object.values(botScreenshots).map((scr) => (
                      <div
                        key={scr.platform}
                        className={`screenshot-thumb ${scr.sessionId ? "interactive" : ""}`}
                        style={{ cursor: scr.sessionId ? "pointer" : "default" }}
                        onClick={() => {
                          if (scr.sessionId) {
                            handleHandoff(scr.sessionId);
                          }
                        }}
                      >
                        <div className="screenshot-thumb-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%" }}>
                          <span>{scr.platform.toUpperCase()}</span>
                          {scr.sessionId && (
                            <div className="flex-row gap-xs" style={{ alignItems: "center", fontSize: 9 }}>
                              <span style={{ color: "hsl(var(--color-primary))" }}>
                                {handoffStatus[scr.sessionId] === "pending" ? "Focusing..." : handoffStatus[scr.sessionId] === "success" ? "Focused" : "Handoff"}
                              </span>
                              <Eye size={10} className={handoffStatus[scr.sessionId] === "pending" ? "animate-pulse" : ""} />
                            </div>
                          )}
                        </div>
                        <img
                          src={`data:image/jpeg;base64,${scr.imageBase64}`}
                          alt={scr.platform}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Terminal */}
              <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
                <span className="form-label" style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 6 }}>
                  <Terminal size={11} />
                  Execution Console
                </span>
                <div className="terminal-window" style={{ flex: 1 }}>
                  {botLogs.map((log, idx) => (
                    <div key={idx} className="log-line">
                      <span className="log-time">
                        [{new Date(log.timestamp).toLocaleTimeString()}]
                      </span>
                      <span className="log-platform">[{log.platform.toUpperCase()}]</span>
                      <span className={`log-${log.level}`}>{log.message}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

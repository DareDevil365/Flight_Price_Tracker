import { useState, useEffect, useRef } from "react";
import {
  Plane, Wallet, Sparkles, Activity, Check, Terminal, Eye, Tag, Plus, Upload, FileImage, Loader
} from "lucide-react";
import { useSearchStore, useBotStore, useSettingsStore, usePlatformStore, useResultStore } from "../store";
import { validDate, localDate } from '../dateUtils';
import airportReference from '../../../backend/data/indian_airports.json';


interface SearchCockpitProps {
  sendMessage: (type: string, payload: Record<string, unknown>) => void;
}



const BANKS = ["SBI", "HDFC", "ICICI", "AXIS", "KOTAK", "AMEX"];

// Share the compiler's sourced location reference; this is not a promise of service.
const INDIAN_AIRPORTS = airportReference.airports;

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
    ...(platformsLoaded
      ? dbPlatforms
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
  const nlpPending = useRef(false);
  const [aiTab, setAiTab] = useState<"text" | "vision">("text");
  const [isDragOver, setIsDragOver] = useState(false);
  const [visionExtracting, setVisionExtracting] = useState(false);
  const visionPending = useRef(false);
  const visionReader = useRef<FileReader | null>(null);
  const [visionError, setVisionError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileUpload = (file: File) => {
    if (!file || nlpPending.current || visionPending.current) return;
    if (!file.type.startsWith("image/")) {
      setVisionError("Invalid file type. Please upload an image screenshot.");
      return;
    }
    setVisionError("");
    visionPending.current = true;
    setVisionExtracting(true);

    const reader = new FileReader();
    visionReader.current = reader;
    reader.onload = (e) => {
      if (!visionPending.current || visionReader.current !== reader) return;
      const base64Data = e.target?.result as string;
      if (base64Data) {
        sendMessage("ai:extract", { imageBase64: base64Data });
      } else {
        setVisionError("Failed to read image file.");
        visionPending.current = false;
        setVisionExtracting(false);
      }
    };
    reader.onerror = () => {
      if (visionReader.current !== reader) return;
      setVisionError("Error reading file.");
      visionPending.current = false;
      setVisionExtracting(false);
    };
    reader.readAsDataURL(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  };

  const triggerFileSelect = () => {
    if (nlpPending.current || visionPending.current) return;
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFileUpload(e.target.files[0]);
    }
  };

  // Custom Promo / Coupon Input States
  const [customCode, setCustomCode] = useState("");
  const [customPlatform, setCustomPlatform] = useState("");
  const [customBank, setCustomBank] = useState("ANY");
  const [customValue, setCustomValue] = useState("");
  const [couponStatus, setCouponStatus] = useState("");
  const [couponSaving, setCouponSaving] = useState(false);
  const couponPending = useRef(false);
  useEffect(()=>{
    const added=(event:Event)=>{
      const payload=(event as CustomEvent).detail;
      if (!couponPending.current || payload.platform!==customPlatform || payload.code!==customCode.trim().toUpperCase()) return;
      couponPending.current=false;setCouponSaving(false); setCouponStatus('Coupon saved. Its actual eligibility and savings still need testing.');
      setCustomCode(''); setCustomValue(''); setCustomBank('ANY');
    };
    const failed=(event:Event)=>{
      const payload=(event as CustomEvent).detail;
      if (payload?.originalType==='coupon:add' && couponPending.current) {couponPending.current=false;setCouponSaving(false);setCouponStatus('Error: '+payload.message);}
      if (payload?.originalType==='search:nlp_parse') {nlpPending.current=false;setNlpExtracting(false);}
      if (payload?.originalType==='ai:extract') {visionPending.current=false;visionReader.current=null;setVisionExtracting(false);setVisionError(payload.message || 'Image extraction failed.');}
    };
    const disconnected=()=>{nlpPending.current=false;visionPending.current=false;visionReader.current=null;setNlpExtracting(false);setVisionExtracting(false);if(couponPending.current){couponPending.current=false;setCouponSaving(false);setCouponStatus('Error: Connection lost. Check the coupon list before retrying.');}};
    window.addEventListener('coupon_added',added);window.addEventListener('request_error',failed);window.addEventListener('socket_disconnected',disconnected);
    return()=>{window.removeEventListener('coupon_added',added);window.removeEventListener('request_error',failed);window.removeEventListener('socket_disconnected',disconnected);};
  },[customPlatform,customCode]);

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
    
    couponPending.current=true;setCouponSaving(true);
    setCouponStatus('Saving coupon...');
    sendMessage("coupon:add", {
      platform: customPlatform,
      code: customCode.trim().toUpperCase(),
      description: `User-defined code for ${customPlatform}`,
      bank_restriction: customBank === "ANY" ? null : customBank,
      discount_value: Math.max(0, parseFloat(customValue) || 0),
      discount_type: "FLAT",
      card_type: "ANY"
    });
    
  };

  // Autocomplete & Validation States
  const [originInput, setOriginInput] = useState(trip.origin?.code || "");
  const [destInput, setDestInput] = useState(trip.destination?.code || "");
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
    const syncTripInputs = () => {
      const current = useSearchStore.getState().trip;
      setOriginInput(current.origin?.code || "");
      setDestInput(current.destination?.code || "");
    };
    const handleNlpDone = () => {
      nlpPending.current = false;
      syncTripInputs();
      setNlpExtracting(false);
      setNlpQuery("");
    };
    const handleVisionDone = () => {
      visionPending.current = false;
      visionReader.current = null;
      syncTripInputs();
      setVisionExtracting(false);
      setVisionError("");
    };
    document.addEventListener("mousedown", handleClickOutside);
    window.addEventListener("nlp_parsed", handleNlpDone);
    window.addEventListener("vision_parsed", handleVisionDone);
    return () => {
      nlpPending.current = false;
      visionPending.current = false;
      visionReader.current = null;
      document.removeEventListener("mousedown", handleClickOutside);
      window.removeEventListener("nlp_parsed", handleNlpDone);
      window.removeEventListener("vision_parsed", handleVisionDone);
    };
  }, []);

  const clearResults = () => {
    useResultStore.getState().clearResults();
  };

  const handleNlpSearch = () => {
    if (!nlpQuery.trim() || nlpPending.current || visionPending.current) return;
    nlpPending.current = true;
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
      const parsedDate = new Date(trip.departureDate+'T00:00:00');
      if (!validDate(trip.departureDate)) {
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
    if (!Number.isInteger(trip.passengerCount) || trip.passengerCount < 1 || trip.passengerCount > 9) {
      newErrors.passengerCount = "Must be between 1 and 9";
    }

    if (trip.tripType==='round_trip' && (!trip.returnDate || !validDate(trip.returnDate) || trip.returnDate < trip.departureDate)) {
      newErrors.returnDate='Choose a valid return date on or after departure.';
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
    useSearchStore.getState().setSearchId(null);
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
          Compare domestic Indian flights, then verify eligible coupons and fees at checkout.
        </p>
      </div>

      {/* AI Smart Assistant (Conversational & Vision Upload) */}
      <div className="glass-card module-card" style={{ marginBottom: 20 }}>
        <div className="ai-tabs-container">
          <button
            className={`ai-tab-btn ${aiTab === "text" ? "active" : ""}`}
            onClick={() => setAiTab("text")}
          >
            <Sparkles size={13} style={{ marginRight: 6 }} />
            Conversational Search
          </button>
          <button
            className={`ai-tab-btn ${aiTab === "vision" ? "active" : ""}`}
            onClick={() => setAiTab("vision")}
          >
            <FileImage size={13} style={{ marginRight: 6 }} />
            Itinerary Vision Scan
          </button>
        </div>

        {aiTab === "text" ? (
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
            <button className="btn btn-secondary" onClick={handleNlpSearch} disabled={nlpExtracting || visionExtracting}>
              {nlpExtracting ? "Extracting..." : "Analyze"}
            </button>
          </div>
        ) : (
          <div className="flex-col gap-sm">
            <div
              className={`upload-zone ${isDragOver ? "dragover" : ""} ${visionExtracting ? "analyzing" : ""}`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={triggerFileSelect}
            >
              <input
                type="file"
                ref={fileInputRef}
                style={{ display: "none" }}
                accept="image/*"
                onChange={handleFileChange}
              />
              {visionExtracting ? (
                <>
                  <Loader size={24} className="upload-icon animate-pulse" style={{ color: "hsl(var(--color-warning))" }} />
                  <span className="upload-title">Scanning itinerary screenshot...</span>
                  <span className="upload-subtitle">Gemini Vision is extracting structured travel parameters.</span>
                </>
              ) : (
                <>
                  <Upload size={24} className="upload-icon" />
                  <span className="upload-title">Drag & drop flight itinerary screenshot here</span>
                  <span className="upload-subtitle">Or click to select an image from your files</span>
                </>
              )}
            </div>
            {visionError && (
              <div className="validation-error" style={{ textAlign: "center" }}>
                {visionError}
              </div>
            )}
          </div>
        )}
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
                <label className="form-label">Adults (child fares are not supported yet)</label>
                <input
                  type="number"
                  className={`form-input ${validationErrors.passengerCount ? "invalid" : ""}`}
                  min="1"
                  max="9"
                  value={trip.passengerCount}
                  onChange={(e) => {
                    const val = Number(e.target.value);
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
            <div className="grid-2" style={{marginBottom:16}}>
              <label className="form-label">Trip type<select className="form-input" value={trip.tripType} onChange={e=>updateTrip({tripType:e.target.value as 'one_way' | 'round_trip'})}>
                <option value="one_way">One way</option><option value="round_trip">Round trip (separate legs)</option></select></label>
              <label className="form-label">Cabin<select className="form-input" value={trip.cabinClass} onChange={e=>updateTrip({cabinClass:e.target.value})}>
                <option value="ECONOMY">Economy</option><option value="PREMIUM_ECONOMY">Premium economy</option><option value="BUSINESS">Business</option><option value="FIRST">First class</option></select></label>
            </div>
            {trip.tripType==='round_trip' && <label className="form-label">Return date<input type="date" className="form-input" value={trip.returnDate || ''} min={trip.departureDate || localDate()} onChange={e=>updateTrip({returnDate:e.target.value})}/>{validationErrors.returnDate && <span role="alert" className="validation-error">{validationErrors.returnDate}</span>}</label>}
            <label className="form-label">Preferred departure time<select className="form-input" value={trip.preferredTime} onChange={e=>updateTrip({preferredTime:e.target.value})}>
              {['ANY','MORNING','AFTERNOON','EVENING','NIGHT'].map(t=><option key={t}>{t}</option>)}</select></label>
            <label className="form-label">Nearby departure dates (Google Flights)</label>
            <select className="form-input" value={trip.nearbyDatesRange || 0} onChange={e=>updateTrip({nearbyDatesRange:Number(e.target.value)})}>
              <option value={0}>Exact date only</option><option value={1}>Compare ±1 day</option><option value={2}>Compare ±2 days</option><option value={3}>Compare ±3 days</option>
            </select>
          </div>
          <div className="glass-card module-card">
            <div className="module-header">
              <Activity size={15} className="module-icon" />
              <span className="module-title">Target Platforms</span>
            </div>
            <div className="grid-2">
              {allPlatforms.filter((p) => ['makemytrip','easemytrip','cleartrip','google_flights'].includes(p.id)).map((p) => {
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
                    disabled={couponSaving}
                    onChange={(e) => setCustomCode(e.target.value.toUpperCase())}
                  />
                </div>
                <div>
                  <label className="form-label" style={{ fontSize: 11 }}>Platform</label>
                  <select
                    className="form-input"
                    value={customPlatform}
                    disabled={couponSaving}
                    onChange={(e) => setCustomPlatform(e.target.value)}
                  >
                    <option value="">Select Website...</option>
                    {allPlatforms.filter((p) => ['makemytrip','easemytrip','cleartrip'].includes(p.id)).map((p) => (
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
                    disabled={couponSaving}
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
                  <label className="form-label" style={{ fontSize: 11 }}>Advertised discount, optional (₹)</label>
                  <input
                    type="number"
                    placeholder="e.g. 500"
                    className="form-input"
                    value={customValue}
                    disabled={couponSaving}
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
                disabled={couponSaving}
                style={{ width: "100%", justifyContent: "center", marginTop: 6 }}
              >
                <Plus size={14} />
                <span>{couponSaving?'Saving...':'Save Promo Code'}</span>
              </button>
            </div>
          </div>



          {/* Launch Button */}
          {isRunning ? (
            <button className="btn btn-danger btn-launch" onClick={handleCancel}>
              Cancel Search Execution
            </button>
          ) : (
            <button className="btn btn-primary btn-launch" onClick={handleLaunch}>
              Search flight prices
            </button>
          )}
        </div>

        {/* RIGHT COLUMN */}
        <div className="flex-col gap-lg">
          <div className="glass-card module-card"><label>Stops<select aria-label="Maximum stops" className="form-input" value={trip.maxStops ?? 'ANY'} onChange={e=>updateTrip({maxStops:e.target.value==='ANY'?null:Number(e.target.value)})}>
            <option value="ANY">Any number of stops</option><option value="0">Nonstop only</option><option value="1">At most one stop</option><option value="2">At most two stops</option>
          </select></label></div>
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
            </div>
            <p>Card ownership is not required before searching. Results show deal conditions; tell us there if you cannot use a card or payment method.</p>
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

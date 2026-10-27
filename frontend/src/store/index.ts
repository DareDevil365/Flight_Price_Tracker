import { create } from "zustand";
import { localDate } from '../dateUtils';
import type { 
  TripProfile, 
  FinancialProfile, 
  CloakProfile, 
  BotStatus, 
  BotLogEntry, 
  BotScreenshot, 
  SearchResult, 
  WatchlistItem,
  SearchHistoryItem,
  CustomPlatform,
  SmartSuggestion,
  DateAlternative
} from "../types";
import type { FareQuote, BookingPrediction, JournalEntry } from '../types';


// ── Search Store ──
interface SearchStore {
  searchId: string | null;
  status: "idle" | "running" | "completed" | "cancelled" | "failed";
  trip: TripProfile;
  platforms: string[];
  activeTab: string;
  setSearchId: (id: string | null) => void;
  setStatus: (status: SearchStore["status"]) => void;
  updateTrip: (trip: Partial<TripProfile>) => void;
  togglePlatform: (platform: string) => void;
  resetPlatforms: () => void;
  setActiveTab: (tab: string) => void;
}

export const useSearchStore = create<SearchStore>((set) => ({
  searchId: null,
  status: "idle",
  trip: {
    tripType: "one_way",
    origin: null,
    destination: null,
    departureDate: localDate(new Date(Date.now() + 7 * 24 * 60 * 60 * 1000)),
    preferredTime: "ANY",
    passengerCount: 1,
    cabinClass: "ECONOMY",
  },
  platforms: ["makemytrip", "easemytrip", "cleartrip", "google_flights"],
  activeTab: "search",
  setSearchId: (searchId) => set({ searchId }),
  setStatus: (status) => set({ status }),
  updateTrip: (tripUpdate) => set((state) => ({ trip: { ...state.trip, ...tripUpdate } })),
  togglePlatform: (platform) => set((state) => {
    const active = state.platforms.includes(platform);
    return {
      platforms: active 
        ? state.platforms.filter((p) => p !== platform) 
        : [...state.platforms, platform]
    };
  }),
  resetPlatforms: () => set({ platforms: [] }),
  setActiveTab: (activeTab) => set({ activeTab })
}));

// ── Bot Store ──
interface BotStore {
  botStatuses: Record<string, BotStatus>;
  botLogs: BotLogEntry[];
  botScreenshots: Record<string, BotScreenshot>;
  addLog: (log: BotLogEntry) => void;
  updateBotStatus: (status: BotStatus) => void;
  updateScreenshot: (screenshot: BotScreenshot) => void;
  clearBotData: () => void;
}

export const useBotStore = create<BotStore>((set) => ({
  botStatuses: {},
  botLogs: [],
  botScreenshots: {},
  addLog: (log) => set((state) => ({ botLogs: [log, ...state.botLogs].slice(0, 500) })), // Cap logs
  updateBotStatus: (status) => set((state) => ({
    botStatuses: { ...state.botStatuses, [status.platform]: status }
  })),
  updateScreenshot: (screenshot) => set((state) => ({
    botScreenshots: { ...state.botScreenshots, [screenshot.platform]: screenshot }
  })),
  clearBotData: () => set({ botStatuses: {}, botLogs: [], botScreenshots: {} })
}));

// ── Result Store ──
interface ResultStore {
  googleBooking:Record<string,import('../types').GoogleBookingReport>;
  setGoogleBooking:(report:import('../types').GoogleBookingReport)=>void;
  dealOptions:import('../types').DealOptions|null;
  setDealOptions:(value:import('../types').DealOptions|null)=>void;
  results: SearchResult[];
  brain: import('../types').BrainReport | null;
  brainError: string | null;
  alternatives: import('../types').FlightAlternative[];
  redRoomItems: import('../types').RedRoomItem[];
  notifications: import('../types').SavedNotification[];
  setBrain: (brain:import('../types').BrainReport)=>void;
  setAlternatives: (alternatives:import('../types').FlightAlternative[])=>void;
  setRedRoom: (items:import('../types').RedRoomItem[])=>void;
  setNotifications: (items:import('../types').SavedNotification[])=>void;
  couponTrackRecord:Record<string,import('../types').CouponAuditRun[]>;
  setCouponTrackRecord:(platform:string,runs:import('../types').CouponAuditRun[])=>void;
  offers: Record<string, import('../types').PublishedOffer[]>;
  offerStatus: string;
  setOffers: (platform:string,offers:import('../types').PublishedOffer[])=>void;
  setOfferStatus: (status:string)=>void;
  watchlist: WatchlistItem[];
  handoffStatus: Record<string, "idle" | "pending" | "success" | "failed">;
  checkoutStatus: Record<string, {status: 'running' | 'success' | 'failed'; message: string}>;
  setCheckoutStatus: (sessionId: string, status: ResultStore['checkoutStatus'][string]) => void;
  historyData: FareQuote[];
  intelligenceRequestId: string | null;
  prediction: BookingPrediction | null;
  suggestions: SmartSuggestion | null;
  dateAlternatives: DateAlternative[];
  highlightedFlightId: string | null;
  setResults: (results: SearchResult[]) => void;
  addResult: (result: SearchResult) => void;
  setWatchlist: (items: WatchlistItem[]) => void;
  setHandoffStatus: (sessionId: string, status: ResultStore["handoffStatus"][string]) => void;
  setHistoryData: (data: FareQuote[]) => void;
  setPrediction: (prediction: BookingPrediction | null) => void;
  setSuggestions: (suggestions: SmartSuggestion) => void;
  setDateAlternatives: (dateAlternatives: DateAlternative[]) => void;
  setHighlightedFlightId: (id: string | null) => void;
  clearResults: () => void;
}


export const useResultStore = create<ResultStore>((set) => ({
  googleBooking:{},
  setGoogleBooking:(report)=>set(state=>({googleBooking:{...state.googleBooking,[report.resultId]:report}})),
  dealOptions:null,
  setDealOptions:(dealOptions)=>set({dealOptions}),
  results: [],
  brain: null,
  brainError: null,
  alternatives: [],
  redRoomItems: [],
  notifications: [],
  setBrain: (brain)=>set({brain,brainError:null}),
  setAlternatives: (alternatives)=>set({alternatives}),
  setRedRoom: (redRoomItems)=>set({redRoomItems}),
  setNotifications: (notifications)=>set({notifications}),
  couponTrackRecord:{},
  setCouponTrackRecord:(platform,runs)=>set(state=>({couponTrackRecord:{...state.couponTrackRecord,[platform]:runs}})),
  offers: {},
  offerStatus: '',
  setOffers: (platform,offers)=>set(state=>({offers:{...state.offers,[platform]:offers}})),
  setOfferStatus: (offerStatus)=>set({offerStatus}),
  watchlist: [],
  handoffStatus: {},
  checkoutStatus: {},
  setCheckoutStatus: (sessionId, status) => set(state => ({checkoutStatus: {...state.checkoutStatus, [sessionId]: status}})),
  historyData: [],
  intelligenceRequestId: null,
  prediction: null,
  suggestions: null,
  dateAlternatives: [],
  highlightedFlightId: null,
  setResults: (results) => set({ results }),
  addResult: (result) => set((state) => {
    // Avoid duplicates
    const filtered = state.results.filter((r) => r.id !== result.id);
    return { results: [...filtered, result].sort((a, b) => a.effective_price - b.effective_price) };
  }),
  setWatchlist: (watchlist) => set({ watchlist }),
  setHandoffStatus: (sessionId, status) => set((state) => ({
    handoffStatus: { ...state.handoffStatus, [sessionId]: status }
  })),
  setHistoryData: (historyData) => set({ historyData }),
  setPrediction: (prediction) => set({ prediction }),
  setSuggestions: (suggestions) => set({ suggestions }),
  setDateAlternatives: (dateAlternatives) => set({ dateAlternatives }),
  setHighlightedFlightId: (highlightedFlightId) => set({ highlightedFlightId }),
  clearResults: () => set({ results: [], googleBooking:{}, dealOptions:null, alternatives: [], brain: null, brainError:null, handoffStatus: {}, checkoutStatus: {}, historyData: [], intelligenceRequestId:null, prediction: null, suggestions: null, dateAlternatives: [], highlightedFlightId: null })
}));


// ── Settings Store (Financial & Cloak Configuration) ──
interface SettingsStore {
  financial: FinancialProfile;
  cloak: CloakProfile;
  updateFinancial: (update: Partial<FinancialProfile>) => void;
  updateCloak: (update: Partial<CloakProfile>) => void;
  loadSettings: (payload: { financial?: Partial<FinancialProfile>; cloak?: Partial<CloakProfile> }) => void;
}

export const useSettingsStore = create<SettingsStore>((set) => ({
  financial: {
    whitelistedBanks: [],
    blacklistedBanks: [],
    allowedCardTypes: ["CREDIT", "DEBIT", "UPI"],
    allowEMI: false,
    allowBNPL: false,
    allowWalletOffers: true,
    allowAppOnly: false,
    maxFinalPrice: null,
    customInstructions: "",
    cardRewardRates: []
  },
  cloak: {
    proxyMode: "OFF",
    sessionIsolation: true,
    humanSimIntensity: "MEDIUM",
    requestCooldownSec: 2.0,
    fingerprintRotation: true,
    maxConcurrentBots: 3,
    engine: "playwright"
  },
  updateFinancial: (update) => set((state) => ({ financial: { ...state.financial, ...update } })),
  updateCloak: (update) => set((state) => ({ cloak: { ...state.cloak, ...update } })),
  loadSettings: (payload) => set((state) => ({
    financial: payload.financial ? { ...state.financial, ...payload.financial } : state.financial,
    cloak: payload.cloak ? { ...state.cloak, ...payload.cloak } : state.cloak
  }))
}));

// ── API Key Store ──
export interface ApiKeyStatus {
  index: number;
  masked: string;
  status: "ACTIVE" | "EXHAUSTED";
  exhausted_until: string | null;
  use_count: number;
  failed_count: number;
  last_used: string | null;
}

interface ApiStore {
  apiKeys: ApiKeyStatus[];
  setApiKeys: (keys: ApiKeyStatus[]) => void;
}

export const useApiStore = create<ApiStore>((set) => ({
  apiKeys: [],
  setApiKeys: (apiKeys) => set({ apiKeys }),
}));

// ── Search History Store ──
interface HistoryStore {
  history: SearchHistoryItem[];
  searchResults: Record<string, SearchResult[]>;
  setHistory: (history: SearchHistoryItem[]) => void;
  setSearchResults: (searchId: string, results: SearchResult[]) => void;
}

export const useHistoryStore = create<HistoryStore>((set) => ({
  history: [],
  searchResults: {},
  setHistory: (history) => set({ history }),
  setSearchResults: (searchId, results) => set((state) => ({
    searchResults: { ...state.searchResults, [searchId]: results }
  })),
}));

// ── Custom Platforms Store ──
interface PlatformStore {
  platforms: CustomPlatform[];
  loaded: boolean;
  setPlatforms: (platforms: CustomPlatform[]) => void;
}

export const usePlatformStore = create<PlatformStore>((set) => ({
  platforms: [],
  loaded: false,
  setPlatforms: (platforms) => set({ platforms, loaded: true }),
}));

// ── Learning Store ──
export interface LearningDashboardData {
  data_source?: string;
  provider_run_count?: number | null;
  cycle_count: number | null;
  coupon_stats: {
    available?: boolean;
    run_count?: number | null;
    trial_count?: number | null;
    review_accepted_trials?: number | null;
    checkout_accepted_trials?: number | null;
    total_tracked: number | null;
    dead_coupons: number | null;
    avg_success_rate: number | null;
    avg_trust_score: number | null;
  };
  pipeline_health: Record<string, {
    total: number;
    successes: number;
    success_rate: number;
    avg_latency_ms: number | null;
  }>;
  prediction_accuracy: {
    available?: boolean;
    total_audited: number | null;
    avg_mape: number | null;
  };
  suggestion_stats: Record<string, {
    shown: number;
    clicked: number;
    accepted: number;
  }>;
  recent_journal: JournalEntry[];
  improvements_count: number | null;
}

interface LearningStore {
  dashboardData: LearningDashboardData | null;
  journal: JournalEntry[];
  setDashboardData: (data: LearningDashboardData) => void;
  setJournal: (journal: JournalEntry[]) => void;
}

export const useLearningStore = create<LearningStore>((set) => ({
  dashboardData: null,
  journal: [],
  setDashboardData: (dashboardData) => set({ dashboardData }),
  setJournal: (journal) => set({ journal }),
}));

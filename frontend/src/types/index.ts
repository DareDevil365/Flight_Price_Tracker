export interface Airport {
  code: string;
  name: string;
}

export interface TripProfile {
  tripType: "one_way" | "round_trip";
  origin: Airport | null;
  destination: Airport | null;
  departureDate: string;
  returnDate?: string;
  preferredTime: string;
  passengerCount: number;
  cabinClass: string;
  specificFlightNumber?: string;
}

export interface CardRewardRate {
  bank: string;
  rate: number;
}

export interface FinancialProfile {
  whitelistedBanks: string[];
  blacklistedBanks: string[];
  allowedCardTypes: string[];
  allowEMI: boolean;
  allowBNPL: boolean;
  allowWalletOffers: boolean;
  allowAppOnly: boolean;
  maxFinalPrice: number | null;
  customInstructions: string;
  cardRewardRates: CardRewardRate[];
}

export interface CloakProfile {
  proxyMode: "OFF" | "ON";
  proxyCredentials?: string;
  sessionIsolation: boolean;
  humanSimIntensity: "LOW" | "MEDIUM" | "HIGH";
  requestCooldownSec: number;
  fingerprintRotation: boolean;
  maxConcurrentBots: number;
  engine: "playwright" | "camoufox";
  showBrowser?: boolean;
}

export interface SearchRequest {
  trip: TripProfile;
  financial: FinancialProfile;
  cloak: CloakProfile;
  platforms: string[];
}

export interface BotStatus {
  platform: string;
  phase: "initializing" | "navigating" | "searching" | "passenger_details" | "testing_coupons" | "aggregating" | "completed" | "failed";
  progress: number;
  currentBestPrice?: number;
  currentCouponCode?: string;
  error?: string;
}

export interface BotLogEntry {
  platform: string;
  level: "info" | "warning" | "error" | "success";
  message: string;
  timestamp: string;
}

export interface BotScreenshot {
  platform: string;
  imageBase64: string;
  timestamp: string;
  sessionId?: string;
}

export interface CouponTestResult {
  code: string;
  status: "pre_filtered" | "invalid" | "valid_but_excluded" | "valid_match" | "error";
  price?: number;
  savings?: number;
  reason?: string;
}

export interface StackingSavingsDetail {
  provider: string;
  amount: number;
  type: string;
  rate_percent?: number;
}

export interface SavingsBreakdown {
  checkout_price: number;
  effective_price: number;
  total_stacking_savings: number;
  cashback_portal: StackingSavingsDetail;
  payment_method: StackingSavingsDetail;
  instructions: string[];
  convenience_fee?: number;
}

export interface SearchResult {
  id: string;
  search_id: string;
  platform: string;
  flight_number: string;
  airline: string;
  departure_time: string;
  arrival_time: string;
  duration: string;
  stops: number;
  base_price: number;
  final_price: number;
  best_coupon_code: string;
  savings: number;
  effective_price: number;
  deal_score: number;
  all_tested_coupons: CouponTestResult[];
  savings_breakdown: SavingsBreakdown;
  session_id: string;
  rank?: number;
  departure_date?: string;
}

export interface WatchlistItem {
  id: number;
  origin: string;
  destination: string;
  departure_date: string;
  target_price: number;
  check_frequency: string;
  last_checked?: string;
  last_price?: number;
  is_active: boolean;
}

export interface SearchHistoryItem {
  id: string;
  origin: string;
  destination: string;
  departure_date: string;
  return_date: string | null;
  passenger_count: number;
  cabin_class: string;
  platforms: string[];
  status: "pending" | "running" | "completed" | "cancelled" | "failed";
  started_at: string | null;
  completed_at: string | null;
  total_duration_ms: number | null;
  created_at: string;
}

export interface CustomPlatform {
  id: string;
  name: string;
  url: string;
  is_active: boolean;
  created_at: string;
}

export interface SmartSuggestionItem {
  type: "DATE_SHIFT" | "AIRPORT_ALT" | "LAYOVER" | "TIME_SHIFT";
  title: string;
  saving: number;
  net_saving?: number;
  detail: string;
  flight_id?: string;
  date?: string;
}

export interface ScenarioItem {
  label: string;
  price?: number;
  price_range?: string;
  verdict: string;
  note: string;
}

export interface SmartSuggestion {
  route: string;
  travel_date: string;
  verdict: string;
  urgency: string;
  confidence: number;
  recommended_book_by: string;
  potential_savings: number;
  advice: string;
  scenarios: ScenarioItem[];
  suggestions: SmartSuggestionItem[];
}


export interface DateAlternative {
  date: string;
  price: number;
  savings: number;
}


export interface Airport {
  code: string;
  name: string;
}

export type SocketSend = (type: string, payload: Record<string, unknown>) => void;
export interface FareQuote { observed_at: string; price: number; verification: string }
export interface BookingPrediction {
  current_price: number | null;
  current_best_platform: string | null;
  decision: { signal: string; reasoning: string; confidence: number | null };
}
export interface JournalEntry {
  category: string; action: string; reason: string; timestamp?: string; recorded_at?: string;
  before_value?: string; after_value?: string;
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
  nearbyDatesRange?: number;
  maxStops?:number|null;
}

export interface CardRewardRate {
  bank: string;
  rate: number;
}

export interface FinancialProfile {
  excludedCardNames?: string[];
  ownedCardNames?: string[];
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
  reasonCode?: string;
  manualUrl?: string;
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
  status: "pre_filtered" | "invalid" | "valid_but_excluded" | "valid_match" | "error" | "not_tested" | "conditional" | "accepted_no_saving" | "rejected" | "inconclusive";
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
  source_transport?: string;
  source_learning_allowed?: boolean | null;
  source_freshness?: string | null;
  source_inventory?: {complete: boolean;scope: string;candidate_cards?: number;parsed_rows?: number;rejected_cards?: number;returned_rows?: number;normalized_rows?: number;rejected_rows?: number;limitation: string};
  integrity?:{status:string;reasons:string[];compared_sources:string[]};
  layovers?:{airport:string;duration:number;change_of_airport?:boolean}[];
  coupon_coverage?:{eligible:number;tested:number;complete:boolean;collection?:string};
  verification?: "listed" | "checkout" | "unverified";
  previous_checkout?: {price: number; coupon: string | null; observed_at: string | null; invalidated_at: string};
  origin?: string;
  destination?: string;
  direction?: string;
  passenger_count?: number;
  cabin_class?: string;
  observed_at?: string;
  booking_url?: string;
  fee_status?: string;
  fee_scope?: string;
  listed_price?: number;
  booking_problem?: {code:string;message:string};
  checkout_price: number | null;
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
  brain?: BrainReport;
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

export interface PublishedOffer {
  code:string; platform:string; description?:string; bank_restriction?:string;
  valid_until?:string; source_url?:string; last_verified?:string;
  filter_reason?:string;
}

export interface DealOptions {
  searchId:string;excludedResultIds:string[];message:string;
  bestListed:SearchResult|null;bestVerified:SearchResult|null;
  eligibleOffers:PublishedOffer[];excludedOffers:PublishedOffer[];
  rules:{blacklisted_banks:string[];excluded_card_names:string[];allowed_card_types:string[];allow_emi:boolean;allow_bnpl:boolean};
}

export interface BrainReport {
  context_problems?:string[];
  feed_status?:{data?:Record<string,string>;updated_at?:string};
  source_problems?:Record<string,string>;
  partial_results?:{platform:string;price:number;airline:string;departure_time:string;integrity?:{status:string;reasons:string[]}}[];
  certainty:{percent:number|null;sample_count:number;range:number[]|null;scope:string;explanation:string};
  signal:string; reasoning:string; wait_until?:string; price:number|null; platform?:string;
  verification?:string; historical_years:number; updated_at:string;
  forecast:{status:string;observed_days:number;forecast_7d:number|null;model_mae:number|null;baseline_mae:number|null;confidence:string|null;readiness?:ForecastReadiness};
  factors:{kind:string;title:string;value?:number;units?:string;as_of?:string;change_30d_pct?:number;change_yoy_pct?:number|null;change_yoy_pp?:number|null;previous_year_value?:number;stale?:boolean;source_url?:string;interpretation:string}[];
  news:{title:string;url:string;published_at:string;primary_source:boolean}[];
  upcoming_offers:{platform:string;code:string;valid_from:string;source_url:string}[];
  missing_parameters:string[];
}
export interface ForecastReadiness {
  observed_days:number;training_days_required:number;training_days_remaining:number;
  weekly_outcomes_observed:number;weekly_outcomes_required_for_forecast:number;weekly_outcomes_required_for_certainty:number;
  weekly_outcomes_remaining_for_forecast:number;weekly_outcomes_remaining_for_certainty:number;
  minimum_additional_daily_observations_for_forecast:number|null;minimum_additional_daily_observations_for_certainty:number|null;
  earliest_forecast_evidence_date:string|null;earliest_certainty_evidence_date:string|null;
  trip_departure_date?:string;forecast_evidence_possible_before_departure?:boolean|null;certainty_evidence_possible_before_departure?:boolean|null;
  blockers:string[];assumptions:string[];
}
export interface GoogleBookingReport {
  searchId:string;resultId:string;status:'loading'|'available'|'unavailable';message?:string;
  source_url?:string;observed_at?:string;sessionId?:string;limitation?:string;
  scope?:{origin:string;destination:string;departure_date:string;passenger_count:number;cabin_class:string;airline:string;departure_time:string;arrival_time:string;stops:number};
  insight?:{classification:string;quoted_price:number;typical_low:number|null;typical_high:number|null;comparison_scope:string;certainty_percent:null}|null;
  booking_options?:{merchant:string;listed_total:number;included_convenience_fee:number|null;fee_note:string;verification:string}[];
}
export interface FlightAlternative {
  type:string; title:string; detail:string; saving:number; net_saving?:number|null;
}
export interface RedRoomItem {
  id:string;request:{trip:{origin:string;destination:string;departureDate:string;passengerCount:number;cabinClass:string};targetPrice?:number};
  interval_hours:number;last_checked?:string;last_attempt?:string;last_success?:string;last_error?:string;last_price?:number;report?:BrainReport & {alternatives?:FlightAlternative[]};checking:boolean;
}
export interface SavedNotification {id:number;title:string;message:string;is_read:boolean;created_at:string}

export interface CouponAuditRun {
  id:string;platform:string;started_at:string;completed_at?:string;status:string;
  scope:{origin?:string;destination?:string;departure_date?:string;passenger_count?:number;
    cabin_class?:string;flight_number?:string;stage:string;payment?:{method?:string;banks?:string[]}};
  summary:{baseline_price?:number;best_price?:number;best_coupon?:string;reason?:string;coverage?:{eligible:number;tested:number;complete:boolean;manual_review?:boolean}};
  trials:(CouponTestResult & {observed_at:string;restrictions?:string;terms?:string;source_url?:string;source_host?:string;valid_until?:string})[];
}

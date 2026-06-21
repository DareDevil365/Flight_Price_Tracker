# 🛫 Flight Finder — Personal Travel Optimization Agent

## Definitive Build Specification for Claude Code

> **For Claude Code:** This is the COMPLETE product specification. Read EVERY section before writing a single line of code. The architecture, tech stack, data models, UI modules, and processing pipeline are all defined here. Build exactly what is described. Where you have implementation freedom, default to simplicity, robustness, and maintainability.

> **This is NOT a screen scraper. This is a checkout-level price verification engine.**

---

## Table of Contents

1. [Product Vision](#1-product-vision)
2. [Tech Stack](#2-tech-stack)
3. [Application Architecture](#3-application-architecture)
4. [Project File Structure](#4-project-file-structure)
5. [The Cockpit — UI Modules](#5-the-cockpit--ui-modules)
6. [Data Models & Type Definitions](#6-data-models--type-definitions)
7. [End-to-End Processing Pipeline](#7-end-to-end-processing-pipeline)
8. [Stealth & Anti-Detection Layer](#8-stealth--anti-detection-layer)
9. [Coupon Brute-Force Engine](#9-coupon-brute-force-engine)
10. [The Foreground Handoff System](#10-the-foreground-handoff-system)
11. [Database Schemas](#11-database-schemas)
12. [WebSocket API Contract](#12-websocket-api-contract)
13. [Additional Features](#13-additional-features)
14. [Security & Privacy Model](#14-security--privacy-model)
15. [Error Handling & Resilience](#15-error-handling--resilience)
16. [Testing Strategy](#16-testing-strategy)
17. [Environment & Configuration](#17-environment--configuration)
18. [Build Order & Phasing](#18-build-order--phasing)

---

## 1. Product Vision

Build a **desktop application** (Electron shell + Python FastAPI backend) that acts as a personal flight price hunter. It operates real, stealthy headless browser sessions that navigate all the way to the **final checkout screen** of flight booking platforms — not just the search results page. At checkout, it programmatically brute-forces all known coupon codes, filters results against the user's personal banking/financial rules, and presents a ranked list of the absolute cheapest verified final prices.

The user never enters payment details into the app — the winning browser session is surfaced to the foreground of their desktop and the user completes payment themselves in a real browser.

### Why This Exists

The "listed price" on travel sites is a lie. The real price lives behind:
- Platform-specific coupon codes (sometimes 10-15% off)
- Bank-specific instant discounts (Rs.500-Rs.2000 off on specific cards)
- Hidden combo offers (coupon + bank discount stacking)
- Dynamic pricing that inflates based on your browsing history
- Add-on fees that appear only at checkout (convenience fees, insurance auto-added)

This agent kills all of that noise and gives you one number: **what you will actually pay**.

### Core Principles

1. **User never enters payment info into our app** — we hand off the live browser session
2. **Zero personal data leaves the user's machine** — all processing is local
3. **Stealth-first** — every browser session looks like a unique human visitor
4. **Modular** — every platform is a plugin; adding a new airline/OTA = adding a new worker file
5. **Transparent** — the user sees exactly what every bot is doing in real-time
6. **Price is ground truth** — never trust listing price; only trust the final checkout screen number
7. **Fail gracefully** — one crashed worker never kills the whole run

---

## 2. Tech Stack

| Layer | Technology | Reason |
|---|---|---|
| **Desktop Shell** | Electron (Node.js) | Cross-platform window management, foreground session handoff, system tray |
| **UI Framework** | React 18+ with TypeScript | Component-based, great for real-time dashboards |
| **UI Styling** | Tailwind CSS v4 + shadcn/ui | Rapid premium UI development |
| **UI State** | Zustand | Lightweight, no boilerplate |
| **UI Animations** | Framer Motion | Smooth micro-animations and transitions |
| **UI Charts** | Recharts | Price history sparklines, heatmaps |
| **UI Icons** | Lucide React | Consistent, lightweight icon set |
| **Backend Engine** | Python 3.11+ (FastAPI) | Superior async ecosystem, best Playwright stealth libraries, cleaner worker pattern |
| **Browser Automation** | Playwright (async Python) + CloakBrowser patches | Source-level fingerprint removal, passes 30/30 bot detection tests |
| **Anti-Detection** | playwright-stealth + custom JS injection patches | Secondary protection layer |
| **Proxy Management** | Residential proxy rotation (BrightData / Oxylabs / Smartproxy) | Unique IP per target platform |
| **Vision AI** | GPT-4o Vision API (primary) / local LLaVA via Ollama (offline fallback) | Screenshot-to-trip-details extraction |
| **Text AI** | GPT-4o-mini / Gemini Flash | Coupon rule parsing, custom instruction interpretation |
| **Coupon Database** | SQLite via aiosqlite | Fast local lookups, zero external dependency |
| **Session State** | Redis (local instance) | Real-time tracking of parallel browser session states |
| **IPC** | WebSocket (ws://localhost:8765) | Electron <-> FastAPI real-time bidirectional streaming |
| **Logging** | Loguru (Python) | Rotating log files, structured logging |
| **Packaging** | PyInstaller (Python) + Electron Builder (Electron) | Single distributable desktop app |

---

## 3. Application Architecture

```
+-----------------------------------------------------+
|                  ELECTRON SHELL                      |
|  +-----------------------------------------------+  |
|  |           REACT FRONTEND (Cockpit UI)          |  |
|  |                                                |  |
|  |  Module A | Module B | Module C | Module D     |  |
|  |                                                |  |
|  |  Module E: Live Execution Monitor              |  |
|  |  Results Ranker + "Book Now" Handoff Button    |  |
|  +----------------------+------------------------+  |
+-------------------------|---------------------------+
                          | WebSocket (ws://localhost:8765)
+-------------------------|---------------------------+
|              PYTHON FASTAPI BACKEND                  |
|                                                      |
|  +-------------+ +---------------+ +--------------+  |
|  | Vision/AI   | | Task Compiler | |  Coupon DB   |  |
|  | (GPT-4o)    | | (Schema Build)| |  (SQLite)    |  |
|  +-------------+ +---------------+ +--------------+  |
|                                                      |
|  +------------------------------------------------+  |
|  |         PARALLEL DISPATCH ENGINE                |  |
|  |  asyncio task pool — one task per platform      |  |
|  |  Concurrency limiter (default: 4 parallel)      |  |
|  +------------------------------------------------+  |
|                                                      |
|  +----------+ +----------+ +----------+ +--------+  |
|  |MakeMyTrip| |Cleartrip | |EaseMyTrip| | IndiGo |  |
|  | Worker   | | Worker   | | Worker   | | Worker |  |
|  +----------+ +----------+ +----------+ +--------+  |
|       Each worker: CloakBrowser + proxy              |
|       Each worker: traverses to checkout             |
|       Each worker: brute-forces coupon codes         |
|                                                      |
|  +------------------------------------------------+  |
|  |       SESSION MANAGER (Redis-backed)            |  |
|  |  Tracks all live browser sessions for handoff   |  |
|  +------------------------------------------------+  |
+------------------------------------------------------+
```

### Data Flow

```
[User fills Cockpit UI] 
       |
       | WebSocket: "search:start" + SearchSchema
       v
[FastAPI receives, compiles TaskSchema]
       |
       v
[Dispatcher launches N async workers in parallel]
       |
       +----> Worker 1 (MakeMyTrip + Proxy A)
       +----> Worker 2 (Cleartrip + Proxy B)  
       +----> Worker 3 (IndiGo + Proxy C)
       +----> Worker N ...
       |
       | WebSocket: real-time progress events stream to UI
       |
[Each worker: Search -> Select -> Passenger Details -> Checkout -> Coupon Loop]
       |
       v
[Results aggregated, filtered, ranked by final price]
       |
       | WebSocket: "search:results" + ranked list
       v
[UI displays ranked result cards]
       |
       | User clicks "Book Now"
       v
[Electron brings that worker's browser window to foreground]
[User completes payment themselves in the real browser]
```

---

## 4. Project File Structure

```
flight-finder/
|
+-- electron/                        # Electron Shell
|   +-- main.js                      # Main process: window management, spawn Python, IPC
|   +-- preload.js                   # Secure context bridge for renderer
|   +-- window-manager.js            # Foreground handoff logic (bring browser to front)
|   +-- package.json
|   +-- electron-builder.yml         # Packaging config
|
+-- frontend/                        # React UI (bundled by Vite)
|   +-- src/
|   |   +-- main.tsx                 # React entry point
|   |   +-- App.tsx                  # Root component with routing
|   |   |
|   |   +-- components/
|   |   |   +-- cockpit/             # The 5 Control Modules
|   |   |   |   +-- FlightIntentCapture.tsx    # Module A
|   |   |   |   +-- PlatformGrid.tsx           # Module B
|   |   |   |   +-- FinancialRulesEngine.tsx   # Module C
|   |   |   |   +-- CloakSettings.tsx          # Module D
|   |   |   |   +-- LaunchButton.tsx           # The big "Find Cheapest" button
|   |   |   |
|   |   |   +-- monitor/             # Module E: Live Execution Monitor
|   |   |   |   +-- BotStatusGrid.tsx          # Real-time bot status cards
|   |   |   |   +-- BotLogStream.tsx           # Terminal-style live log feed
|   |   |   |   +-- ProgressTimeline.tsx       # Overall pipeline progress
|   |   |   |   +-- SessionScreenshot.tsx      # Live screenshot previews
|   |   |   |
|   |   |   +-- results/             # Results Display
|   |   |   |   +-- ResultsRanker.tsx          # Ranked price table
|   |   |   |   +-- ResultCard.tsx             # Individual result card
|   |   |   |   +-- PriceBreakdown.tsx         # Detailed price breakdown modal
|   |   |   |   +-- HandoffButton.tsx          # "Book Now" foreground handoff
|   |   |   |
|   |   |   +-- features/            # Additional Feature UIs
|   |   |   |   +-- PriceHistory.tsx           # Historical price chart + sparklines
|   |   |   |   +-- FlexDateHeatmap.tsx        # Calendar heatmap for flexible dates
|   |   |   |   +-- CashbackCalculator.tsx     # Reward points value calculator
|   |   |   |   +-- WatchlistTab.tsx           # Saved routes + price alerts
|   |   |   |   +-- SessionReplay.tsx          # Bot execution replay viewer
|   |   |   |
|   |   |   +-- shared/              # Shared Components
|   |   |       +-- Navbar.tsx
|   |   |       +-- Sidebar.tsx
|   |   |       +-- Modal.tsx
|   |   |       +-- Toast.tsx
|   |   |       +-- ThemeToggle.tsx
|   |   |
|   |   +-- hooks/
|   |   |   +-- useWebSocket.ts      # WebSocket connection + message handling
|   |   |   +-- useBotStatus.ts      # Real-time bot state subscription
|   |   |   +-- useResults.ts        # Results state management
|   |   |
|   |   +-- stores/                  # Zustand State Stores
|   |   |   +-- searchStore.ts
|   |   |   +-- botStore.ts
|   |   |   +-- resultStore.ts
|   |   |   +-- settingsStore.ts
|   |   |
|   |   +-- types/
|   |   |   +-- index.ts             # All TypeScript interfaces
|   |   |
|   |   +-- styles/
|   |       +-- globals.css          # Tailwind base + custom design tokens
|   |
|   +-- package.json
|   +-- vite.config.ts
|   +-- tsconfig.json
|   +-- tailwind.config.ts
|
+-- backend/                         # Python FastAPI Backend
|   +-- main.py                      # FastAPI app + WebSocket server entry
|   +-- compiler.py                  # Phase 1: UI inputs -> TaskSchema
|   +-- dispatcher.py               # Phase 2: Parallel async task dispatch
|   +-- session_manager.py          # Browser session lifecycle + Redis state
|   +-- financial_filter.py         # Coupon pre-filter against user's financial rules
|   +-- human_sim.py                # Human behavior simulation (typing, mouse, scroll)
|   +-- proxy_manager.py            # Proxy allocation and rotation
|   +-- coupon_db.py                # SQLite coupon CRUD operations
|   +-- coupon_scraper.py           # Weekly auto-refresh from coupon aggregator sites
|   +-- coupon_brute_forcer.py      # Sequential coupon testing loop at checkout
|   +-- vision_intake.py            # GPT-4o Vision: image -> trip details
|   +-- text_ai.py                  # LLM: coupon rule parsing, custom instructions
|   +-- price_tracker.py            # Price history logging + trend analysis
|   |
|   +-- stealth/                    # Anti-Detection Layer
|   |   +-- browser_factory.py      # CloakBrowser creation with stealth patches
|   |   +-- fingerprint.py          # Canvas, WebGL, Audio, Font fingerprint rotation
|   |   +-- js_patches.py           # JavaScript injection patches for navigator overrides
|   |
|   +-- workers/                    # Platform-Specific Workers (one file per platform)
|   |   +-- base_worker.py          # Abstract base class all workers inherit
|   |   +-- makemytrip.py
|   |   +-- easemytrip.py
|   |   +-- cleartrip.py
|   |   +-- yatra.py
|   |   +-- ixigo.py
|   |   +-- indigo.py
|   |   +-- airindia.py
|   |   +-- akasa.py
|   |   +-- spicejet.py
|   |
|   +-- db/
|   |   +-- schema.sql              # SQLite table definitions
|   |   +-- seed_coupons.py         # Initial coupon data seeding script
|   |   +-- flight_agent.db         # SQLite database file (gitignored)
|   |
|   +-- requirements.txt
|
+-- config/
|   +-- user_profile.json           # Saved financial rules (persisted between sessions)
|   +-- watchlist.json              # Scheduled price monitoring jobs
|   +-- settings.json              # App settings, proxy keys, UI preferences
|
+-- logs/                           # Rotating log files (gitignored)
|   +-- app.log
|   +-- workers/
|       +-- makemytrip.log
|       +-- cleartrip.log
|       +-- ...
|
+-- sessions/                       # Browser session screenshots (gitignored)
|   +-- {session_uuid}/
|       +-- checkout.png
|       +-- screenshots/            # Periodic screenshots for replay
|
+-- .env                            # Environment variables (gitignored)
+-- .env.example                    # Template for env vars
+-- README.md
```

---

## 5. The Cockpit — UI Modules

### Design Philosophy

The UI should feel like a **mission control dashboard** — dark theme by default, with a futuristic/aviation aesthetic. Think cockpit instruments meets Bloomberg terminal. Layout: **left panel** (input controls, Modules A-D) and **right panel** (live monitoring Module E, then results).

### Design System

#### Color Palette
```
Background:         #0A0A0F  (near-black)
Surface:            #12121A  (card backgrounds)
Surface Elevated:   #1A1A2E  (hover states, modals)
Surface Active:     #252547  (selected items, active tabs)
Primary Accent:     #6366F1  (indigo-500 — action buttons, highlights)
Secondary Accent:   #8B5CF6  (violet-500 — secondary actions)
Success:            #10B981  (emerald-500 — cheaper prices, valid coupons, matches)
Warning:            #F59E0B  (amber-500 — medium prices, partial matches, beta status)
Danger:             #EF4444  (red-500 — expensive, blocked, errors, blacklisted)
Text Primary:       #F8FAFC  (slate-50)
Text Secondary:     #94A3B8  (slate-400)
Text Muted:         #475569  (slate-600)
Border:             #1E293B  (slate-800)
Glow Effect:        rgba(99, 102, 241, 0.15)  (indigo glow for active/focused elements)
```

#### Typography
```
Primary Font:       "Inter" (Google Fonts) — all UI text
Monospace Font:     "JetBrains Mono" (Google Fonts) — prices, coupon codes, logs, timestamps
```

#### Animation Guidelines
```
Duration:           150ms (micro), 300ms (standard), 500ms (emphasis)
Easing:             cubic-bezier(0.4, 0, 0.2, 1) for most transitions
Entry:              Fade + slide-up (8px) for cards appearing
Exit:               Fade + slide-down (4px)
Progress bars:      Animated with subtle shimmer effect
Status changes:     Brief color pulse (e.g., green flash when coupon matches)
```

---

### Module A: Flight Intent Capture

**Purpose:** Capture what flight the user wants to find.

#### Manual Input Fields

| Field | Type | Details |
|-------|------|---------|
| Trip Type | Toggle buttons | One-way / Round-trip |
| Origin | Autocomplete Input | IATA code + city name (e.g., "DEL - New Delhi"). Autocomplete from bundled airport database. |
| Destination | Autocomplete Input | Same format as Origin |
| Departure Date | Date Picker | Calendar with price color hints if history data exists for this route |
| Return Date | Date Picker | Only visible for Round-trip mode |
| Preferred Time | Dropdown | Any / Early Morning (6-9am) / Morning (9am-12pm) / Afternoon (12-6pm) / Evening (6-10pm) / Night (10pm-6am) |
| Passengers | Counter input | Adults (12+) — default 1 |
| Cabin Class | Dropdown | Economy / Premium Economy / Business / First |
| Specific Flight No. | Optional text input | e.g., "6E 2341" — locks search to this specific flight across platforms |
| Flexible Dates | Toggle + Range | "Find cheapest within +/-3 days" — enables calendar heatmap feature |

#### AI Visual Intake Zone

A drag-and-drop media zone below the manual fields:

```
+------------------------------------------------------+
|                                                      |
|     [camera icon]  Drop a screenshot or image here   |
|                                                      |
|   Supports: Flight itineraries, old boarding passes,  |
|   WhatsApp trip screenshots, search result captures   |
|                                                      |
|         [Browse Files]   [Paste from Clipboard]       |
|                                                      |
+------------------------------------------------------+
```

**Processing flow on image drop:**
1. Show loading spinner with "Analyzing image..."
2. Send image to GPT-4o Vision API with extraction prompt (see Section 7 Phase 1)
3. Auto-populate manual fields with extracted data
4. Show green checkmark icon next to each successfully extracted field
5. Show AI confidence level badge per field: High (green) / Medium (amber) / Low (red)
6. User can override any auto-filled field before proceeding

---

### Module B: Platform Grid Selection

A grid of toggleable cards. Each card shows:

| Element | Details |
|---------|---------|
| Platform logo | Actual logo image |
| Platform name | Text label |
| Status indicator | Green dot = supported, Yellow = beta, Gray = coming soon |
| Checkbox | Toggle selection on/off |
| Coupon count | "23 codes" — number of known coupons in local DB |
| Last run timestamp | "Last run: 2h ago" or "Never" |
| Estimated time | "~2 min" estimated search duration |
| Live status (during run) | Idle / Queued / Running / Done / Failed |

**Controls:** "Select All" / "Deselect All" toggle button at top.

**Supported Platforms:**

| Platform | Type | Build Priority |
|----------|------|----------------|
| MakeMyTrip | OTA | P0 (reference implementation) |
| EaseMyTrip | OTA | P0 |
| Cleartrip | OTA | P1 |
| Yatra | OTA | P1 |
| ixigo | OTA | P1 |
| IndiGo (goindigo.in) | Airline Direct | P0 |
| Air India | Airline Direct | P1 |
| Akasa Air | Airline Direct | P1 |
| SpiceJet | Airline Direct | P2 |

---

### Module C: Personal Financial Rules Engine

This module shapes how the bot filters coupon/offer results. All settings persist locally between sessions.

#### C1: Asset Whitelist (Banks I Hold)
- Tag-input field with auto-suggest from known Indian bank list
- Banks: SBI, ICICI, HDFC, Axis, Kotak, Yes Bank, IndusInd, RBL, AU Small Finance, Federal, IDFC First, Bank of Baroda, PNB, Canara, Union, etc.
- Visual: Blue/indigo tags
- Example input: "SBI, ICICI, HDFC"
- **Meaning:** "Only consider coupons valid for these banks"

#### C2: Asset Blacklist (Banks to Ignore)
- Same tag-input, visually distinct (red tags)
- Example: "Yes Bank, J&K Bank, American Express"
- **Meaning:** "Even if a coupon gives a lower price, skip it if it requires these banks"

#### C3: Card Type Filter
- Checkboxes: Credit Card / Debit Card / Net Banking / UPI / Wallet
- Default: All checked
- **Meaning:** "Only show coupons compatible with these payment methods"

#### C4: Financing Toggles
| Toggle | Default | Meaning |
|--------|---------|---------|
| Allow EMI offers | OFF | When OFF, any coupon requiring EMI commitment is auto-skipped |
| Allow BNPL offers | OFF | Skip Buy Now Pay Later dependent discounts |
| Allow wallet offers | ON | Include Paytm/Amazon Pay/PhonePe wallet offers |
| Allow app-only offers | OFF | Include offers that require booking via mobile app |

#### C5: Max Price Cap
- Optional number input: "Don't show me anything above Rs. ___"
- Filters out results exceeding this threshold from the final ranking

#### C6: Custom Instructions (Free Text)
```
Textarea placeholder: "Any special preferences? e.g., 'Only non-stop flights',
'I'm a student — check student discounts', 'Prefer morning departures even
if Rs.500 more'"
```
- Parsed by LLM during the filtering phase as soft rules
- Not hard-coded logic — AI interprets and applies best-effort

#### C7: Cashback/Rewards Rate (per card)
- Optional: user inputs reward rate per card
- Example: "HDFC Infinia: 3.3% reward value on travel" / "SBI SimplyCLICK: 1.25%"
- Used to calculate **effective price** after rewards
- `effectivePrice = checkoutPrice - (checkoutPrice * rewardRate)`

**[Save Profile]** button — persists entire Module C config to `config/user_profile.json`

---

### Module D: Anti-Price Surge Protocol (Cloak Settings)

Informational + configurable panel showing stealth measures.

#### Status Indicators (always visible)
```
[green]  Stateless Sessions     — Every browser starts blank (no cookies/cache)
[green]  Fingerprint Rotation   — Canvas, WebGL, Audio, Font prints randomized
[green]  Proxy Routing          — Each platform gets a unique residential IP
[green]  Human Simulation       — Typing, mouse, scrolling mimic real users
[yellow] Timing Jitter          — Gaussian-distributed random delays
```

#### Configurable Controls

| Setting | Default | Range/Options | Description |
|---------|---------|---------------|-------------|
| Proxy Mode | Residential | OFF / Residential / Datacenter | How requests are routed |
| Proxy API Key | (empty) | Text input | BrightData / Oxylabs / Smartproxy credentials |
| Session Isolation | ON | Toggle | Each browser gets completely fresh profile |
| Human Simulation Intensity | Medium | Slider: Low / Medium / High | Controls typing variance, cursor movement, micro-pauses |
| Request Cooldown | 2s | 1-10s | Minimum seconds between actions on same platform |
| Fingerprint Rotation | ON | Toggle | Rotate Canvas, WebGL, Audio, Font fingerprints per session |
| Max Concurrent Bots | 4 | 1-8 | How many browsers run in parallel (RAM dependent) |

#### Proxy Config Sub-panel
```
Provider: [BrightData] [Oxylabs] [Smartproxy] [Custom]
API Key / Credentials: [____________]
[Test Connection] button -> shows latency + IP for verification
Status: "Connected via BrightData — 12 residential IPs available"
```

---

### Module E: Live Execution Monitor (Mission Control)

This panel activates when the search begins. It slides in as the primary view, replacing the input modules (which collapse to a sidebar summary).

#### Overall Progress Bar
```
==================------  62%  —  4 of 6 platforms complete
Elapsed: 2m 34s   |   Est. Remaining: 1m 45s
```

#### Per-Bot Status Cards (Grid Layout)

Each active worker gets a live card:

```
+-------------------------------------------+
| [green dot] MakeMyTrip              2m 12s |
| Phase: Coupon Testing (8/23)               |
| Current Best: Rs.4,234 (MMTSBI500)        |
| =============---------  35%               |
|                                            |
| [View Screenshot] [View Logs] [Kill Bot]   |
+-------------------------------------------+
```

Card states:
- **Queued** — gray, pulsing border
- **Running** — indigo border glow, live progress bar
- **Done** — green border, shows final best price
- **Failed** — red border, shows error reason

#### Live Log Stream (Terminal Style)

Scrolling monospace log view (dark background, colored text):

```
[12:34:56] [MakeMyTrip] [INFO] Navigated to search results
[12:34:58] [MakeMyTrip] [INFO] Found 12 flights for DEL->BOM on Jul 15
[12:35:02] [MakeMyTrip] [INFO] Selected cheapest: IndiGo 6E-2341 Rs.4,892
[12:35:05] [MakeMyTrip] [INFO] Navigating to passenger details...
[12:35:12] [MakeMyTrip] [INFO] Filling placeholder passenger info...
[12:35:18] [MakeMyTrip] [SUCCESS] Reached checkout page
[12:35:19] [MakeMyTrip] [INFO] Starting coupon test loop (23 codes)
[12:35:22] [MakeMyTrip] [WARNING] MMTFIRST -> Invalid
[12:35:26] [MakeMyTrip] [SUCCESS] MMTSBI500 -> Rs.4,392 (SBI Card - MATCH)
[12:35:30] [MakeMyTrip] [WARNING] MMTHDFC -> Rs.4,284 (HDFC required - NO MATCH)
```

Log levels color-coded: INFO (white), SUCCESS (green), WARNING (amber), ERROR (red)

#### Screenshot Preview

Clicking "[View Screenshot]" on any bot card shows a modal with the latest browser screenshot for that session. Updated every 2 seconds during execution.

---

## 6. Data Models & Type Definitions

### 6.1 Frontend Types (TypeScript)

```typescript
// ---- Trip & Search ----

interface TripProfile {
  tripType: 'one_way' | 'round_trip';
  origin: AirportCode;           // { code: 'DEL', city: 'New Delhi' }
  destination: AirportCode;
  departureDate: string;         // 'YYYY-MM-DD'
  returnDate?: string;
  preferredTime: 'ANY' | 'EARLY_MORNING' | 'MORNING' | 'AFTERNOON' | 'EVENING' | 'NIGHT';
  passengerCount: number;
  cabinClass: 'ECONOMY' | 'PREMIUM_ECONOMY' | 'BUSINESS' | 'FIRST';
  specificFlightNumber?: string;
  flexibleDates?: { enabled: boolean; rangeDays: number; };
}

interface AirportCode {
  code: string;  // 'DEL'
  city: string;  // 'New Delhi'
}

// ---- Financial Profile ----

interface FinancialProfile {
  whitelistedBanks: string[];      // ['SBI', 'ICICI', 'HDFC']
  blacklistedBanks: string[];      // ['YES_BANK', 'JK_BANK']
  allowedCardTypes: CardType[];    // ['CREDIT', 'DEBIT', 'UPI']
  allowEMI: boolean;
  allowBNPL: boolean;
  allowWalletOffers: boolean;
  allowAppOnly: boolean;
  maxFinalPrice?: number;          // Rs.8000 cap
  customInstructions: string;      // Free-text parsed by LLM
  cardRewardRates: CardRewardRate[];
}

type CardType = 'CREDIT' | 'DEBIT' | 'NET_BANKING' | 'UPI' | 'WALLET';

interface CardRewardRate {
  bankName: string;
  cardName?: string;
  rewardRate: number;  // 0.033 for 3.3%
}

// ---- Stealth/Cloak Config ----

interface CloakConfig {
  proxyMode: 'OFF' | 'RESIDENTIAL' | 'DATACENTER';
  proxyCredentials?: ProxyCredentials;
  sessionIsolation: boolean;
  humanSimIntensity: 'LOW' | 'MEDIUM' | 'HIGH';
  requestCooldownSec: number;
  fingerprintRotation: boolean;
  maxConcurrentBots: number;
}

interface ProxyCredentials {
  provider: 'brightdata' | 'oxylabs' | 'smartproxy' | 'custom';
  host: string;
  port: number;
  username: string;
  password: string;
}

// ---- Search Schema (sent to backend) ----

interface SearchSchema {
  searchId: string;               // UUID
  trip: TripProfile;
  financial: FinancialProfile;
  platforms: string[];            // ['makemytrip', 'cleartrip', 'indigo']
  cloak: CloakConfig;
  timestamp: string;              // ISO timestamp
}

// ---- Bot Status (received from backend in real-time) ----

interface BotStatus {
  searchId: string;
  platform: string;
  phase: BotPhase;
  progress: number;               // 0-100
  currentBestPrice?: number;
  currentCouponCode?: string;
  couponsTestedCount: number;
  couponsTotalCount: number;
  startedAt: string;
  elapsedMs: number;
  error?: string;
  lastScreenshotPath?: string;
  retryCount: number;
}

type BotPhase =
  | 'queued'
  | 'initializing'
  | 'loading_site'
  | 'searching_flights'
  | 'selecting_flight'
  | 'filling_passenger_details'
  | 'skipping_addons'
  | 'navigating_to_checkout'
  | 'at_checkout'
  | 'testing_coupons'
  | 'complete'
  | 'error'
  | 'captcha_detected'
  | 'retrying';

// ---- Log Entry ----

interface BotLogEntry {
  searchId: string;
  platform: string;
  level: 'info' | 'success' | 'warning' | 'error';
  message: string;
  timestamp: string;
}

// ---- Results ----

interface SessionResult {
  platform: string;
  platformName: string;           // 'MakeMyTrip'
  flightNumber: string;
  airline: string;
  departureTime: string;
  arrivalTime: string;
  duration: string;
  stops: number;
  basePrice: number;              // Price before any coupon
  bestCouponCode: string | null;
  finalPrice: number;             // Verified checkout price after best coupon
  savings: number;                // basePrice - finalPrice
  effectivePrice?: number;        // After cashback/rewards calculation
  cashbackAmount?: number;
  sessionId: string;              // UUID for handoff
  screenshotUrl: string;          // Local path to checkout screenshot
  status: 'READY_FOR_HANDOFF' | 'SESSION_EXPIRED' | 'FAILED';
  allTestedCoupons: CouponTestResult[];
}

interface CouponTestResult {
  code: string;
  status: 'valid_match' | 'valid_but_excluded' | 'invalid' | 'pre_filtered' | 'error';
  priceAfterCoupon?: number;
  savings?: number;
  reason?: string;
  bankRequired?: string;
}

interface SearchResultSet {
  searchId: string;
  status: 'running' | 'completed' | 'partial';
  results: SessionResult[];       // Sorted by finalPrice ascending
  completedPlatforms: string[];
  failedPlatforms: { platform: string; reason: string; }[];
  bestSavings: number;            // Difference between highest and lowest finalPrice
  elapsedTime: number;            // Total milliseconds
}
```

### 6.2 Backend Models (Python / Pydantic)

```python
from pydantic import BaseModel
from typing import Optional
from enum import Enum

class TripProfile(BaseModel):
    trip_type: str                 # 'one_way' | 'round_trip'
    origin: str                   # 'DEL'
    destination: str              # 'BOM'
    departure_date: str           # '2026-07-15'
    return_date: Optional[str]
    preferred_time: str           # 'EVENING'
    passenger_count: int
    cabin_class: str              # 'ECONOMY'
    specific_flight_number: Optional[str]

class FinancialRules(BaseModel):
    whitelisted_banks: list[str]
    blacklisted_banks: list[str]
    allowed_card_types: list[str]
    allow_emi: bool
    allow_bnpl: bool
    allow_wallet_offers: bool
    allow_app_only: bool
    max_final_price: Optional[float]
    custom_instructions: str
    card_reward_rates: list[dict]

class CloakConfig(BaseModel):
    proxy_mode: str
    proxy_credentials: Optional[dict]
    session_isolation: bool
    human_sim_intensity: str      # 'LOW' | 'MEDIUM' | 'HIGH'
    request_cooldown_sec: float
    fingerprint_rotation: bool
    max_concurrent_bots: int

class TaskSchema(BaseModel):
    search_id: str
    trip: TripProfile
    financial: FinancialRules
    platforms: list[str]
    cloak: CloakConfig
    coupons_by_platform: dict[str, list[dict]]  # Pre-fetched from SQLite
    timestamp: str

class SessionResult(BaseModel):
    platform: str
    flight_number: str
    airline: str
    departure_time: str
    arrival_time: str
    base_price: float
    best_coupon: Optional[str]
    final_price: float
    savings: float
    session_id: str
    screenshot_path: str
    status: str                   # 'READY_FOR_HANDOFF'
    all_tested_coupons: list[dict]
```

---

## 7. End-to-End Processing Pipeline (Detailed)

### Phase 1: Compilation

```python
async def compile_task_schema(search_schema: dict) -> TaskSchema:
    """
    Convert raw UI inputs into a validated, immutable TaskSchema.
    - Validate all fields (raise WebSocket error before any browser launches)
    - Fetch relevant coupon codes from SQLite for each selected platform
    - Parse custom instructions through LLM to extract soft rules
    - Build proxy assignments per platform
    - Return complete TaskSchema
    """
```

**Vision API extraction prompt** (used when user uploads an image):
```
Extract all flight booking details from this image. Return ONLY valid JSON:
{
  "origin": "DEL",
  "destination": "BOM",
  "departure_date": "2026-07-15",
  "return_date": null,
  "flight_number": "6E 2341",
  "airline": "IndiGo",
  "cabin_class": "ECONOMY",
  "passenger_count": 1,
  "preferred_time": "MORNING",
  "confidence": {
    "origin": "high",
    "destination": "high",
    "departure_date": "medium",
    "flight_number": "high"
  }
}
Only include fields you can confidently extract. Set uncertain fields to null.
Use IATA codes for airports. Dates in YYYY-MM-DD format.
```

### Phase 2: Parallel Dispatch

```python
async def dispatch_all(task: TaskSchema) -> list[SessionResult]:
    """
    Launch one async worker per selected platform, up to max_concurrent_bots.
    Excess platforms are queued and dispatched as slots free up.
    """
    semaphore = asyncio.Semaphore(task.cloak.max_concurrent_bots)
    
    async def run_with_limit(platform: str):
        async with semaphore:
            proxy = proxy_manager.get_fresh_proxy(platform)
            return await run_platform_worker(platform, task, proxy)
    
    tasks = [run_with_limit(p) for p in task.platforms]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    valid_results = [r for r in results if isinstance(r, SessionResult)]
    failed = [r for r in results if isinstance(r, Exception)]
    
    # Log failures, continue with valid results
    for f in failed:
        logger.error(f"Worker failed: {f}")
        emit_ws("bot:error", {"error": str(f)})
    
    # Rank by final price
    valid_results.sort(key=lambda r: r.final_price)
    return valid_results
```

### Phase 3: Stealth Traversal (Per Worker)

Each worker performs this sequence:

1. **Launch CloakBrowser** with fresh profile directory, stealth patches, assigned proxy
2. **Apply fingerprint rotation:** Canvas noise, WebGL vendor string, User-Agent, screen resolution, timezone, language, platform
3. **Navigate to platform URL** — wait for full visual stability (not just DOM ready)
4. **Human simulation for ALL interactions:**
   - Variable typing speed: gaussian distribution centered at intensity-dependent mean
     - LOW: mean 60ms, stddev 15ms
     - MEDIUM: mean 100ms, stddev 30ms
     - HIGH: mean 140ms, stddev 40ms
   - Occasional typo + backspace correction: 5% probability per word (HIGH only)
   - Mouse movements: bezier curve paths, not teleportation
   - Random micro-scrolls during page "reading" (100-400px, random direction)
   - Wait times between actions: gaussian around cooldown mean, not fixed values

### Phase 4: Checkout Navigation

Each worker navigates through:

1. **Enter search query** — origin, destination, date using human typing
2. **Parse search results** — find target flight:
   - If specific flight number given: find that exact flight
   - Else: find cheapest flight in preferred time window
3. **Select the flight** — click with human mouse movement
4. **Passenger details page** — fill placeholder data:
   - Name: "Raj Kumar" (or configurable placeholder)
   - Age: 28
   - Email: configurable temp email from .env (`APP_TEMP_EMAIL`)
   - Phone: configurable temp phone from .env (`APP_TEMP_PHONE`)
5. **Skip ALL upsells** — insurance, meals, seat selection, priority check-in, trip protection
6. **Reach final review/payment page**
7. **Take full-page screenshot** of checkout page
8. **Emit WebSocket event:** `"bot:phase"` = `"at_checkout"` — signal ready for coupon testing

### Phase 5: Coupon Brute-Force

See Section 9 for full details.

### Phase 6: Financial Violation Filter + Aggregation

```python
def passes_financial_rules(coupon: dict, rules: FinancialRules) -> bool:
    """Pre-filter BEFORE any DOM interaction. Reject coupons that can't possibly match."""
    
    # EMI check
    if coupon.get('requires_emi') and not rules.allow_emi:
        return False
    
    # BNPL check
    if coupon.get('requires_bnpl') and not rules.allow_bnpl:
        return False
    
    # Bank blacklist check
    bank = coupon.get('bank_restriction')
    if bank and bank.upper() in [b.upper() for b in rules.blacklisted_banks]:
        return False
    
    # Bank whitelist check (if whitelist is set, only whitelisted banks pass)
    if bank and rules.whitelisted_banks:
        if bank.upper() not in [b.upper() for b in rules.whitelisted_banks]:
            return False
    
    # Card type check
    card_type = coupon.get('card_type', 'ANY')
    if card_type != 'ANY' and card_type not in rules.allowed_card_types:
        return False
    
    # Wallet check
    if coupon.get('requires_wallet') and not rules.allow_wallet_offers:
        return False
    
    # App-only check
    if coupon.get('app_only') and not rules.allow_app_only:
        return False
    
    return True
```

After all workers complete:
1. Collect all `SessionResult` objects
2. Apply max price cap filter (if set)
3. Calculate effective prices using card reward rates
4. Sort by `finalPrice` ascending (or `effectivePrice` if reward rates are configured)
5. Assign ranks (1 = cheapest)
6. Send full `SearchResultSet` to frontend via WebSocket

### Phase 7: Results Display

See Module E and Results Dashboard in Section 5. Frontend receives `SearchResultSet` and renders ranked `ResultCard` components.

---

## 8. Stealth & Anti-Detection Layer

### CloakBrowser Factory (`stealth/browser_factory.py`)

```python
async def create_cloak_browser(proxy: dict = None, cloak: CloakConfig = None) -> tuple:
    """
    Create a stealth Playwright browser with CloakBrowser patches.
    Returns (browser, context, page) tuple.
    """
    
    launch_args = [
        '--disable-blink-features=AutomationControlled',
        '--disable-features=IsolateOrigins,site-per-process',
        '--disable-site-isolation-trials',
        '--no-sandbox',
        '--disable-infobars',
        '--disable-dev-shm-usage',
        '--disable-accelerated-2d-canvas',
        '--no-first-run',
        '--no-zygote',
    ]
    
    # Launch in HEADED mode but off-screen (for handoff later)
    browser = await playwright.chromium.launch(
        headless=False,
        args=launch_args,
    )
    
    # Randomize fingerprint
    fingerprint = generate_random_fingerprint()
    
    context = await browser.new_context(
        viewport=fingerprint['viewport'],
        user_agent=fingerprint['user_agent'],
        locale='en-IN',
        timezone_id='Asia/Kolkata',
        geolocation=fingerprint['geolocation'],
        permissions=['geolocation'],
        proxy={
            'server': f"{proxy['protocol']}://{proxy['host']}:{proxy['port']}",
            'username': proxy.get('username'),
            'password': proxy.get('password'),
        } if proxy else None,
        # Move window off-screen for stealth (brought to foreground on handoff)
        screen={'width': 1920, 'height': 1080},
    )
    
    # Inject anti-detection scripts
    await context.add_init_script(JS_PATCHES)
    
    page = await context.new_page()
    
    # Move browser window off-screen
    cdp = await context.new_cdp_session(page)
    await cdp.send('Browser.setWindowBounds', {
        'windowId': 1,
        'bounds': {'left': -10000, 'top': -10000, 'width': 1280, 'height': 800}
    })
    
    return browser, context, page
```

### JavaScript Patches (`stealth/js_patches.py`)

```python
JS_PATCHES = """
// Remove webdriver flag
Object.defineProperty(navigator, 'webdriver', { get: () => false });

// Override chrome object
window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };

// Override permissions
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (params) =>
  params.name === 'notifications'
    ? Promise.resolve({ state: Notification.permission })
    : originalQuery(params);

// Override plugins
Object.defineProperty(navigator, 'plugins', {
  get: () => [
    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
    { name: 'Native Client', filename: 'internal-nacl-plugin' },
  ]
});

// Override languages
Object.defineProperty(navigator, 'languages', {
  get: () => ['en-US', 'en', 'hi']
});

// Canvas fingerprint noise
const origGetContext = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function(type, ...args) {
  const ctx = origGetContext.call(this, type, ...args);
  if (type === '2d') {
    const origGetImageData = ctx.getImageData;
    ctx.getImageData = function(...gdArgs) {
      const imageData = origGetImageData.apply(this, gdArgs);
      for (let i = 0; i < imageData.data.length; i += 4) {
        imageData.data[i] += (Math.random() * 2 - 1);  // Subtle noise
      }
      return imageData;
    };
  }
  return ctx;
};
"""
```

### Human Simulation (`human_sim.py`)

```python
import random
import math
import asyncio

class HumanSimulator:
    def __init__(self, intensity: str = 'MEDIUM'):
        self.config = {
            'LOW':    {'type_mean': 60,  'type_std': 15, 'typo_rate': 0.0},
            'MEDIUM': {'type_mean': 100, 'type_std': 30, 'typo_rate': 0.02},
            'HIGH':   {'type_mean': 140, 'type_std': 40, 'typo_rate': 0.05},
        }[intensity]
    
    async def type_text(self, page, selector, text):
        """Type text with human-like speed variance and occasional typos."""
        await page.click(selector)
        await self.random_delay(200, 500)
        
        for i, char in enumerate(text):
            # Occasional typo (only at MEDIUM/HIGH intensity)
            if random.random() < self.config['typo_rate']:
                wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
                await page.keyboard.type(wrong_char, delay=self._typing_delay())
                await self.random_delay(100, 300)
                await page.keyboard.press('Backspace')
                await self.random_delay(50, 150)
            
            await page.keyboard.type(char, delay=self._typing_delay())
    
    async def click_element(self, page, selector):
        """Click with bezier-curve mouse movement."""
        element = await page.query_selector(selector)
        box = await element.bounding_box()
        
        target_x = box['x'] + box['width'] / 2 + random.uniform(-3, 3)
        target_y = box['y'] + box['height'] / 2 + random.uniform(-3, 3)
        
        # Bezier curve movement (not teleportation)
        await self._bezier_move(page, target_x, target_y)
        await self.random_delay(50, 150)
        await page.mouse.click(target_x, target_y)
    
    async def scroll_randomly(self, page):
        """Simulate natural reading scroll behavior."""
        scroll_amount = random.randint(100, 400)
        await page.mouse.wheel(0, scroll_amount)
        await self.random_delay(500, 1500)
    
    async def random_delay(self, min_ms, max_ms):
        """Gaussian-distributed delay (more natural than uniform)."""
        mean = (min_ms + max_ms) / 2
        std = (max_ms - min_ms) / 4
        delay = max(min_ms, min(max_ms, random.gauss(mean, std)))
        await asyncio.sleep(delay / 1000)
    
    def _typing_delay(self) -> int:
        """Gaussian-distributed typing delay in ms."""
        delay = random.gauss(self.config['type_mean'], self.config['type_std'])
        return max(30, int(delay))
    
    async def _bezier_move(self, page, target_x, target_y, steps=20):
        """Move mouse along a bezier curve to target position."""
        # Get current position (approximate)
        start_x = random.uniform(100, 500)
        start_y = random.uniform(100, 500)
        
        # Random control points for bezier curve
        cp1_x = start_x + random.uniform(-100, 100)
        cp1_y = start_y + random.uniform(-100, 100)
        cp2_x = target_x + random.uniform(-100, 100)
        cp2_y = target_y + random.uniform(-100, 100)
        
        for i in range(steps + 1):
            t = i / steps
            x = (1-t)**3 * start_x + 3*(1-t)**2*t * cp1_x + 3*(1-t)*t**2 * cp2_x + t**3 * target_x
            y = (1-t)**3 * start_y + 3*(1-t)**2*t * cp1_y + 3*(1-t)*t**2 * cp2_y + t**3 * target_y
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.005, 0.02))
```

---

## 9. Coupon Brute-Force Engine

### Coupon Database Schema

```sql
CREATE TABLE coupons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,              -- 'makemytrip', 'cleartrip', etc.
    code TEXT NOT NULL,
    description TEXT,                    -- 'Flat Rs.500 off on SBI Credit Cards'
    bank_restriction TEXT,               -- 'SBI', 'HDFC', NULL = universal
    card_type TEXT DEFAULT 'ANY',        -- 'CREDIT', 'DEBIT', 'ANY'
    requires_emi BOOLEAN DEFAULT 0,
    requires_bnpl BOOLEAN DEFAULT 0,
    requires_wallet BOOLEAN DEFAULT 0,
    app_only BOOLEAN DEFAULT 0,
    discount_type TEXT,                  -- 'FLAT', 'PERCENT', 'CASHBACK'
    discount_value REAL,                 -- 500 or 10 (for percent)
    max_discount REAL,                   -- Cap for percentage discounts
    min_booking_value REAL,              -- Minimum transaction to qualify
    valid_from DATE,
    valid_until DATE,
    is_active BOOLEAN DEFAULT 1,
    source TEXT DEFAULT 'manual',        -- 'manual', 'scraped', 'user'
    last_verified DATE,
    success_rate REAL DEFAULT 0.5,       -- 0.0 to 1.0, updated after each test
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, code)
);

CREATE INDEX idx_coupons_platform ON coupons(platform);
CREATE INDEX idx_coupons_active ON coupons(is_active);
```

### Coupon Auto-Refresh Sources

Weekly background scraper that pulls codes from:
1. **Platform official offer pages** — makemytrip.com/offers/flights, cleartrip.com/offers, etc.
2. **Coupon aggregator sites** — GrabOn, CouponDunia, CashKaro, DesiDime
3. **Bank offer pages** — SBI Card offers, ICICI offers, HDFC offers
4. Never overwrites existing codes — only adds new ones, marks expired ones

### Brute-Force Loop

```python
async def brute_force_coupons(
    page,
    platform_worker,        # The platform-specific worker instance
    coupons: list[dict],
    financial_rules: FinancialRules,
    search_id: str
) -> dict:
    """
    Test all applicable coupons at the checkout page.
    Returns the best valid result.
    """
    results = []
    baseline_price = await platform_worker.parse_current_price(page)
    best_price = baseline_price
    best_coupon = None
    
    # Sort by expected discount value (highest first — test best candidates first)
    sorted_coupons = sorted(coupons, key=lambda c: c.get('discount_value', 0), reverse=True)
    
    for i, coupon in enumerate(sorted_coupons):
        # --- PRE-FILTER (no DOM interaction) ---
        if not passes_financial_rules(coupon, financial_rules):
            emit_log(search_id, platform_worker.name, 'info',
                     f"Skipping {coupon['code']} — pre-filter reject")
            results.append({
                'code': coupon['code'],
                'status': 'pre_filtered',
                'reason': 'Financial profile mismatch'
            })
            continue
        
        try:
            # 1. Clear any existing coupon
            await platform_worker.clear_coupon_field(page)
            await human.random_delay(300, 800)
            
            # 2. Type coupon code with human-like speed
            await human.type_text(page, platform_worker.coupon_selector, coupon['code'])
            await human.random_delay(200, 500)
            
            # 3. Click "Apply"
            await platform_worker.click_apply_coupon(page)
            
            # 4. Wait for DOM update (AJAX price recalculation)
            await page.wait_for_timeout(3000)
            
            # 5. Check if coupon was accepted
            applied = await platform_worker.check_coupon_applied(page)
            
            if not applied['success']:
                emit_log(search_id, platform_worker.name, 'warning',
                         f"{coupon['code']} -> Invalid ({applied.get('error', 'N/A')})")
                results.append({
                    'code': coupon['code'],
                    'status': 'invalid',
                    'reason': applied.get('error', 'Not applicable')
                })
                # Update success rate down
                update_coupon_stats(coupon['id'], success=False)
                continue
            
            # 6. Coupon applied! Parse new price
            new_price = await platform_worker.parse_current_price(page)
            
            # 7. Parse validation/restriction text shown on page
            restriction_text = await platform_worker.get_coupon_validation_text(page)
            
            # 8. Double-check restriction text against financial rules
            #    (catches cases where DOM accepted coupon but it requires a blacklisted bank)
            if contains_financial_violation(restriction_text, financial_rules):
                emit_log(search_id, platform_worker.name, 'warning',
                         f"{coupon['code']} -> Rs.{new_price} but violates financial rules — SKIPPED")
                results.append({
                    'code': coupon['code'],
                    'status': 'valid_but_excluded',
                    'price': new_price,
                    'reason': f'Restriction: {restriction_text}'
                })
                await platform_worker.clear_coupon_field(page)
                continue
            
            # 9. Valid and usable!
            savings = baseline_price - new_price
            emit_log(search_id, platform_worker.name, 'success',
                     f"{coupon['code']} -> Rs.{new_price} MATCH! (Save Rs.{savings})")
            
            results.append({
                'code': coupon['code'],
                'status': 'valid_match',
                'price': new_price,
                'savings': savings,
            })
            
            # Update success rate up
            update_coupon_stats(coupon['id'], success=True)
            
            if new_price < best_price:
                best_price = new_price
                best_coupon = coupon['code']
                # Keep this coupon applied — it's our current best
            else:
                # Not better, clear it and keep the previous best applied
                await platform_worker.clear_coupon_field(page)
                # Re-apply the current best
                if best_coupon:
                    await human.type_text(page, platform_worker.coupon_selector, best_coupon)
                    await platform_worker.click_apply_coupon(page)
                    await page.wait_for_timeout(2000)
        
        except Exception as e:
            emit_log(search_id, platform_worker.name, 'error',
                     f"{coupon['code']} -> Error: {str(e)}")
            results.append({
                'code': coupon['code'],
                'status': 'error',
                'reason': str(e)
            })
        
        # Emit progress update
        emit_ws("bot:status", {
            'searchId': search_id,
            'platform': platform_worker.platform_id,
            'phase': 'testing_coupons',
            'progress': int((i + 1) / len(sorted_coupons) * 100),
            'currentBestPrice': best_price,
            'currentCouponCode': best_coupon,
            'couponsTestedCount': i + 1,
            'couponsTotalCount': len(sorted_coupons),
        })
        
        # Random delay between tests to avoid detection
        await human.random_delay(1000, 3000)
    
    return {
        'baseline_price': baseline_price,
        'best_price': best_price,
        'best_coupon': best_coupon,
        'savings': baseline_price - best_price,
        'all_results': results
    }
```

---

## 10. The Foreground Handoff System

### Architecture

All browsers run in **headed mode** (not headless) but positioned **off-screen** (`x: -10000, y: -10000`). This means:
- Each browser session is a real OS-level window
- We take periodic screenshots for the monitoring UI
- On handoff, we simply move the window to center screen
- No headless-to-headed conversion needed (which is unreliable)

### Handoff Flow

```python
# session_manager.py

async def handoff_to_user(session_id: str):
    """
    Bring the checkout browser session to the foreground.
    The user completes payment in the real browser.
    """
    session = session_pool.get(session_id)
    if not session or session['status'] != 'READY_FOR_HANDOFF':
        raise ValueError(f"Session {session_id} not available for handoff")
    
    page = session['page']
    
    # 1. Move browser window to center of screen
    cdp = await session['context'].new_cdp_session(page)
    await cdp.send('Browser.setWindowBounds', {
        'windowId': session['window_id'],
        'bounds': {
            'left': 320,   # Centered on 1920px screen
            'top': 140,    # Centered on 1080px screen
            'width': 1280,
            'height': 800,
            'windowState': 'normal'
        }
    })
    
    # 2. Focus the window (platform-specific)
    # Windows: use pywin32
    if sys.platform == 'win32':
        import win32gui
        hwnd = session.get('hwnd')
        if hwnd:
            win32gui.SetForegroundWindow(hwnd)
    
    # 3. Update session status
    session['status'] = 'HANDED_OFF'
    session['handoff_time'] = datetime.utcnow().isoformat()
    
    # 4. Notify frontend
    emit_ws("session:handoff", {
        'sessionId': session_id,
        'status': 'success',
        'message': 'Browser session is now in your foreground. Complete your payment.'
    })
    
    # 5. Start session timeout watchdog (15 minutes)
    asyncio.create_task(session_timeout_watchdog(session_id, timeout_minutes=15))
    
    # 6. Monitor for browser close
    page.on('close', lambda: handle_session_closed(session_id))


async def session_timeout_watchdog(session_id: str, timeout_minutes: int):
    """Warn user before session expires."""
    await asyncio.sleep((timeout_minutes - 2) * 60)  # Warn 2 min before
    emit_ws("session:warning", {
        'sessionId': session_id,
        'message': f'Session expires in 2 minutes. Complete payment soon.'
    })
    await asyncio.sleep(2 * 60)
    emit_ws("session:expired", {
        'sessionId': session_id,
        'message': 'Session has expired. You may need to re-run the search.'
    })
```

> [!IMPORTANT]
> **The user NEVER enters payment information into our application.** The handoff gives them direct control of a standard browser window on the real booking platform's website. Our app's job is done at this point.

---

## 11. Database Schemas

### Full SQLite Schema (`backend/db/schema.sql`)

```sql
-- Coupon Codes (see Section 9 for full definition)
-- ... (defined above)

-- Search History
CREATE TABLE searches (
    id TEXT PRIMARY KEY,                   -- UUID
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    departure_date TEXT NOT NULL,
    return_date TEXT,
    passenger_count INTEGER DEFAULT 1,
    cabin_class TEXT DEFAULT 'ECONOMY',
    platforms TEXT,                         -- JSON array: ['makemytrip', 'cleartrip']
    status TEXT DEFAULT 'pending',          -- pending, running, completed, failed
    started_at TEXT,
    completed_at TEXT,
    total_duration_ms INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Search Results
CREATE TABLE search_results (
    id TEXT PRIMARY KEY,                   -- UUID
    search_id TEXT NOT NULL REFERENCES searches(id),
    platform TEXT NOT NULL,
    flight_number TEXT,
    airline TEXT,
    departure_time TEXT,
    arrival_time TEXT,
    duration TEXT,
    stops INTEGER DEFAULT 0,
    base_price REAL,                       -- Before coupon
    final_price REAL,                      -- After best coupon
    best_coupon_code TEXT,
    savings REAL,
    effective_price REAL,                  -- After cashback calculation
    all_tested_coupons TEXT,               -- JSON array of CouponTestResult
    session_id TEXT,                       -- For handoff reference
    rank INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Price History (for trend tracking)
CREATE TABLE price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route TEXT NOT NULL,                   -- 'DEL-BOM'
    departure_date TEXT NOT NULL,
    airline TEXT,
    flight_number TEXT,
    price REAL NOT NULL,
    platform TEXT NOT NULL,
    cabin_class TEXT DEFAULT 'ECONOMY',
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_price_route ON price_history(route, departure_date);

-- Watchlist (for price alerts)
CREATE TABLE watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    departure_date TEXT NOT NULL,
    target_price REAL,                     -- Alert when price drops below
    check_frequency TEXT DEFAULT 'daily',  -- 'hourly', 'daily', 'weekly'
    last_checked TEXT,
    last_price REAL,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Browser Sessions (Redis-backed at runtime, SQLite for persistence)
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,                   -- UUID
    search_id TEXT REFERENCES searches(id),
    platform TEXT NOT NULL,
    status TEXT DEFAULT 'active',          -- active, ready_for_handoff, handed_off, expired, closed
    browser_pid INTEGER,
    window_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    handoff_at TEXT,
    expires_at TEXT
);
```

---

## 12. WebSocket API Contract

All communication between Electron/React frontend and Python FastAPI backend flows through a single WebSocket connection at `ws://localhost:8765`.

### Messages: Frontend -> Backend

```typescript
// Start a new flight search
{ type: 'search:start', payload: SearchSchema }

// Cancel a running search
{ type: 'search:cancel', payload: { searchId: string } }

// Request foreground handoff for a specific session
{ type: 'session:handoff', payload: { sessionId: string } }

// Check if a session is still alive
{ type: 'session:check', payload: { sessionId: string } }

// Upload image for AI extraction
{ type: 'ai:extract', payload: { imageBase64: string } }

// Get all coupons for a platform
{ type: 'coupon:list', payload: { platform: string } }

// Add a custom coupon code
{ type: 'coupon:add', payload: { platform: string, code: string, ... } }

// Trigger coupon database refresh (scrape latest)
{ type: 'coupon:refresh', payload: { platforms?: string[] } }

// Get/set user profile
{ type: 'settings:get', payload: {} }
{ type: 'settings:update', payload: FinancialProfile }

// Test proxy connectivity
{ type: 'proxy:test', payload: ProxyCredentials }

// Get price history for a route
{ type: 'history:get', payload: { route: string, days: number } }

// Watchlist operations
{ type: 'watchlist:add', payload: { origin, destination, date, targetPrice } }
{ type: 'watchlist:remove', payload: { watchId: number } }
{ type: 'watchlist:list', payload: {} }
```

### Messages: Backend -> Frontend (Real-Time Events)

```typescript
// Bot status update (emitted frequently during execution)
{ type: 'bot:status', payload: BotStatus }

// Log entry for the live terminal
{ type: 'bot:log', payload: BotLogEntry }

// Screenshot update (every 2 seconds per active bot)
{ type: 'bot:screenshot', payload: { searchId, platform, imageBase64, timestamp } }

// Search completed — final results
{ type: 'search:results', payload: SearchResultSet }

// Search error
{ type: 'search:error', payload: { searchId, error: string } }

// AI extraction result
{ type: 'ai:result', payload: ExtractedTripDetails }

// Session handoff confirmation
{ type: 'session:handoff:ack', payload: { sessionId, status, message } }

// Session warnings
{ type: 'session:warning', payload: { sessionId, message } }
{ type: 'session:expired', payload: { sessionId, message } }

// Coupon refresh status
{ type: 'coupon:refresh:done', payload: { added: number, updated: number } }

// Price alert notification
{ type: 'watchlist:alert', payload: { watchId, route, currentPrice, targetPrice } }
```

---

## 13. Additional Features

### 13.1 Price History & Trend Tracker
- Every search result is logged to `price_history` table
- Results cards show a sparkline graph: "This route 7-day trend"
- Alert badge if today's price is unusually high/low vs. historical average
- Full chart view accessible from a "History" tab showing 30/60/90 day trends
- Simple trend indicator: "Prices RISING for this route" or "DROPPING — wait 2-3 days"

### 13.2 Scheduled Auto-Scout (Watchlist)
- User saves: "Check DEL->BOM every day at 9am for 2 weeks"
- Agent runs silently in background, sends desktop notification when price drops below threshold
- Full history log viewable in "Watchlist" tab
- Each watchlist entry shows: last checked price, trend arrow, days remaining

### 13.3 Coupon Database Self-Updating
- Weekly background scraper pulling from GrabOn, CouponDunia, CashKaro, DesiDime
- Also scrapes each platform's own /offers page
- Never overwrites — only adds new codes, marks expired ones
- User can trigger manual refresh from UI

### 13.4 Smart Session Resume (CAPTCHA Handling)
- If bot hits CAPTCHA mid-session: pause worker, take screenshot, send notification
- UI shows: "CAPTCHA detected on [Platform]. Solve it manually or skip?"
- If user clicks "Solve Manually": handoff browser to user for CAPTCHA solve only
- After manual solve: bot automatically resumes from where it left off
- If user clicks "Skip": mark platform as failed, continue with others

### 13.5 Flexible Date Mode (+/-3 Days)
- When enabled, agent runs lightweight front-page-only searches across 7 dates
- Displays a calendar heatmap: each day color-coded green (cheap) to red (expensive)
- User clicks a specific day to run the full deep checkout search on that date
- Shows: "Flying Tuesday instead of Friday saves ~Rs.1,200"

### 13.6 Effective Price Calculator (Cashback + Rewards)
- User inputs card reward rates in Module C (e.g., "HDFC Infinia: 3.3% on travel")
- After coupon testing, calculate: `effectivePrice = finalPrice - (finalPrice * rewardRate)`
- Results show both "Checkout Price" and "Effective Price (after rewards)"
- This can flip rankings — Rs.4,500 with 5% back beats Rs.4,400 with 0%

### 13.7 Multi-Coupon Stacking Detection
- After finding best single coupon, check if bank offers stack on top
- Some platforms have separate "Bank Offer" checkboxes that apply additively
- Test combinations: Best Coupon + each Bank Offer
- Flag in results: "Rs.4,200 = MMTFLY (Rs.300 off) + SBI Offer (Rs.392 off)"

### 13.8 Session Replay (Audit Trail)
- Take screenshot every 2 seconds during execution (stored in `sessions/{uuid}/screenshots/`)
- Build flipbook-style "video player" in UI that scrubs through screenshots
- Store full action log (click targets, typed text, URLs visited) as structured JSON
- Useful for: debugging failed scrapers, understanding what the bot did, trust

### 13.9 Export & Share
- Export any result card as PDF with: platform, flight, route, price breakdown, coupon used
- One-click copy of: "Platform + Flight + Price + Coupon Code" as formatted text
- Share via WhatsApp deep link (pre-formatted message)

### 13.10 Baggage Cost Normalizer
- User sets default baggage preference: "I always check 15kg"
- When comparing IndiGo (no free baggage) vs Air India (15kg included):
  - Auto-add IndiGo's baggage fee to its price
  - Show: "IndiGo: Rs.4,200 base + Rs.800 baggage = Rs.5,000" vs "Air India: Rs.4,800 all-in"
- Prevents false "cheapest" rankings from bare-bones fares

---

## 14. Security & Privacy Model

> [!CAUTION]
> This application handles sensitive financial metadata (bank names, card preferences). Security is non-negotiable.

1. **ALL data stays local.** Zero network calls except to:
   - Target booking websites (via stealth browsers)
   - Coupon aggregator sites (for scraping)
   - OpenAI/Gemini API (only trip details sent — NEVER financial data)
   - Proxy servers (for network routing)

2. **No payment data storage.** App never sees, stores, or transmits card numbers, CVVs, or OTPs.

3. **AI API calls are sanitized.** When sending to GPT-4o/Gemini:
   - Strip all personal financial details
   - Only send: image content, trip details, coupon text
   - Never send: bank names, card info, payment preferences

4. **Local SQLite encryption.** Database file encrypted at rest using SQLCipher.

5. **Proxy credentials.** Stored in `.env` file, never logged or transmitted.

6. **Logging.** Log files never contain: financial profile data, proxy passwords, API keys.

---

## 15. Error Handling & Resilience

### Platform-Level Errors

| Scenario | Response |
|----------|----------|
| Platform down / unreachable | Mark "Unavailable", skip, continue with others |
| CAPTCHA detected | Pause bot, screenshot to UI, offer "Solve Manually" or "Skip" |
| Anti-bot block (403/429) | Retry with fresh proxy + fingerprint (up to 3 attempts) |
| Session expired during coupon testing | Re-navigate to checkout, resume from last tested coupon |
| Flight sold out at checkout | Report "Price Changed / Sold Out" in results |
| Unexpected page layout change | Log full HTML for debugging, flag "Scraper Needs Update" |
| Coupon field not found | Try fallback CSS selectors, flag if all fail |
| Browser crash | Auto-restart with fresh context, retry from beginning |

### System-Level Errors

| Scenario | Response |
|----------|----------|
| Out of memory (too many browsers) | Queue platforms, run in batches (concurrency limiter) |
| Network failure (user's internet drops) | Pause all bots, auto-resume when network returns |
| Proxy pool exhausted | Fall back to direct connection with warning to user |
| AI API rate limit / failure | Fall back to regex-based image parsing |
| Redis unavailable | Fall back to in-memory dict for session state |
| SQLite corruption | Auto-backup before each search, restore on corruption |

### Key Rules

1. **One crashed worker NEVER kills the whole run.** Each worker is isolated via asyncio exception handling.
2. **All errors are logged** with timestamps to rotating log files under `logs/`.
3. **Retry budget:** Each worker gets 3 retry attempts with exponential backoff.
4. **Graceful degradation:** If non-critical features fail (history, rewards calc), core search continues.

---

## 16. Testing Strategy

### Unit Tests (Python - pytest)
- `financial_filter.py` — test all rule matching scenarios
- `coupon_db.py` — CRUD operations, expiry logic
- `compiler.py` — TaskSchema validation and compilation
- `human_sim.py` — delay distributions, bezier math

### Integration Tests
- Full worker flow against saved HTML snapshots (not live sites)
- Coupon brute-force loop with mock page responses
- WebSocket message contract verification
- SQLite schema creation + migration

### E2E Tests (Manual)
- Full search flow: UI input -> progress dashboard -> results -> handoff
- Image upload -> AI extraction -> field population
- CAPTCHA pause/resume flow
- Session timeout and expiry

### Scraper Health Checks
- Each worker implements a `health_check()` method
- Verifies CSS selectors still work against the live site
- Run before dispatching — skip unhealthy workers with warning

---

## 17. Environment & Configuration

### `.env.example`

```env
# ── Vision AI ──
OPENAI_API_KEY=sk-...
# OR for local/offline: VISION_PROVIDER=ollama

# ── Proxy Provider (choose one) ──
PROXY_PROVIDER=brightdata
BRIGHTDATA_HOST=brd.superproxy.io
BRIGHTDATA_PORT=22225
BRIGHTDATA_USERNAME=...
BRIGHTDATA_PASSWORD=...

# OR
# PROXY_PROVIDER=oxylabs
# OXYLABS_USERNAME=...
# OXYLABS_PASSWORD=...

# ── App Config ──
APP_TEMP_EMAIL=test@yourdomain.com
APP_TEMP_PHONE=9999999999
APP_TEMP_NAME=Raj Kumar
SESSION_TIMEOUT_MINUTES=15
MAX_CONCURRENT_BOTS=4
LOG_LEVEL=INFO

# ── Coupon Auto-Refresh ──
COUPON_REFRESH_DAY=sunday
COUPON_REFRESH_HOUR=3

# ── Redis ──
REDIS_URL=redis://localhost:6379/0

# ── WebSocket ──
WS_HOST=localhost
WS_PORT=8765
```

### `backend/requirements.txt`

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
websockets==12.0
playwright==1.45.0
playwright-stealth==1.0.6
aiohttp==3.9.5
aiosqlite==0.20.0
pillow==10.4.0
openai==1.40.0
pydantic==2.8.2
python-dotenv==1.0.1
redis[hiredis]==5.0.7
beautifulsoup4==4.12.3
lxml==5.2.2
schedule==1.2.2
loguru==0.7.2
pywin32==306; sys_platform == "win32"
pyobjc==10.3.1; sys_platform == "darwin"
```

### `frontend/package.json` (key dependencies)

```json
{
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "zustand": "^4.5.0",
    "framer-motion": "^11.0.0",
    "recharts": "^2.12.0",
    "lucide-react": "^0.400.0",
    "@radix-ui/react-dialog": "^1.1.0",
    "@radix-ui/react-dropdown-menu": "^2.1.0",
    "@radix-ui/react-switch": "^1.1.0",
    "@radix-ui/react-slider": "^1.2.0",
    "@radix-ui/react-tabs": "^1.1.0"
  },
  "devDependencies": {
    "typescript": "^5.5.0",
    "vite": "^5.4.0",
    "tailwindcss": "^4.0.0",
    "@tailwindcss/vite": "^4.0.0",
    "autoprefixer": "^10.4.0"
  }
}
```

---

## 18. Build Order & Phasing

> [IMPORTANT]
> Build in this exact order. Each phase must be functional and tested before proceeding to the next.

### Phase 1: Foundation (Start Here)
```
[ ] Set up Electron + React + Vite project with TypeScript
[ ] Set up Python FastAPI backend with WebSocket server
[ ] Establish WebSocket IPC between Electron and FastAPI
[ ] Build basic dark-theme UI shell (navbar, sidebar, layout)
[ ] Build Module A UI (flight intent form with airport autocomplete)
[ ] Build Module B UI (platform grid, toggleable cards)
[ ] Set up SQLite database with schema + Drizzle/aiosqlite
[ ] Implement settings persistence (user_profile.json)
```

### Phase 2: Core Engine
```
[ ] Build CloakBrowser factory (stealth/browser_factory.py)
[ ] Implement human simulation module (human_sim.py)
[ ] Build proxy manager (proxy_manager.py)
[ ] Create abstract base_worker.py with full interface
[ ] Implement MakeMyTrip worker (reference implementation)
[ ] Build parallel dispatcher with asyncio semaphore
[ ] Wire WebSocket progress streaming to frontend
[ ] Build Module E: Live Execution Monitor UI
```

### Phase 3: Intelligence Layer
```
[ ] Build Module C: Financial Rules Engine UI
[ ] Implement financial_filter.py
[ ] Seed coupon database with initial data for all platforms
[ ] Implement coupon brute-force loop (coupon_brute_forcer.py)
[ ] Build Results Ranker UI + ResultCard components
[ ] Implement result aggregation, filtering, and ranking
```

### Phase 4: Handoff + Vision
```
[ ] Implement session_manager.py (Redis-backed session pool)
[ ] Build foreground browser handoff (window manager)
[ ] Build "Book Now" flow: UI -> WebSocket -> handoff -> user control
[ ] Implement session timeout watchdog
[ ] Integrate GPT-4o Vision API (vision_intake.py)
[ ] Build AI Visual Intake drop zone in Module A
[ ] Implement LLM-powered coupon rule text analysis
```

### Phase 5: Anti-Detection (Module D)
```
[ ] Build Module D: Cloak Settings UI
[ ] Integrate residential proxy provider SDK
[ ] Implement fingerprint rotation (Canvas, WebGL, Audio, Font)
[ ] Build CAPTCHA pause-and-resume flow
[ ] Tune human simulation parameters per platform
```

### Phase 6: Remaining Platform Workers
```
[ ] EaseMyTrip worker
[ ] Cleartrip worker
[ ] IndiGo (goindigo.in) worker
[ ] Air India worker
[ ] Akasa Air worker
[ ] Yatra worker
[ ] ixigo worker
[ ] SpiceJet worker
```

### Phase 7: Advanced Features
```
[ ] Price history tracker + sparkline charts
[ ] Watchlist + scheduled auto-scout
[ ] Coupon database self-updater (weekly scraper)
[ ] Flexible date mode (+/-3 days) + calendar heatmap
[ ] Effective price calculator (cashback/rewards)
[ ] Multi-coupon stacking detection
[ ] Session replay viewer (screenshot flipbook)
[ ] Export/share (PDF, clipboard, WhatsApp)
[ ] Baggage cost normalizer
```

### Phase 8: Polish & Packaging
```
[ ] Comprehensive error handling for all edge cases
[ ] Performance optimization (memory management for browsers)
[ ] Database encryption (SQLCipher)
[ ] Electron auto-updater
[ ] PyInstaller packaging for Python backend
[ ] Electron Builder packaging for desktop app
[ ] First-run onboarding flow
[ ] Full test suite (unit + integration)
```

---

## Appendix A: Platform Worker Interface

Every worker must implement this abstract base class:

```python
# workers/base_worker.py
from abc import ABC, abstractmethod

class BaseWorker(ABC):
    """Abstract base class for all platform-specific workers."""
    
    @property
    @abstractmethod
    def platform_id(self) -> str: ...          # 'makemytrip'
    
    @property
    @abstractmethod
    def platform_name(self) -> str: ...        # 'MakeMyTrip'
    
    @property
    @abstractmethod
    def base_url(self) -> str: ...             # 'https://www.makemytrip.com'
    
    @property
    @abstractmethod
    def coupon_selector(self) -> str: ...      # CSS selector for coupon input field
    
    # ── Search Phase ──
    @abstractmethod
    async def navigate_to_search(self, page) -> None: ...
    @abstractmethod
    async def input_search_criteria(self, page, trip: TripProfile) -> None: ...
    @abstractmethod
    async def execute_search(self, page) -> None: ...
    @abstractmethod
    async def parse_search_results(self, page) -> list[dict]: ...
    @abstractmethod
    async def select_flight(self, page, flight: dict) -> None: ...
    
    # ── Passenger Details Phase ──
    @abstractmethod
    async def fill_passenger_details(self, page) -> None: ...
    @abstractmethod
    async def skip_addons(self, page) -> None: ...
    @abstractmethod
    async def proceed_to_checkout(self, page) -> None: ...
    
    # ── Checkout Phase ──
    @abstractmethod
    async def is_at_checkout(self, page) -> bool: ...
    @abstractmethod
    async def parse_current_price(self, page) -> float: ...
    @abstractmethod
    async def enter_coupon_code(self, page, code: str) -> None: ...
    @abstractmethod
    async def click_apply_coupon(self, page) -> None: ...
    @abstractmethod
    async def check_coupon_applied(self, page) -> dict: ...
    @abstractmethod
    async def get_coupon_validation_text(self, page) -> str: ...
    @abstractmethod
    async def clear_coupon_field(self, page) -> None: ...
    
    # ── Utility ──
    @abstractmethod
    async def detect_captcha(self, page) -> bool: ...
    @abstractmethod
    async def health_check(self, page) -> bool: ...
```

---

## Appendix B: Critical Implementation Rules

> [WARNING]
> **Read these before writing ANY code.**

1. **Payment data NEVER enters the app.** Only facilitates navigation. All payment = user in surfaced browser.

2. **Sessions must be isolated.** No shared cookies, localStorage, cache, or profiles between workers. Ever.

3. **Fail gracefully.** One crashed worker never crashes the whole run. `asyncio.gather(*tasks, return_exceptions=True)`.

4. **Price is ground truth.** Never trust listing price. Only trust the number on the final payment page after all fees/taxes.

5. **Coupon pre-filtering first.** Always run `passes_financial_rules()` BEFORE any DOM interaction. Only DOM-test coupons that pass pre-filter.

6. **Session handoff is sacred.** Once a browser is "READY_FOR_HANDOFF", nothing else touches it. No polling, no re-navigation. It waits for the user.

7. **Log everything.** Every action with timestamps to rotating log files. Essential for debugging.

8. **Scraper selectors WILL break.** Use resilient selectors (data-attributes > class names > XPath). Implement fallback chains. Log full HTML on selector failure.

9. **Memory management.** Each Chromium ~100-300MB RAM. Enforce concurrency limit. Kill sessions that aren't needed.

10. **India-specific:**
    - IATA airport codes (DEL, BOM, BLR, HYD, CCU, MAA, GOI, etc.)
    - Currency: INR, format Rs.4,234 (Indian comma: 1,00,000)
    - Timezone: Asia/Kolkata (IST) only
    - Placeholder phone: +91 9XXXXXXXXX format
    - Placeholder names: Indian-sounding (Raj Kumar, Priya Sharma)

---

*This document is the single source of truth. Build this. Every module, every phase, every constraint is intentional. When in doubt, refer to Section 1 — the goal is to find the real lowest checkout price and hand the user a live browser session to complete payment.*

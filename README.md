# Flight Finder & Savings Optimizer

An AI-powered travel intelligence web application built with a FastAPI backend and a React (Vite) frontend. The system evaluates real-time flight search results, applies coupon rules and payment reward rates to calculate the *True Cost* of fares, and runs a 3-layer ensemble ML/RAG model to recommend booking windows and savings alternatives.

---

## 🚀 Architecture & Technical Highlights

1. **Rs. 0 Budget Scraping & Data Ingestion**:
   - Uses Camoufox (a hardened anti-detect browser based on Firefox) via the custom modular stealth scraper.
   - Mimics human behaviors (Bezier mouse curve movements, human typing delays) and runs requests with randomized user agents and dynamic viewport sizes.
2. **Modular Reusable Tools (`/modular_tools`)**:
   - Designed to be 100% modular and independent. You can copy these folders directly into other automation/ML projects.
   - **`stealth_scraper/`**: General Camoufox stealth browser wrapper with human simulation and proxy fallbacks.
   - **`macro_feeds/`**: Fetches exchange rates (USD/INR), commodity indexes (Brent Crude), and regional holiday calendars via yfinance, feedparser, and python-holidays.
   - **`ml_forecaster/`**: Prophet time-series model fit/predict engine and XGBoost tabular model driver analyzer with permutation feature analysis.
   - **`rag_advisor/`**: ChromaDB RAG advisor which parses local JSON knowledge bases and connects to Gemini 1.5 Flash (free tier), GPT-4o, or local Ollama.
3. **True Cost Calculation**:
   - Automatically harvests and brute-forces discount codes.
   - Subtracts payment portal cashbacks and credit card reward rates (e.g. HDFC SmartBuy, SBI Card) configured in User Settings.
4. **AI Savings Optimizer**:
   - Instead of hiding layovers or alternatives based on arbitrary hardcoded filters, the system calculates the **Implied Hourly Savings Rate** for layovers, date shifts, and airport shifts (e.g., Goa Mopa GOX vs Dabolim GOI, Hindon HND vs Delhi DEL). It presents these alternatives to you, leaving the final valuation of time vs. money completely in your control.

---

## 📂 Project Structure

```
Flight Finder/
├── modular_tools/            # 100% Reusable Modular Codebases
│   ├── stealth_scraper/      # Stealth browser automation (Camoufox)
│   ├── macro_feeds/          # yfinance macro feeds (crude oil, USDINR, holidays)
│   ├── ml_forecaster/        # Prophet & XGBoost Ensemble prediction
│   └── rag_advisor/          # Local ChromaDB and Multi-LLM RAG connector
├── backend/                  # FastAPI Web + WebSocket API Server
│   ├── db/                   # Database models, schema, and seeding script
│   ├── predictor/            # RAG Knowledge base, historical CSV dataset, and ensemble rules
│   ├── main.py               # Main entry point (FastAPI server)
│   ├── price_predictor.py    # AI Savings Optimizer & 3-layer predictor coordinator
│   └── requirements.txt      # Python dependencies
├── frontend/                 # React Frontend
│   ├── src/
│   │   ├── components/       # UI (Cockpit, PriceHistory, ResultsRanker)
│   │   ├── store/            # Zustand state management
│   │   └── types.ts          # TypeScript type definitions
│   └── package.json          # Node dependencies
└── README.md                 # Setup & Run documentation
```

---

## 🛠️ Setup & Execution

### 1. Prerequisite: Seeding the Database
To avoid cold start issues (where forecasting models lack enough training samples), seed the SQLite database with 2,700 price observations:
```powershell
cd backend
.\venv\Scripts\python.exe db/seed_history.py
```
This initializes the database at `backend/db/flight_agent.db` and populates the `observed_prices` and `price_history` tables.

### 2. Run the FastAPI Backend
Start the FastAPI server on port `8765`:
```powershell
cd backend
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8765 --reload
```

### 3. Run the Frontend Development Server
Start the Vite dev server (usually serves on port `5173`):
```powershell
cd frontend
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 🧪 Running Automated Tests
Verify that all ML forecasters, cyclical date encodings, rules engine overrides, and RAG advisors function properly:
```powershell
cd backend
.\venv\Scripts\pytest.exe
```

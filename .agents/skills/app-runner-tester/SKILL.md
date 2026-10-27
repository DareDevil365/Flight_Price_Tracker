---
name: app-runner-tester
description: "Use when starting app servers or running Python tests."
---

# Runtime and tests

Run ./start.ps1 -NoBrowser from the root, or backend/.venv/Scripts/python.exe main.py from backend/. Frontend uses npm run dev -- --host 127.0.0.1 --port 5173 --strictPort. Do not use the obsolete backend/venv or Uvicorn --reload on Windows: Playwright requires a subprocess-capable asyncio loop.

Run all backend tests before finalizing, with temporary database/profile/model locations for legacy suites. Run npm run build and npm run lint from frontend/. Live smoke tests: backend/tools/validate_live_routes.py exercises the running WebSocket app; backend/tools/probe_live.py inspects public provider pages. Never fill real passenger/payment data or purchase tickets during validation.

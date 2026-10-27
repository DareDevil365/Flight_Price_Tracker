---
name: stealth-scraper-troubleshooter
description: "Use when debugging public provider browser searches."
---

# Provider diagnostics

Use backend/tools/probe_live.py with provider IDs and PROBE_ORIGIN, PROBE_DEST, PROBE_DATE, PROBE_ADULTS, PROBE_CABIN. Page HTML/text/screenshot dumps are no longer saved. Use backend/tools/probe_memory_checkout.py for short-lived DOM and optional cropped image inspection; only scoped coupon facts may be persisted with --ledger. Use backend/.venv. Deleted scratch paths are obsolete.

Inspect actual public criteria, itinerary, visible money units, nearby-airport notices and source disagreement before changing adapters. Do not invent fallback quotes, override failed criteria or solve human-verification challenges. Chromium retains its own version/UA; random fingerprint patches and resource blocking previously broke pages. Cached/API/vision approximations are not valid replacements for exact visible evidence. Keep failed providers visible to users while preserving good results from others.

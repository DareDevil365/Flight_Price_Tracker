---
node_id: "pattern:p003"
node_type: "PATTERN"
pattern_id: "p003"
description: "Fuel spike >20% in 30 days leads to 8-12% fare rise in 3-5 days"
confidence: 0.85
occurrences: ["2022-Mar", "2022-Jun"]
observed_price_rise_pct: 10
---
# Pricing Pattern: p003

**Summary**: Fuel spike >20% in 30 days leads to 8-12% fare rise in 3-5 days. Statistical confidence: 85%.
**Last updated**: 2026-06-19

---

## Pattern Conditions
- **Rules Trigger**: `{"atf_change_30d_pct": ">20", "brent_change_30d_pct": ">15"}`
- **Historical Occurrences**: ['2022-Mar', '2022-Jun']

## Linked Nodes

---
node_id: "pattern:p002"
node_type: "PATTERN"
pattern_id: "p002"
description: "Monsoon + beach route = 15-20% discount, best booking window"
confidence: 0.88
occurrences: ["2022-Jul", "2023-Jul", "2024-Jul"]
observed_price_drop_pct: 18
---
# Pricing Pattern: p002

**Summary**: Monsoon + beach route = 15-20% discount, best booking window. Statistical confidence: 88%.
**Last updated**: 2026-06-19

---

## Pattern Conditions
- **Rules Trigger**: `{"months": [6, 7, 8], "route_type": "BEACH", "days_to_departure": ">21"}`
- **Historical Occurrences**: ['2022-Jul', '2023-Jul', '2024-Jul']

## Linked Nodes
- Linked to Route Segment: [[route-type-beach]]
- Linked to Month: [[june]]
- Linked to Month: [[july]]
- Linked to Month: [[august]]

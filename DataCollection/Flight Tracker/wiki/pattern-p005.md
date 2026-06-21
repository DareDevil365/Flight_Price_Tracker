---
node_id: "pattern:p005"
node_type: "PATTERN"
pattern_id: "p005"
description: "Tuesday/Wednesday departures are 8-12% cheaper than Friday/Sunday"
confidence: 0.9
occurrences: ["2022-2024 aggregate"]
observed_price_drop_pct: 10
---
# Pricing Pattern: p005

**Summary**: Tuesday/Wednesday departures are 8-12% cheaper than Friday/Sunday. Statistical confidence: 90%.
**Last updated**: 2026-06-19

---

## Pattern Conditions
- **Rules Trigger**: `{"departure_day": ["Tuesday", "Wednesday"], "route_type": "ALL"}`
- **Historical Occurrences**: ['2022-2024 aggregate']

## Linked Nodes
- Linked to Route Segment: [[route-type-beach]]
- Linked to Route Segment: [[route-type-metro]]
- Linked to Route Segment: [[route-type-business]]

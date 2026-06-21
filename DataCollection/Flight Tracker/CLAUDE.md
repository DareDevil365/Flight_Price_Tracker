# Flight Tracker & Travel Intelligence Wiki

A structured, interlinked personal knowledge base maintained by the AI agent.
Based on Andrej Karpathy's LLM Wiki pattern and customized for planning domestic travel, tracking routes, and optimizing flight booking strategies.

## Purpose

This wiki acts as the central intelligence repository for flight routing, pricing trends, and offer stack optimization. It aggregates raw travel inputs (news articles, card updates, prediction audits, and fare indices) and converts them into clear, actionable booking strategies.

## Folder Structure

```
raw/          -- raw source documents (immutable -- e.g. raw airline policy changes, bank card announcements, oil price feeds)
wiki/         -- markdown concept pages maintained by the AI agent
wiki/index.md -- index table of contents mapping routes, airlines, and booking playbooks
wiki/log.md   -- append-only record of all wiki ingest and updating operations
```

## Ingest Workflow

When new travel data, news feeds, or offer listings are added to `raw/`:

1. **Read & Synthesize**: Read the raw files completely (e.g. a new credit card terms sheet).
2. **Review Takeaways**: Align with the user on pricing/saving implications before publishing.
3. **Generate Wiki Pages**:
   - Create or update the specific route page (e.g., [[del-bom-route]] or [[del-goi-route]]).
   - Create or update banking/offer files (e.g., [[hdfc-smartbuy-offers]] or [[sbi-card-discounts]]).
   - Create or update carrier profiles detailing peak schedules or baggage policies (e.g., [[indigo-airlines]]).
4. **Interlink Concepts**: Insert wiki-links (`[[page-name]]`) to bind routes, airlines, and savings stacks together.
5. **Update Index & Log**: Update `wiki/index.md` with a link and description, and log the operation details in `wiki/log.md`.

## Page Format & Graph RAG Integration

Every wiki page represents a **Graph RAG Node** and must start with a YAML frontmatter block defining its properties. The markdown body contains human-readable descriptions and **wiki-links (`[[page-name]]`)** which represent **Graph RAG Edges**.

### YAML Frontmatter Schema

#### 1. Routes (e.g., `wiki/del-bom-route.md`)
```yaml
---
node_id: "route:DEL-BOM"
node_type: "ROUTE"
type: "METRO"
base_price: 4600
peak_months: [10, 11, 12, 1]
off_months: [6, 7, 8]
---
```

#### 2. Bank Card Offers (e.g., `wiki/sbi-tuesday-sale.md`)
```yaml
---
node_id: "bank_offer:SBI_0"
node_type: "BANK_OFFER"
name: "SBI Tuesday Sale"
discount_pct: 10
typical_months: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
---
```

#### 3. Macro/Geopolitical Events (e.g., `wiki/fuel-spike.md`)
```yaml
---
node_id: "event_type:fuel_spike"
node_type: "EVENT_TYPE"
description: "Rapid increase in ATF or Brent crude prices"
typical_price_impact_pct: 8
lag_days: 3
affected_routes: ["ALL"]
---
```

#### 4. Pricing Patterns (e.g., `wiki/pattern-p001.md`)
```yaml
---
node_id: "pattern:p001"
node_type: "PATTERN"
pattern_id: "p001"
description: "Diwali + 14 days + T-7 booking = guaranteed price spike"
observed_price_rise_pct: 35
confidence: 0.92
---
```

### Graph RAG Edge Mapping (Wikilinks)
- Wikilinks pointing to other pages (e.g., `[[january]]` or `[[sbi-card-discounts]]`) are resolved by the Graph compiler to create directed edges in SQLite.
- The link relationship (edge type) is inferred automatically (e.g. linking a pattern to a month creates an `active_in` relationship, and linking to a route creates `affects_route` or `linked_to`).
- Custom edge relationships can be specified as `[[relation_type:target_page]]` (e.g., `[[triggered_by:geopolitical_tension]]`).

---

## Strategic Playbook
Primary booking instructions, price brackets, and airline behavior.

## Active Savings Stack
- **Direct Coupons**: Applicable promo codes from local DB.
- **Card/Bank Offers**: Stacking rules (e.g., net 5% rewards via [[hdfc-smartbuy-offers]]).

## Related pages

- [[related-concept-or-route]]

## Citation & Validation Rules

- Every claim (like a mean route price, card discount percentage, or seasonal peak window) must reference its source file in the format `(source: filename.pdf)`.
- If news updates contradict historical trend rules, document both perspectives and highlight the volatility risk.

## Querying & Answering

When asking routing or pricing strategy questions:
1. Search `wiki/index.md` to identify route, airline, or savings pages.
2. Read the interlinked notes and draft a cohesive booking schedule (e.g., "Wait 10 days for HDFC sales on IndiGo DEL-GOI").
3. Update the wiki if a query uncovers a new travel strategy.

## Linting & Quality Audits

Run weekly checks to ensure:
- No dead/broken wiki-links.
- Card offer validity dates are current and expired offers are archived.
- Specific route guidelines match the latest scraped average prices.
- All pages follow the strict markdown format.

## Rules

- Never write to or edit files in the `raw/` folder.
- Keep page filenames lowercase and hyphenated (e.g. `del-bom-route.md` or `indigo-sales.md`).
- Write in clear, structured, and action-oriented travel advice prose.


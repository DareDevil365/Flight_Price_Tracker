# Flight Tracker & Travel Intelligence Wiki — Guidelines

This document outlines the ingest workflow, page format, and Graph RAG compilation rules for the Flight Tracker Obsidian vault located in this directory under `Flight Tracker/`.

## Folder Structure

```
DataCollection/
  Flight Tracker/
    raw/          -- raw source documents (airline policy updates, bank announcements, fuel feeds)
    wiki/         -- markdown concept pages parsed by the Graph RAG engine
    wiki/index.md -- index table of contents mapping routes, offers, and patterns
    wiki/log.md   -- append-only record of wiki update operations
```

## Ingest Workflow

When new travel data, news feeds, or offer listings are added to `Flight Tracker/raw/`:

1. **Read & Synthesize**: Extract key pricing indicators (e.g. discount rates, active months, seasonal routes).
2. **Review Takeaways**: Align on pricing/saving implications.
3. **Generate Wiki Pages**:
   - Create or update the specific route page (e.g., `wiki/del-goi-route.md` or `wiki/bom-goi-route.md`).
   - Create or update banking/offer files (e.g., `wiki/sbi-card-offer-0.md` or `wiki/hdfc-card-offer-0.md`).
   - Create or update macro/event files (e.g., `wiki/event-type-fuel-spike.md`).
4. **Interlink Concepts**: Insert standard wiki-links (`[[page-name]]`) to bind routes, offers, months, and pricing patterns together.
5. **Update Index & Log**: Update `wiki/index.md` with links and log the operation details in `wiki/log.md`.

---

## Page Format & Graph RAG Integration

Every wiki page in `wiki/` represents a **Graph RAG Node** and must start with a YAML frontmatter block defining its properties. The markdown body contains human-readable descriptions and **wiki-links (`[[page-name]]`)** representing **Graph RAG Edges**.

### YAML Frontmatter Schema

#### 1. Routes (e.g., `wiki/del-bom-route.md`)
```yaml
---
node_id: "route:DEL-BOM"
node_type: "ROUTE"
route_type: "METRO"
base_price: 4600
peak_months: [10, 11, 12, 1]
off_months: [6, 7, 8]
---
```

#### 2. Bank Card Offers (e.g., `wiki/sbi-card-offer-0.md`)
```yaml
---
node_id: "bank_offer:SBI_0"
node_type: "BANK_OFFER"
name: "SBI Tuesday Sale"
discount_pct: 10
typical_months: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
---
```

#### 3. Macro/Geopolitical Events (e.g., `wiki/event-type-fuel-spike.md`)
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
- Wikilinks pointing to other pages (e.g., `[[january]]` or `[[sbi-card-offer-0]]`) are resolved by the Graph compiler to create directed edges in SQLite.
- The link relationship (edge type) is inferred automatically:
  - Linking to a month creates `active_in`.
  - Linking to a route or route type creates `affects_route` or `linked_to`.
  - Linking to a keyword creates `triggered_by`.
- Custom edge relationships can be specified as `[[relation_type:target_page]]` (e.g., `[[triggered_by:geopolitical_tension]]`).

---

## Strategic Playbook
Primary booking instructions, price brackets, and airline behavior.

## Active Savings Stack
- **Direct Coupons**: Applicable promo codes from local DB.
- **Card/Bank Offers**: Stacking rules (e.g., net 5% rewards via `[[hdfc-card-offer-0]]`).

---

## Citation & Validation Rules

- Every claim (like a mean route price, card discount percentage, or seasonal peak window) must reference its source file in the format `(source: filename.pdf)`.
- If news updates contradict historical trend rules, document both perspectives and highlight the volatility risk.

## CLI Utilities & Operations

### 1. Re-exporting JSON to Markdown notes
To force export/overwrite the Markdown notes from the legacy master JSON database `graph_rag_knowledge_base.json`:
```bash
python DataCollection/export_kb_to_markdown.py
```

### 2. Compiling the Graph
When the program starts (or when tests run), the Graph RAG engine automatically scans the Markdown vault `wiki/` folder and compiles all nodes and edges into the SQLite database.

### 3. Visualizing the Graph
To generate a live Mermaid.js graph visualization from the compiled SQLite tables:
```bash
# Activates the visualizer and updates graph_view.md
python backend/predictor/visualize_graph.py
```

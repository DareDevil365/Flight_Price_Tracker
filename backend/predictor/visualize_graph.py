"""
Flight Finder — Graph Visualizer
Queries the local SQLite Graph RAG tables and generates a beautiful markdown
file containing a Mermaid.js diagram of the active entities and relationships.
"""

import sqlite3
import json
from pathlib import Path
from loguru import logger

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "backend" / "db" / "flight_agent.db"
OUTPUT_PATH = PROJECT_ROOT / "backend" / "predictor" / "graph_view.md"
ARTIFACT_OUTPUT_PATH = Path(r"C:\Users\yasha\.gemini\antigravity-ide\brain\8e0cf4b0-be31-46e3-b755-0e00bfad57c2\graph_view.md")

def generate_graph_markdown():
    if not DB_PATH.exists():
        logger.error(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Query statistics
    cursor.execute("SELECT COUNT(*) FROM graph_nodes")
    node_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM graph_edges")
    edge_count = cursor.fetchone()[0]

    # Query all nodes
    cursor.execute("SELECT node_id, node_type, properties_json FROM graph_nodes")
    nodes = [dict(row) for row in cursor.fetchall()]

    # Query all edges
    cursor.execute("SELECT source_id, target_id, relation_type FROM graph_edges")
    edges = [dict(row) for row in cursor.fetchall()]

    conn.close()

    logger.info(f"Loaded {len(nodes)} nodes and {len(edges)} edges for visualization.")

    # We will build a focused Mermaid diagram centering on key routes and connections to keep it readable
    # Groups:
    # ROUTES (e.g. route:DEL-GOI)
    # MONTHS (e.g. month:7)
    # BANK_OFFERS (e.g. bank_offer:Axis_0)
    # PATTERNS (e.g. pattern:p002)
    # MACRO_EVENTS (e.g. macro_event:geo_0)

    # Let's map node IDs to safe Mermaid identifiers (alphanumeric only)
    def clean_id(nid):
        return nid.replace(":", "_").replace("-", "_").replace(" ", "_")

    mermaid_lines = [
        "graph TD",
        "  %% Node Styles",
        "  classDef route fill:#1f77b4,stroke:#fff,stroke-width:2px,color:#fff;",
        "  classDef type fill:#aec7e8,stroke:#fff,stroke-dasharray: 5 5,color:#333;",
        "  classDef month fill:#ff7f0e,stroke:#fff,stroke-width:2px,color:#fff;",
        "  classDef offer fill:#2ca02c,stroke:#fff,stroke-width:2px,color:#fff;",
        "  classDef pattern fill:#d62728,stroke:#fff,stroke-width:2px,color:#fff;",
        "  classDef macro fill:#9467bd,stroke:#fff,stroke-dasharray: 3 3,color:#fff;",
        ""
    ]

    # Define nodes in Mermaid
    for node in nodes:
        nid = node["node_id"]
        ntype = node["node_type"]
        props = json.loads(node["properties_json"])
        
        cid = clean_id(nid)
        label = nid.split(":")[-1]
        
        # Format labels nicely
        if ntype == "ROUTE":
            label = f"Route: {label}"
            style = "route"
        elif ntype == "ROUTE_TYPE":
            label = f"Type: {label}"
            style = "type"
        elif ntype == "MONTH":
            label = props.get("name", label)
            style = "month"
        elif ntype == "BANK_OFFER":
            label = props.get("name", label)
            style = "offer"
        elif ntype == "PATTERN":
            label = f"Pattern {label}: {props.get('description', '')[:30]}..."
            style = "pattern"
        elif ntype == "EVENT_TYPE" or ntype == "MACRO_EVENT":
            label = f"Macro/Event: {label}"
            style = "macro"
        else:
            style = "default"

        # Safe labels for Mermaid (escaping brackets)
        safe_label = label.replace('"', '\\"').replace('(', '[').replace(')', ']')
        mermaid_lines.append(f'  {cid}["{safe_label}"]')
        mermaid_lines.append(f'  class {cid} {style}')

    mermaid_lines.append("")
    mermaid_lines.append("  %% Edge Relationships")

    # Add edges
    for edge in edges:
        src = clean_id(edge["source_id"])
        tgt = clean_id(edge["target_id"])
        rel = edge["relation_type"]
        mermaid_lines.append(f"  {src} -- {rel} --> {tgt}")

    # Build full markdown
    markdown_content = f"""# Graph RAG Knowledge Graph View

This is a live visual representation of the entities and connections stored inside the local SQLite database.

## Graph Database Statistics
- **Total Nodes**: {node_count}
- **Total Edges**: {edge_count}

## Graph Traversal Visualizer

```mermaid
{chr(10).join(mermaid_lines)}
```

## Entity Descriptions

### 1. Routes (Blue Nodes)
Represents flight origin-destination pairs. Linked to route types (e.g. `BEACH_TOURISM` vs `METRO_BUSINESS`) which dictate baseline demand characteristics.

### 2. Months (Orange Nodes)
Represent calendar month targets. Ingestion creates month-edges indicating peak tourist activity or active seasonal modifiers (like monsoons).

### 3. Bank Offers (Green Nodes)
Represents recurring credit card promos (SBI Tuesday, Axis Flipkart Monsoon, HDFC SmartBuy) mapped to their valid months to flag discounts.

### 4. Pricing Patterns (Red Nodes)
Causal inference pairs gathered from historical analysis (e.g., T-7 booking spikes, monsoon discounts on beach routes).
"""

    # Save to both locations
    OUTPUT_PATH.write_text(markdown_content, encoding="utf-8")
    logger.info(f"Saved local graph view to {OUTPUT_PATH}")
    
    # Save to artifact folder
    ARTIFACT_OUTPUT_PATH.write_text(markdown_content, encoding="utf-8")
    logger.info(f"Saved artifact graph view to {ARTIFACT_OUTPUT_PATH}")

if __name__ == "__main__":
    generate_graph_markdown()

import os
import json
from pathlib import Path

def run_export():
    project_dir = Path(__file__).parent.parent
    kb_json_path = project_dir / "DataCollection" / "graph_rag_knowledge_base.json"
    vault_dir = project_dir / "DataCollection" / "Flight Tracker"
    wiki_dir = vault_dir / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading knowledge base from {kb_json_path}...")
    with open(kb_json_path, "r", encoding="utf-8") as f:
        kb = json.load(f)

    # 1. Months Map
    months_names = {
        1: "january", 2: "february", 3: "march", 4: "april", 5: "may", 6: "june",
        7: "july", 8: "august", 9: "september", 10: "october", 11: "november", 12: "december"
    }
    
    # Export Months
    for m_id, m_name in months_names.items():
        m_file = wiki_dir / f"{m_name}.md"
        content = f"""---
node_id: "month:{m_id}"
node_type: "MONTH"
id: {m_id}
name: "{m_name.capitalize()}"
---
# Month: {m_name.capitalize()}

Represents the travel month {m_name.capitalize()}. Used by Graph RAG to resolve seasonality and active credit card offers.
"""
        m_file.write_text(content.strip() + "\n", encoding="utf-8")
    print("Exported 12 calendar month notes.")

    # 2. Export Route Seasonality
    route_seasonality = kb.get("route_seasonality", {})
    route_filenames = {}
    for route, data in route_seasonality.items():
        filename = f"{route.lower()}-route"
        route_filenames[route] = filename
        r_file = wiki_dir / f"{filename}.md"
        
        # Determine route type
        r_type = data.get("type", "METRO")
        
        # Construct YAML frontmatter
        yaml_data = {
            "node_id": f"route:{route}",
            "node_type": "ROUTE",
            "route_type": r_type, # align with existing code expectation
            "base_price": data.get("base_price", 4000),
            "peak_months": data.get("peak_months", []),
            "off_months": data.get("off_months", []),
            "peak_price_surge_pct": data.get("peak_price_surge_pct", 25)
        }
        
        frontmatter = "---\n" + "\n".join(f"{k}: {json.dumps(v)}" for k, v in yaml_data.items()) + "\n---"
        
        # Links
        links_str = f"- [[route-type-{r_type.lower()}]]\n"
        for pm in data.get("peak_months", []):
            links_str += f"- Peak active in: [[{months_names[pm]}]]\n"
        for om in data.get("off_months", []):
            links_str += f"- Off-peak active in: [[{months_names[om]}]]\n"

        content = f"""{frontmatter}
# Route: {route}

**Summary**: Route seasonality details for flight corridor {route}.
**Last updated**: 2026-06-19

---

## Strategic Playbook
This corridor is classified as a `{r_type}` route. Base fare baseline is estimated at ₹{yaml_data['base_price']:,}.

## Active Connections
{links_str}
"""
        r_file.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"Exported {len(route_filenames)} route notes.")

    # 3. Export Route Types
    route_types = ["BEACH", "METRO", "BUSINESS", "BEACH_TOURISM", "METRO_BUSINESS"]
    for rt in route_types:
        rt_file = wiki_dir / f"route-type-{rt.lower()}.md"
        content = f"""---
node_id: "route_type:{rt}"
node_type: "ROUTE_TYPE"
type: "{rt}"
---
# Route Type: {rt}

Represents flight corridors categorized under the {rt} travel segment.
"""
        rt_file.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"Exported {len(route_types)} route segment type notes.")

    # 4. Export Bank Offers
    bank_offers = {
        "SBI": [{"name": "SBI Tuesday Sale", "discount_pct": 10, "typical_months": list(range(1, 13))}],
        "HDFC": [{"name": "HDFC SmartBuy Monthly", "discount_pct": 5, "typical_months": list(range(1, 13))}],
        "Axis": [{"name": "Axis Flipkart Monsoon", "discount_pct": 10, "typical_months": [7, 8, 9]}]
    }
    
    offer_filenames = []
    for bank, offers in bank_offers.items():
        for idx, offer in enumerate(offers):
            filename = f"{bank.lower()}-card-offer-{idx}"
            offer_filenames.append(filename)
            o_file = wiki_dir / f"{filename}.md"
            
            yaml_data = {
                "node_id": f"bank_offer:{bank}_{idx}",
                "node_type": "BANK_OFFER",
                "name": offer["name"],
                "discount_pct": offer["discount_pct"],
                "typical_months": offer["typical_months"]
            }
            
            frontmatter = "---\n" + "\n".join(f"{k}: {json.dumps(v)}" for k, v in yaml_data.items()) + "\n---"
            
            links_str = ""
            for m in offer["typical_months"]:
                links_str += f"- [[{months_names[m]}]]\n"
                
            content = f"""{frontmatter}
# Bank Card Offer: {offer['name']}

**Summary**: Recurring {offer['discount_pct']}% discount offer for {bank} cardholders.
**Last updated**: 2026-06-19

---

## Active Savings Playbook
Cardholders get an instant {offer['discount_pct']}% off tickets booked during active periods.

## Valid Months
{links_str}
"""
            o_file.write_text(content.strip() + "\n", encoding="utf-8")
    print("Exported 3 bank card offer notes.")

    # 5. Export Geopolitical / Macro Events (from event_types in KB)
    event_types = kb.get("event_types", {})
    event_filenames = {}
    for event_name, data in event_types.items():
        filename = f"event-type-{event_name.lower().replace('_', '-')}"
        event_filenames[event_name] = filename
        e_file = wiki_dir / f"{filename}.md"
        
        yaml_data = {
            "node_id": f"event_type:{event_name}",
            "node_type": "EVENT_TYPE",
            "description": data.get("description", ""),
            "typical_price_impact_pct": data.get("typical_price_impact_pct", 0),
            "lag_days": data.get("lag_days", 0),
            "affected_routes": data.get("affected_routes", ["ALL"])
        }
        
        frontmatter = "---\n" + "\n".join(f"{k}: {json.dumps(v)}" for k, v in yaml_data.items()) + "\n---"
        
        links_str = ""
        # Link to affected routes
        affected = data.get("affected_routes", ["ALL"])
        if "ALL" in affected:
            for r in route_seasonality.keys():
                links_str += f"- Affects Route: [[{route_filenames[r]}]]\n"
        else:
            for r in affected:
                if r in route_filenames:
                    links_str += f"- Affects Route: [[{route_filenames[r]}]]\n"
                
        # Link to months if active in specific months
        for m in data.get("months", []):
            links_str += f"- Active in Month: [[{months_names[m]}]]\n"
            
        content = f"""{frontmatter}
# Event Type: {event_name}

**Summary**: {yaml_data['description']}. Typical price impact: {yaml_data['typical_price_impact_pct']}% with lag of {yaml_data['lag_days']} days.
**Last updated**: 2026-06-19

---

## Macro Impact Parameters
- **Typical Fare Drift**: {yaml_data['typical_price_impact_pct']:+}%
- **Response Latency**: {yaml_data['lag_days']} days

## Linked Concepts
{links_str}
"""
        e_file.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"Exported {len(event_filenames)} macro event notes.")

    # 6. Export Learned Patterns
    learned_patterns = kb.get("learned_patterns", [])
    pattern_filenames = []
    for pat in learned_patterns:
        pat_id = pat["pattern_id"]
        filename = f"pattern-{pat_id.lower()}"
        pattern_filenames.append(filename)
        p_file = wiki_dir / f"{filename}.md"
        
        yaml_data = {
            "node_id": f"pattern:{pat_id}",
            "node_type": "PATTERN",
            "pattern_id": pat_id,
            "description": pat.get("description", ""),
            "confidence": pat.get("confidence", 0.90),
            "occurrences": pat.get("occurrences", [])
        }
        if "observed_price_rise_pct" in pat:
            yaml_data["observed_price_rise_pct"] = pat["observed_price_rise_pct"]
        elif "observed_price_drop_pct" in pat:
            yaml_data["observed_price_drop_pct"] = pat["observed_price_drop_pct"]
            
        frontmatter = "---\n" + "\n".join(f"{k}: {json.dumps(v)}" for k, v in yaml_data.items()) + "\n---"
        
        conds = pat.get("conditions", {})
        links_str = ""
        # Link to route types
        r_type = conds.get("route_type")
        if r_type:
            if r_type == "ALL":
                for rt in ["BEACH", "METRO", "BUSINESS"]:
                    links_str += f"- Linked to Route Segment: [[route-type-{rt.lower()}]]\n"
            else:
                links_str += f"- Linked to Route Segment: [[route-type-{r_type.lower()}]]\n"
                
        # Link to months
        for m in conds.get("months", []):
            links_str += f"- Linked to Month: [[{months_names[m]}]]\n"
            
        content = f"""{frontmatter}
# Pricing Pattern: {pat_id}

**Summary**: {yaml_data['description']}. Statistical confidence: {yaml_data['confidence']:.0%}.
**Last updated**: 2026-06-19

---

## Pattern Conditions
- **Rules Trigger**: `{json.dumps(conds)}`
- **Historical Occurrences**: {yaml_data['occurrences']}

## Linked Nodes
{links_str}
"""
        p_file.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"Exported {len(pattern_filenames)} learned pricing pattern notes.")

    # 7. Create wiki/index.md
    index_file = wiki_dir / "index.md"
    index_content = f"""# Flight Tracker & Travel Intelligence Wiki

Welcome to the interlinked Travel Intelligence Wiki! This knowledge base maps pricing patterns, credit card promotions, routes, and calendar months into a structured web of connections for Graph RAG.

## Flight Route Corridors
"""
    for route, fname in sorted(route_filenames.items()):
        index_content += f"- [[{fname}]] -- Seasonality & base prices for {route}\n"
        
    index_content += "\n## Credit Card Promotions\n"
    for fname in sorted(offer_filenames):
        index_content += f"- [[{fname}]]\n"
        
    index_content += "\n## Macro & Geopolitical Influences\n"
    for name, fname in sorted(event_filenames.items()):
        index_content += f"- [[{fname}]] -- {name.replace('_', ' ').title()}\n"
        
    index_content += "\n## Learned Pricing Patterns\n"
    for fname in sorted(pattern_filenames):
        index_content += f"- [[{fname}]]\n"
        
    index_content += "\n## Route Segment Classifications\n"
    for rt in sorted(route_types):
        index_content += f"- [[route-type-{rt.lower()}]]\n"

    index_file.write_text(index_content.strip() + "\n", encoding="utf-8")
    print("Created index.md.")

    # 8. Create wiki/log.md
    log_file = wiki_dir / "log.md"
    log_content = """# Ingest and Update Operations Log

- **2026-06-19**: Initial batch migration of knowledge base from `graph_rag_knowledge_base.json` into Obsidian markdown vault notes. Auto-generated route corridors, bank card promotions, event types, and learned pricing patterns.
"""
    log_file.write_text(log_content.strip() + "\n", encoding="utf-8")
    print("Created log.md.")
    print("[OK] Wiki vault export completed successfully!")

if __name__ == "__main__":
    run_export()

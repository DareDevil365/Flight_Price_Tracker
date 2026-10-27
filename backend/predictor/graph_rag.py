"""
Flight Finder — Graph RAG Engine
Builds and queries a local SQLite-based knowledge graph to map and reason over
routes, months, festivals, bank offers, macro-indicators, and learned pricing patterns.
"""

import os
import json
import re
import sys
from pathlib import Path
from datetime import datetime
from loguru import logger
import aiosqlite

class GraphRAGEngine:
    def __init__(self, db_path: str = None):
        if db_path is None:
            self.db_path = str(Path(__file__).parent.parent / "db" / "flight_agent.db")
        else:
            self.db_path = db_path
        self.kb_path = Path(__file__).parent / "rag_knowledge_base.json"
        self.vault_path = Path(__file__).parent.parent.parent / "DataCollection" / "Flight Tracker"

    async def initialize_graph_tables(self):
        """Create SQLite tables for nodes and edges if they do not exist."""
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS graph_nodes (
                        node_id TEXT PRIMARY KEY,
                        node_type TEXT NOT NULL,
                        properties_json TEXT NOT NULL
                    )
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS graph_edges (
                        source_id TEXT NOT NULL,
                        target_id TEXT NOT NULL,
                        relation_type TEXT NOT NULL,
                        properties_json TEXT NOT NULL,
                        PRIMARY KEY (source_id, target_id, relation_type)
                    )
                """)
                await conn.commit()
                logger.info("✅ Graph RAG SQLite tables initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize Graph RAG tables: {e}")

    async def populate_graph_from_kb(self):
        """Parse knowledge base vault or fallback JSON and populate the SQLite store."""
        wiki_dir = self.vault_path / "wiki"
        
        # Self-healing: If vault doesn't exist, generate it programmatically from JSON
        if not wiki_dir.exists():
            logger.info(f"Obsidian knowledge vault not found at {self.vault_path}. Auto-generating from JSON...")
            try:
                # Add DataCollection to path so we can import exporter
                data_collection_path = str(self.vault_path.parent)
                if data_collection_path not in sys.path:
                    sys.path.append(data_collection_path)
                from DataCollection.export_kb_to_markdown import run_export
                run_export()
            except Exception as e:
                logger.error(f"Failed to auto-export JSON knowledge base to markdown vault: {e}")

        if wiki_dir.exists():
            logger.info(f"Loading knowledge graph from Obsidian Markdown vault: {wiki_dir}")
            await self.populate_graph_from_markdown_vault(wiki_dir)
        else:
            logger.warning("Markdown vault unavailable. Falling back to JSON knowledge base ingestion.")
            await self._populate_graph_from_json_fallback()

    def _parse_yaml_frontmatter(self, content: str):
        """Parses a simple YAML frontmatter block from markdown."""
        properties = {}
        body = ""
        lines = content.splitlines()
        if len(lines) > 0 and lines[0].strip() == "---":
            yaml_lines = []
            body_lines = []
            in_yaml = True
            for line in lines[1:]:
                if in_yaml:
                    if line.strip() == "---":
                        in_yaml = False
                    else:
                        yaml_lines.append(line)
                else:
                    body_lines.append(line)
            body = "\n".join(body_lines)
            
            # Parse simple YAML key-value pairs
            for y_line in yaml_lines:
                if ":" not in y_line:
                    continue
                k, v = y_line.split(":", 1)
                k = k.strip()
                v = v.strip()
                if " #" in v:
                    v = v.split(" #", 1)[0].strip()
                if v.startswith("[") and v.endswith("]"):
                    try:
                        properties[k] = json.loads(v)
                    except Exception:
                        items = [item.strip().strip("'\"") for item in v[1:-1].split(",") if item.strip()]
                        typed_items = []
                        for item in items:
                            if item.isdigit():
                                typed_items.append(int(item))
                            elif item.replace("-", "", 1).isdigit():
                                typed_items.append(int(item))
                            else:
                                typed_items.append(item)
                        properties[k] = typed_items
                elif v.lower() == "true":
                    properties[k] = True
                elif v.lower() == "false":
                    properties[k] = False
                elif v.isdigit():
                    properties[k] = int(v)
                else:
                    try:
                        properties[k] = float(v)
                    except ValueError:
                        properties[k] = v.strip("'\"")
        else:
            body = content
            
        return properties, body

    def _extract_wikilinks(self, body: str):
        """Finds all Obsidian-style [[link]] occurrences in markdown."""
        links = re.findall(r'\[\[(.*?)\]\]', body)
        edges = []
        for link in links:
            link = link.strip()
            if ":" in link:
                parts = link.split(":", 1)
                prefix = parts[0].strip()
                rest = parts[1].strip()
                if prefix in ["route", "month", "pattern", "bank_offer", "macro_event", "event_type", "route_type", "keyword"]:
                    edges.append((None, link))
                else:
                    edges.append((prefix, rest))
            else:
                edges.append((None, link))
        return edges

    def _resolve_target_id(self, link: str, file_map: dict):
        """Resolves target link text to programmatic node ID."""
        months_mapping = {
            "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
            "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
        }
        link_clean = link.strip().lower()
        
        # 1. Match against known note filenames
        if link_clean in file_map:
            return file_map[link_clean]
        
        # Match with underscores instead of hyphens
        link_hyphenated = link_clean.replace("_", "-")
        if link_hyphenated in file_map:
            return file_map[link_hyphenated]
            
        # 2. Check if it's already a direct node ID
        if ":" in link:
            prefix = link.split(":", 1)[0].strip().lower()
            if prefix in ["route", "month", "pattern", "bank_offer", "macro_event", "event_type", "route_type", "keyword"]:
                return link
                
        # 3. Check if it's a month name
        if link_clean in months_mapping:
            return f"month:{months_mapping[link_clean]}"
            
        # 4. Check if it's a route
        if len(link_clean) == 7 and "-" in link_clean:
            return f"route:{link.upper()}"
            
        # 5. Default fallback to keyword
        return f"keyword:{link_clean.replace(' ', '_')}"

    async def populate_graph_from_markdown_vault(self, wiki_dir: Path):
        """Parse all markdown notes in wiki_dir and build the SQLite knowledge graph."""
        nodes = []
        edges = []
        file_map = {}
        parsed_notes = []
        
        for file_path in wiki_dir.glob("*.md"):
            if file_path.name in ["index.md", "log.md", "CLAUDE.md"]:
                continue
                
            try:
                content = file_path.read_text(encoding="utf-8")
                props, body = self._parse_yaml_frontmatter(content)
                
                node_id = props.get("node_id")
                node_type = props.get("node_type")
                
                if node_id and node_type:
                    node_props = {k: v for k, v in props.items() if k not in ["node_id", "node_type"]}
                    parsed_notes.append((node_id, node_type, node_props, body))
                    filename_clean = file_path.stem.lower()
                    file_map[filename_clean] = node_id
            except Exception as e:
                logger.error(f"Error parsing markdown note {file_path.name}: {e}")
                
        for node_id, node_type, properties, body in parsed_notes:
            nodes.append((node_id, node_type, json.dumps(properties)))
            
            links = self._extract_wikilinks(body)
            for rel, target_link in links:
                target_id = self._resolve_target_id(target_link, file_map)
                
                relation_type = rel
                if not relation_type:
                    if target_id.startswith("month:"):
                        relation_type = "active_in"
                    elif target_id.startswith("route:") or target_id.startswith("route_type:"):
                        relation_type = "affects_route" if node_type == "EVENT_TYPE" else "linked_to"
                    elif target_id.startswith("event_type:"):
                        relation_type = "affects_route"
                    elif target_id.startswith("keyword:"):
                        relation_type = "triggered_by"
                    else:
                        relation_type = "linked_to"
                        
                edges.append((node_id, target_id, relation_type, json.dumps({})))
                
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute("DELETE FROM graph_nodes")
                await conn.execute("DELETE FROM graph_edges")
                await conn.executemany("""
                    INSERT OR REPLACE INTO graph_nodes (node_id, node_type, properties_json)
                    VALUES (?, ?, ?)
                """, nodes)
                await conn.executemany("""
                    INSERT OR REPLACE INTO graph_edges (source_id, target_id, relation_type, properties_json)
                    VALUES (?, ?, ?, ?)
                """, edges)
                await conn.commit()
            logger.info(f"Successfully populated knowledge graph from Markdown vault: {len(nodes)} nodes, {len(edges)} edges.")
        except Exception as e:
            logger.error(f"Error writing markdown graph nodes/edges to SQLite: {e}")

    async def _populate_graph_from_json_fallback(self):
        """Parse rag_knowledge_base.json and populate the Graph RAG SQLite store (Fallback)."""
        if not self.kb_path.exists():
            logger.warning(f"Knowledge base file not found at {self.kb_path}. Ingestion skipped.")
            return

        try:
            with open(self.kb_path, "r", encoding="utf-8") as f:
                kb = json.load(f)

            logger.info("Ingesting knowledge graph from rag_knowledge_base.json (fallback)...")
            
            nodes = []
            edges = []

            # 1. Ingest Route Seasonality
            route_seasonality = kb.get("route_seasonality", {})
            for route, data in route_seasonality.items():
                node_id = f"route:{route}"
                nodes.append((node_id, "ROUTE", json.dumps(data)))
                
                route_type = data.get("route_type", "METRO_BUSINESS")
                type_node = f"route_type:{route_type}"
                nodes.append((type_node, "ROUTE_TYPE", json.dumps({"type": route_type})))
                edges.append((node_id, type_node, "is_type", json.dumps({})))

            # 2. Ingest Months
            months_names = {
                1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
                7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December"
            }
            for m_id, m_name in months_names.items():
                nodes.append((f"month:{m_id}", "MONTH", json.dumps({"id": m_id, "name": m_name})))

            # 3. Ingest Bank Card Offers
            bank_offers = kb.get("bank_card_offers", {})
            if not bank_offers and "event_types" in kb:
                bank_offers = {
                    "SBI": [{"name": "SBI Tuesday Sale", "discount_pct": 10, "typical_months": list(range(1, 13))}],
                    "HDFC": [{"name": "HDFC SmartBuy Monthly", "discount_pct": 5, "typical_months": list(range(1, 13))}],
                    "Axis": [{"name": "Axis Flipkart Monsoon", "discount_pct": 10, "typical_months": [7, 8, 9]}]
                }

            for bank, offers in bank_offers.items():
                for idx, offer in enumerate(offers):
                    offer_id = f"bank_offer:{bank}_{idx}"
                    nodes.append((offer_id, "BANK_OFFER", json.dumps(offer)))
                    for m in offer.get("typical_months", []):
                        edges.append((offer_id, f"month:{m}", "active_in", json.dumps({})))

            # 4. Ingest Geopolitical & Macro Events
            geopolitical_events = kb.get("geopolitical_events", [])
            for idx, geo in enumerate(geopolitical_events):
                geo_id = f"macro_event:geo_{idx}"
                nodes.append((geo_id, "MACRO_EVENT", json.dumps(geo)))
                for kw in geo.get("event_trigger_keywords", []):
                    kw_id = f"keyword:{kw}"
                    nodes.append((kw_id, "KEYWORD", json.dumps({"word": kw})))
                    edges.append((geo_id, kw_id, "triggered_by", json.dumps({})))

            # 5. Ingest Event Types
            event_types = kb.get("event_types", {})
            for event_name, data in event_types.items():
                event_node = f"event_type:{event_name}"
                nodes.append((event_node, "EVENT_TYPE", json.dumps(data)))
                for m in data.get("months", []):
                    edges.append((event_node, f"month:{m}", "active_in", json.dumps({})))
                for r in data.get("affected_routes", []):
                    if r == "ALL":
                        for route in route_seasonality.keys():
                            edges.append((event_node, f"route:{route}", "affects_route", json.dumps({})))
                    else:
                        edges.append((event_node, f"route:{r}", "affects_route", json.dumps({})))

            # 6. Ingest Learned Patterns
            learned_patterns = kb.get("learned_patterns", [])
            for pat in learned_patterns:
                pat_id = f"pattern:{pat['pattern_id']}"
                nodes.append((pat_id, "PATTERN", json.dumps(pat)))
                conds = pat.get("conditions", {})
                if "route_type" in conds:
                    r_type = conds["route_type"]
                    if r_type == "ALL":
                        for rt in ["BEACH_TOURISM", "METRO_BUSINESS", "BEACH", "METRO", "BUSINESS"]:
                            edges.append((pat_id, f"route_type:{rt}", "linked_to", json.dumps({})))
                    else:
                        edges.append((pat_id, f"route_type:{r_type}", "linked_to", json.dumps({})))
                for m in conds.get("months", []):
                    edges.append((pat_id, f"month:{m}", "active_in", json.dumps({})))

            async with aiosqlite.connect(self.db_path) as conn:
                await conn.executemany("""
                    INSERT OR REPLACE INTO graph_nodes (node_id, node_type, properties_json)
                    VALUES (?, ?, ?)
                """, nodes)
                await conn.executemany("""
                    INSERT OR REPLACE INTO graph_edges (source_id, target_id, relation_type, properties_json)
                    VALUES (?, ?, ?, ?)
                """, edges)
                await conn.commit()
            
            logger.info(f"Successfully populated knowledge graph (fallback): {len(nodes)} nodes, {len(edges)} edges.")
        except Exception as e:
            logger.error(f"Error populating knowledge graph from JSON (fallback): {e}")

    async def retrieve_subgraph(self, route: str, travel_date_str: str, brent_usd: float = 83.0) -> dict:
        """
        Traverses nodes and edges up to 2-hops away to compile route, seasonality, 
        bank card offers, and macro factors for the travel window.
        """
        try:
            travel_dt = datetime.strptime(travel_date_str, "%Y-%m-%d")
        except Exception:
            travel_dt = datetime.now()

        month = travel_dt.month
        route_node = f"route:{route}"
        month_node = f"month:{month}"

        retrieved_facts = []
        scores = [] # list of dicts: {"factor": name, "weight": value}

        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row

            # 1. Fetch Route seasonality details
            async with conn.execute("SELECT properties_json FROM graph_nodes WHERE node_id = ?", (route_node,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    r_data = json.loads(row["properties_json"])
                    retrieved_facts.append(f"Route {route} type is classified as {r_data.get('route_type', r_data.get('type'))}.")
                    
                    # Check peak/off months
                    peak_months = r_data.get("peak_months", [])
                    off_months = r_data.get("off_months", [])
                    if month in peak_months:
                        retrieved_facts.append(f"Travel month {travel_dt.strftime('%B')} is PEAK season for {route} (surge risk: +{r_data.get('peak_price_surge_pct', 25)}%).")
                        scores.append({"factor": "Peak Season demand", "weight": 0.20}) # positive weight = wait/prices rise
                    elif month in off_months:
                        retrieved_facts.append(f"Travel month {travel_dt.strftime('%B')} is OFF-PEAK season for {route} (historically discounted).")
                        scores.append({"factor": "Off-peak monsoon seasonality", "weight": -0.18}) # negative weight = book/prices low

            # 2. Fetch Bank offers active in the travel month (1-hop from month)
            query_bank = """
                SELECT gn.properties_json FROM graph_nodes gn
                JOIN graph_edges ge ON gn.node_id = ge.source_id
                WHERE ge.target_id = ? AND gn.node_type = 'BANK_OFFER'
            """
            async with conn.execute(query_bank, (month_node,)) as cursor:
                rows = await cursor.fetchall()
                for r in rows:
                    offer = json.loads(r["properties_json"])
                    retrieved_facts.append(f"Active Bank Card Offer: {offer['name']} offers {offer['discount_pct']}% discount (Max: ₹{offer.get('max_discount_inr', offer.get('max_discount', 1500))}).")
                    scores.append({"factor": f"Bank offer {offer.get('name')}", "weight": -0.07}) # waiting for offers

            # 3. Retrieve learned patterns linked to this month or route type (2-hop traversal)
            # Find route type
            route_type = "METRO_BUSINESS"
            async with conn.execute("SELECT target_id FROM graph_edges WHERE source_id = ? AND relation_type = 'is_type'", (route_node,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    route_type = row["target_id"].split(":")[-1]

            # Query patterns linked to route type or active in this month
            query_patterns = """
                SELECT DISTINCT gn.properties_json FROM graph_nodes gn
                JOIN graph_edges ge ON gn.node_id = ge.source_id
                WHERE (ge.target_id = ? OR ge.target_id = ?) AND gn.node_type = 'PATTERN'
            """
            async with conn.execute(query_patterns, (f"route_type:{route_type}", month_node)) as cursor:
                rows = await cursor.fetchall()
                for r in rows:
                    pat = json.loads(r["properties_json"])
                    retrieved_facts.append(f"Pattern {pat['pattern_id']}: {pat['description']} (Confidence: {pat['confidence']}, Weight: {pat.get('observed_price_rise_pct', -pat.get('observed_price_drop_pct', 0))}%)")
                    
                    # Incorporate pattern weight
                    if "observed_price_rise_pct" in pat:
                        scores.append({"factor": pat["description"], "weight": pat["observed_price_rise_pct"] / 100.0})
                    elif "observed_price_drop_pct" in pat:
                        scores.append({"factor": pat["description"], "weight": -pat["observed_price_drop_pct"] / 100.0})

            # 4. Integrate Geopolitical / Macro Indicators
            # Check fuel prices
            if brent_usd > 85.0:
                retrieved_facts.append(f"Macro Warning: Brent crude is highly inflated at ${brent_usd:.2f}/bbl. Active 'fuel_spike' condition threatens a 5-10% ticket surcharge in 3-5 days.")
                scores.append({"factor": "High fuel surcharge threat", "weight": 0.12})
            elif brent_usd < 75.0:
                retrieved_facts.append(f"Macro Note: Brent crude is low at ${brent_usd:.2f}/bbl. Fares are stable due to lower fuel overheads.")
                scores.append({"factor": "Low fuel overheads", "weight": -0.05})
            else:
                retrieved_facts.append(f"Macro Note: Brent crude is stable at ${brent_usd:.2f}/bbl.")

            # 5. Semantic node lookup complement (TF-IDF / keyword similarity lookup)
            destination = route.split("-")[1].upper() if "-" in route else route
            semantic_query = f"{route} {destination}"
            if month in [6, 7, 8, 9]:
                semantic_query += " monsoon rain off-peak discount"
            elif month in [10, 11, 12, 1, 2]:
                semantic_query += " festival peak wedding surge"

            async with conn.execute("SELECT node_id, node_type, properties_json FROM graph_nodes") as cursor:
                node_rows = await cursor.fetchall()
                all_nodes = [dict(nr) for nr in node_rows]

            if all_nodes:
                semantic_results = self._compute_tfidf_and_cosine_similarity(semantic_query, all_nodes, top_k=3, threshold=0.1)
                for res in semantic_results:
                    node = res["node"]
                    sim = res["similarity"]
                    node_id = node["node_id"]

                    # Skip if we already processed this route or month node directly
                    if node_id in [route_node, month_node]:
                        continue

                    props = json.loads(node["properties_json"])
                    node_type = node["node_type"]

                    # Add to retrieved facts
                    fact_msg = f"Semantically matched node {node_id} ({node_type}, similarity: {sim:.2f})"
                    if node_type == "BANK_OFFER":
                        fact_msg += f": Offer {props.get('name')} active."
                        scores.append({"factor": f"Semantic bank offer {props.get('name')}", "weight": -0.05})
                    elif node_type == "PATTERN":
                        fact_msg += f": Pattern {props.get('pattern_id')} - {props.get('description')}."
                        if "observed_price_rise_pct" in props:
                            scores.append({"factor": props["description"], "weight": props["observed_price_rise_pct"] / 150.0})
                        elif "observed_price_drop_pct" in props:
                            scores.append({"factor": props["description"], "weight": -props["observed_price_drop_pct"] / 150.0})
                    elif node_type == "MACRO_EVENT":
                        fact_msg += f": Macro event {props.get('title') or props.get('name')}."

                    retrieved_facts.append(fact_msg)

        # Compute net recommendation score
        # Weighted score: sum of all weights
        # If net score is positive, it suggests prices are rising -> BUY NOW
        # If net score is negative, it suggests prices are dropping or deals are active -> WAIT
        net_score = sum(s["weight"] for s in scores)

        return {
            "facts": retrieved_facts,
            "net_score": round(net_score, 3),
            "factors": scores
        }

    async def generate_explanation(self, facts: list, net_score: float, route: str, travel_date: str) -> str:
        """
        Generate explainable recommendation advice. 
        If LLM is available, we query it. Otherwise, we format a robust local rule-based advisory.
        """
        # Load local keys to see if we can use LLM
        openai_key = os.getenv("OPENAI_API_KEY")
        gemini_key = os.getenv("GEMINI_API_KEY")

        if openai_key or gemini_key:
            try:
                # Lazy import RAG advisor
                from modular_tools.rag_advisor.rag_engine import ReusableRAGEngine
                persist_dir = str(Path(__file__).parent.parent.parent / "data" / "chromadb")
                rag = ReusableRAGEngine(persist_dir=persist_dir, gemini_key=gemini_key, openai_key=openai_key)
                
                # Construct prompt
                prompt = (
                    f"You are the Flight Finder AI Brain. Analyze the following graph relations and macro factors "
                    f"for route {route} traveling on {travel_date} and advise if the user should BOOK NOW or WAIT. "
                    f"Determine if the current time is a good call to book or if they should wait (e.g. 10 days for new bank offers in July, "
                    f"or avoid fuel spike price increases, or monsoon discounts).\n\n"
                    f"Graph Facts:\n" + "\n".join([f"- {f}" for f in facts]) + "\n\n"
                    f"Net Graph Score: {net_score:+.2f} (positive = prices rising, negative = prices falling/discounts active).\n\n"
                    f"Generate a clear explanation with the following format:\n"
                    f"VERDICT: [BOOK_NOW | WAIT | MONITOR]\n"
                    f"WAIT_UNTIL: [YYYY-MM-DD or N/A]\n"
                    f"REASON: [Stitch together a professional reason linking seasonality, card offers, fuel prices, and history]\n"
                    f"RISK_IF_OPPOSITE: [Detail the risk of doing the opposite choice]"
                )
                
                logger.info("[GraphRAG] Requesting LLM reasoning...")
                response = await rag.generate_response(prompt, "You are a professional travel intelligence analyst.")
                if response and "VERDICT:" in response:
                    return response
            except Exception as e:
                logger.warning(f"Failed to generate LLM Graph RAG explanation: {e}. Falling back to rule-based parser.")

        # Fallback local rule-based advisory builder
        verdict = "MONITOR"
        wait_until = "N/A"
        
        # Determine verdict
        if net_score >= 0.05:
            verdict = "BOOK_NOW"
        elif net_score <= -0.05:
            verdict = "WAIT"
            # calculate book by date (e.g. 10 days from now or 21 days before travel)
            try:
                travel_dt = datetime.strptime(travel_date, "%Y-%m-%d")
                book_by_dt = travel_dt - datetime.timedelta(days=21)
                if book_by_dt < datetime.now():
                    book_by_dt = datetime.now() + datetime.timedelta(days=7)
                wait_until = book_by_dt.strftime("%Y-%m-%d")
            except Exception:
                wait_until = "10 days"

        # Construct explanation
        reason_parts = []
        risk_parts = []

        if net_score >= 0.05:
            reason_parts.append("Prices are expected to rise due to peak travel demand, upcoming holidays, or high global oil prices driving up airline fuel surcharges.")
            risk_parts.append("Waiting could result in base fares spiking significantly as seat inventory depletes near departure.")
        else:
            reason_parts.append("Fares are trending lower due to off-season travel windows (e.g., monsoon season on beach routes) combined with upcoming credit card sales (like card offers starting in July).")
            risk_parts.append("Booking today means you miss out on credit card instant discounts (up to 10% off) or potential airline price cuts.")

        # Add specific facts
        for f in facts:
            if "monsoon" in f.lower():
                reason_parts.append("Heavy monsoon season is depressing leisure demand, which historical patterns suggest creates a 15-20% off-season discount.")
            if "bank card" in f.lower() or "offer" in f.lower():
                reason_parts.append("Additionally, scheduled card promotions are active or launching soon for this travel month.")
            if "brent crude" in f.lower() and "inflated" in f.lower():
                reason_parts.append("However, Brent crude oil prices are high, which presents an active threat of ticket price increases if airlines issue fuel surcharges.")
                risk_parts.append("Be aware that high oil prices might trigger price hikes, negating card discount savings.")

        reason = " ".join(dict.fromkeys(reason_parts))
        risk = " ".join(dict.fromkeys(risk_parts))

        fallback_explanation = (
            f"VERDICT: {verdict}\n"
            f"WAIT_UNTIL: {wait_until}\n"
            f"REASON: {reason}\n"
            f"RISK_IF_OPPOSITE: {risk}"
        )
        return fallback_explanation

    def _compute_tfidf_and_cosine_similarity(self, query: str, nodes: list[dict], top_k: int = 5, threshold: float = 0.05) -> list[dict]:
        """
        Pure Python TF-IDF and Cosine Similarity to find nodes semantically matching a query.
        """
        import math
        from collections import Counter

        # Tokenize function
        def tokenize(text: str) -> list[str]:
            return re.findall(r'\w+', text.lower())

        # Get documents
        documents = []
        for node in nodes:
            # Combine properties and ID to form document text
            props = json.loads(node["properties_json"])
            props_text = " ".join([str(v) for v in props.values()])
            doc_text = f"{node['node_id']} {node['node_type']} {props_text}"
            documents.append((node, tokenize(doc_text)))

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        # Compute IDF
        num_docs = len(documents)
        dfs = Counter()
        for _, tokens in documents:
            unique_tokens = set(tokens)
            for token in unique_tokens:
                dfs[token] += 1

        idfs = {}
        for token, df in dfs.items():
            idfs[token] = math.log((1 + num_docs) / (1 + df)) + 1

        # TF-IDF of query
        query_tf = Counter(query_tokens)
        query_tfidf = {}
        query_norm = 0.0
        for token, count in query_tf.items():
            if token in idfs:
                tfidf = count * idfs[token]
                query_tfidf[token] = tfidf
                query_norm += tfidf ** 2
        query_norm = math.sqrt(query_norm)

        if query_norm == 0.0:
            return []

        # TF-IDF and similarity for each document
        results = []
        for node, tokens in documents:
            doc_tf = Counter(tokens)
            doc_tfidf = {}
            doc_norm = 0.0
            for token, count in doc_tf.items():
                if token in idfs:
                    tfidf = count * idfs[token]
                    doc_tfidf[token] = tfidf
                    doc_norm += tfidf ** 2
            doc_norm = math.sqrt(doc_norm)

            if doc_norm == 0.0:
                continue

            # Dot product
            dot_product = 0.0
            for token in query_tfidf:
                if token in doc_tfidf:
                    dot_product += query_tfidf[token] * doc_tfidf[token]

            similarity = dot_product / (query_norm * doc_norm)
            if similarity >= threshold:
                results.append((node, similarity))

        # Sort and return top K
        results.sort(key=lambda x: x[1], reverse=True)
        return [{"node": item[0], "similarity": item[1]} for item in results[:top_k]]

    async def search_nodes_semantically(self, query: str, top_k: int = 5, threshold: float = 0.05) -> list[dict]:
        """
        Retrieves nodes semantically matching a query using TF-IDF and cosine similarity.
        """
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute("SELECT node_id, node_type, properties_json FROM graph_nodes") as cursor:
                    rows = await cursor.fetchall()
                    nodes = [dict(row) for row in rows]

            if not nodes:
                return []

            return self._compute_tfidf_and_cosine_similarity(query, nodes, top_k, threshold)
        except Exception as e:
            logger.error(f"Semantic node search failed: {e}")
            return []

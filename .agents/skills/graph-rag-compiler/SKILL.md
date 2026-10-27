---
name: graph-rag-compiler
description: "Run when modifying markdown travel intelligence wiki pages, updating banking/offer details, or visualising the Graph RAG SQLite database."
---

# Graph RAG Compiler Skill

This skill contains the steps to maintain and visualize the Graph RAG travel database.

## 📋 Data Compilation Flow

1.  **Markdown Export (If starting from legacy JSON):**
    If the legacy master JSON database `graph_rag_knowledge_base.json` was updated, export it to Obsidian notes:
    ```powershell
    cd DataCollection
    ..\backend\venv\Scripts\python.exe export_kb_to_markdown.py
    ```
2.  **Verify Obsidian Wiki Structure:**
    Ensure notes in [wiki/](file:///c:/Users/yasha/Desktop/Flight%20Finder/DataCollection/Flight%20Tracker/wiki/) contain valid YAML frontmatter matching [CLAUDE.md](file:///c:/Users/yasha/Desktop/Flight%20Finder/DataCollection/CLAUDE.md).
3.  **Compile & Seed SQLite Graph:**
    The Graph RAG engine scans the markdown files and compiles them into SQLite. Run tests to trigger auto-compilation:
    ```powershell
    cd backend
    .\venv\Scripts\pytest.exe tests/test_graph_rag.py
    ```
4.  **Visualize the Graph:**
    To export a visual layout of nodes and edges to [graph_view.md](file:///c:/Users/yasha/Desktop/Flight%20Finder/backend/predictor/graph_view.md), run:
    ```powershell
    cd backend
    .\venv\Scripts\python.exe predictor/visualize_graph.py
    ```

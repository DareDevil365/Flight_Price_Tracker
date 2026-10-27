# Workspace Context Management

You must follow these rules to minimize token usage and maintain a consistent state across sessions.

## 📋 Rules of Operation

1.  **Read Context First:** At the beginning of any conversation or task, your very first action must be to read the project context file:
    *   Read [context.md](file:///c:/Users/yasha/Desktop/Flight%20Finder/.gemini/context.md) to understand the project architecture, file structure, state, and previous implementations.
2.  **Avoid Codebase Re-Scans:** Do NOT run commands to list all files or read large spec files (like `FLIGHT_FINDER_MASTER_SPEC.md` or large source files) from scratch unless you are modifying them or need specific details not covered in the context file.
3.  **Update Context Last:** Before completing your final turn or concluding a major task, you must update the "Current Project State & Next Steps" section of [context.md](file:///c:/Users/yasha/Desktop/Flight%20Finder/.gemini/context.md) to reflect:
    *   What changes were made (with file links).
    *   The current status of the database and servers.
    *   What tasks remain to be completed.
4.  **Keep it Concise:** Keep [context.md](file:///c:/Users/yasha/Desktop/Flight%20Finder/.gemini/context.md) focused on high-level architecture, main scripts, workflows, and current status. Do not bloat it with low-level details.

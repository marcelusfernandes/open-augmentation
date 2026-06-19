---
description: Search across hot memory and cold knowledge
---

Search for: $ARGUMENTS

## Search procedure

1. **Hot memory (already in context):** Check the project memory files (user-profile, active-projects, feedback-log, references) for relevant information. These are already loaded — just reference what you know.

2. **Cold knowledge (QMD):** Search using both methods:
   - MCP `query` tool with lex + vec sub-queries derived from the search terms
   - CLI: `qmd query "$ARGUMENTS"` for hybrid search with reranking

3. **Present results** with clear attribution:
   - `[memory]` for hits from hot memory files
   - `[knowledge]` for hits from QMD with file path

If no arguments were provided, ask the user what they want to find.

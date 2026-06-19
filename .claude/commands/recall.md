---
description: Search across hot memory and cold knowledge
---

Search for: $ARGUMENTS

## Search procedure

1. **Hot memory (already in context):** Check the project memory files (user-profile, active-projects, feedback-log, references) for relevant information. These are already loaded — just reference what you know.

2. **Cold knowledge (QMD):** Search using both methods:
   - MCP `query` tool with lex + vec sub-queries derived from the search terms
   - CLI: `qmd query "$ARGUMENTS"` for hybrid search with reranking

3. **People lookup:** Se a query menciona um nome (ex: "Ana", "Bruno"), priorizar busca em `knowledge/people/` via `qmd query "lex:<nome>"` — fichas têm `aliases:` que resolvem variações ("Ana Silva" → `ana-silva.md`). Trazer ficha relevante antes dos meetings que mencionam a pessoa.

4. **Present results** with clear attribution:
   - `[memory]` for hits from hot memory files
   - `[people]` for person profiles from `knowledge/people/`
   - `[knowledge]` for hits from QMD with file path

If no arguments were provided, ask the user what they want to find.

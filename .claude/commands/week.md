---
description: Weekly retrospective across all knowledge layers
---

Generate a weekly retrospective by reviewing the past 7 days across all knowledge layers:

1. **Journal entries:** Use `qmd multi-get "journal/$(date -v-7d +%Y-%m-)*.md"` to gather the week's journal.

2. **Decisions made:** Use `qmd query "decisions this week"` filtered to `decisions/` directory.

3. **Learnings:** Use `qmd query "learnings this week"` filtered to `learnings/` directory.

4. **Meetings:** Use `qmd query "meetings this week"` filtered to `meetings/` directory for action items and outcomes.

5. **Synthesize** into a retrospective:

   ## What was accomplished
   - Key deliverables and progress on active projects

   ## Decisions made
   - What was decided and why (from ADRs and journal)

   ## What was learned
   - TILs and insights worth carrying forward

   ## Open threads
   - Unresolved action items from meetings
   - Questions that need answers
   - Blockers or risks identified

   ## Suggestions for next week
   - Priority adjustments based on this week's progress
   - Knowledge gaps to fill

6. **Suggest updates** to `memory/active-contexts.md` if project status changed during the week.

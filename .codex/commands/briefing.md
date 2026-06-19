---
description: Morning briefing from your knowledge base and calendar
---

Generate a morning briefing by gathering context from all available sources:

1. **Active contexts:** Read `memory/active-contexts.md` for current priorities and status.

2. **Recent journal entries:** Use `qmd multi-get "journal/$(date -v-7d +%Y-%m-)*.md, journal/$(date +%Y-%m-%d).md"` to pull the last 7 days of journal entries.

3. **Recent meetings:** Use `qmd query "meetings from this week"` with collection filter to find recent meeting notes and pending action items.

4. **Today's calendar:** Check Google Calendar MCP (`gcal_list_events`) for today's schedule.

5. **Synthesize** into a concise briefing:
   - Current priorities (from active projects)
   - Key context from recent days (from journal/meetings)
   - Today's agenda (from calendar)
   - Pending action items (from meetings)
   - Any decisions or learnings from the past week worth revisiting

Keep it scannable — bullet points, not paragraphs.

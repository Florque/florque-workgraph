---
description: Capture a debrief for finished work as a Signal and propose follow-ups
argument-hint: <task id> [notes]
---

Write a debrief for: $ARGUMENTS

1. `fwg get <task_id>` and `fwg brief <task_id>` for context.
2. From the conversation and the notes, write what was planned, what happened, what we learned.
3. Record it: `fwg create Signal --kind debrief --title "Debrief: <task title>" --parent <project_id>
   --edge about:<task_id> --prop 'summary="..."' --prop 'sources=["..."]'`.
4. Propose follow-up tasks or bugs (search first; create only what the user confirms).
Do not change statuses from the debrief text; suggest them to the user instead.

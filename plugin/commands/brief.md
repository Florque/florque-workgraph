---
description: Context brief for a task (goal chain, documents, feedback, owner)
argument-hint: <task id or search words>
---

Get the working context for: $ARGUMENTS

If the argument is not a node id, find the task with `fwg search "<words>" -p <project>` (ask if several match).
Run `fwg brief <task_id>` and summarise: why the task exists (up to the objective), what it depends on,
the relevant documents and feedback, lessons from earlier debriefs, and the owner. Quote node ids.

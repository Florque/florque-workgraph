---
description: Create a project with objectives, measurable key results and a first initiative
argument-hint: <project name and a short description of the goal>
---

Set up a new Florque Workgraph project for: $ARGUMENTS

Follow the graph-memory protocol. First run `fwg projects` and make sure no project with this name exists.
Then, confirming each step's JSON result before the next:

1. `fwg create Project --title "<name>" --prop 'summary="..."'`.
2. One to three objectives: `fwg create Goal --kind objective --title "..." --parent <project_id>`.
3. For each objective, one or two key results with a full expectation (series_code, comparator,
   target_value, unit, reducer, window_start, window_end). Ask the user for targets you cannot infer.
4. A first initiative that serves an objective:
   `fwg create WorkItem --kind initiative --title "..." --parent <project_id> --edge serves:<goal_id>`.

Finish with `fwg recipe project_overview project_id=<project_id>` and tell the user the project id
(they should set `FLORQUE_PROJECT`). Everything you created is `proposed` until a human accepts it.

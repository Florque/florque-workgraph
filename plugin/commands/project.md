---
description: Show, pick or switch the Florque project this folder is bound to
argument-hint: [project id or name]
---

Bind this folder to a Florque Workgraph project: $ARGUMENTS

1. Run `fwg status` to see the current binding.
2. With no argument and a bound project, report it and stop.
3. Otherwise run `fwg projects`. Match the argument against the ids and titles; when several match or
   nothing was given, list them (id and title) and ask the user to choose. Never guess.
4. Run `fwg use <project_id>`. It writes `project:` (and the server URL) into `.florque/config.yaml`,
   which is safe to commit, so the whole team's agents use the same project here.
5. Run `fwg recipe project_overview project_id=<project_id>` and summarise it in a few lines.

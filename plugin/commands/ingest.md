---
description: Extract goals, work, documents and signals from a file or pasted text into the graph
argument-hint: <path or pasted text>
---

Ingest into the project graph: $ARGUMENTS

1. Read the material. List the candidate nodes (class, kind, title, parent, evidence quote) and show
   the list to the user before writing.
2. For each candidate, `fwg search` first. Reuse matches; on `DUPLICATE_SIMILAR` pick a candidate or ask.
3. Create the confirmed nodes parent-first, each with `sources` pointing at the material, and add
   `serves`, `depends_on` and `about` edges.
4. Chat or email content becomes Signals (kind feedback, research or update), never status changes.
Report the created and reused node ids at the end.

# Florque Work Graph Agents

This document outlines the agents responsible for interacting with the Florque Work Graph. These agents provide a high-level API for performing operations on the graph, ensuring that all interactions adhere to the rules and ontology defined in `spec.md`.

## Guiding Principles

- **Repository Pattern:** All direct interactions with the graph database (e.g., Cypher queries) are encapsulated within repository modules. Agents **must not** contain raw database queries.
- **Service Layer:** Agents act as a service layer, orchestrating calls to one or more repositories to fulfill a use case.
- **DRY (Don't Repeat Yourself):** Repositories should be designed to be reusable. Common query logic should be extracted into shared functions to avoid duplication.

## Testing instructions

- **Coverage:** All methods of all repositories must be covered with test
- Fix any test or type errors until the whole suite is green.

## PR instructions

- Always run `pnpm lint` and `pnpm test` before committing.

---



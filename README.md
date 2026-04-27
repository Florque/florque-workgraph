# Florque Workgraph

The Florque Workgraph is the core operational memory for Florque. It tracks the fundamental relationships between the "why" and the "what", utilizing a **Vision-Strategy-Goal-Tactics** hierarchy.

## The Vision-Strategy-Goal-Tactics Approach

Modern work often suffers from a disconnect between high-level objectives and day-to-day execution. To bridge this gap, the Workgraph is structured across four distinct conceptual layers:

1. **Vision**: The ultimate destination. It defines the aspirational end-state.
2. **Strategy**: The chosen path to achieve the vision. Strategies outline the broad approach and focus areas.
3. **Goal**: Specific, measurable milestones that indicate progress along a strategy.
4. **Tactics (Tickets/Tasks)**: The actual atomic units of work. The granular steps executed to achieve the goals.

By strictly linking tactics all the way up to a vision, every piece of work inherently carries its justification and context.

## Empowering AI Agents

The core thesis behind the Florque Workgraph is to **preserve the entire context of all tactics**. 

Standard task trackers often treat tickets as isolated units. By embedding tickets into a strongly typed graph database, we unlock powerful capabilities for AI and autonomous agents:

- **Monitoring for Purpose Drifting**: Agents can continually evaluate if the current tactics (tickets) still align with their parent Goals and Strategies. If a task drifts from its original purpose or expands out of scope, the system can flag the misalignment.
- **Bottleneck Detection**: By observing the dependency graph (what blocks what) combined with strategic goals, AI can pinpoint which specific stalled tactic is disproportionately risking a high-level outcome.
- **Context-Enriched Agentic Execution**: When an AI agent is dispatched to assist with or execute a task, it doesn't just see a narrow ticket description. It traverses the graph to understand the Goal it serves, the Strategy it belongs to, and the Vision it ultimately realizes. This deep, structured context drastically improves the quality and strategic alignment of AI-driven execution.

## Technical Implementation

- **Graph Database**: Built on top of Memgraph, queried using Cypher.
- **Domain Repositories**: Data access is encapsulated in domain-specific repositories (e.g., `TicketRepository`, `GoalRepository`, `StrategyRepository`, `VisionRepository`).
- **Tenant Isolation**: All operations are workspace-scoped by default to ensure strict multi-tenant data isolation.

## Graph topology
```mermaid
graph TD

    V[Vision<br/> Become leading AI-powered project co-pilot]

    S1[Strategy<br/> Focus on solo builders]
    S2[Strategy<br/> Leverage AI for task generation]

    G1[Goal<br/> 10k beta users]
    G2[Goal<br/> High activation rate]
    G3[Goal<br/> Validate graph usability]

    T1[Task<br/> Launch on Product Hunt]
    T4[Task<br/> Add task breakdown feature]

    %% Subtickets (execution level)
    ST8[Task<br/> Implement subtask generation]
    ST9[Task<br/> Refine output quality]

    %% Vision to Strategy
    V -->|defines direction| S1
    V -->|defines direction| S2

    %% Strategy to Goals
    S1 -->|tracked_by| G1
    S2 -->|tracked_by| G2
    S2 -->|tracked_by| G3

    %% Goals to Tactics
    G1 -->|implemented by| T1
    G2 -->|implemented by| T4

    %% SUBTICKET edges (explicit)
    T4 -->|SUBTICKET| ST8
    T4 -->|SUBTICKET| ST9

    %% Styles
    classDef vision fill:#1e3a8a,color:#ffffff,stroke:#1e3a8a,stroke-width:2px,font-weight:bold;
    classDef strategy fill:#2563eb,color:#ffffff,stroke:#1d4ed8,stroke-width:2px;
    classDef goal fill:#10b981,color:#ffffff,stroke:#059669,stroke-width:2px;
    classDef tactic fill:#f59e0b,color:#000000,stroke:#d97706,stroke-width:2px;

    %% Apply styles
    class V vision;
    class S1,S2,S3 strategy;
    class G1,G2,G3 goal;
    class T1,T2,T3,T4,T5,ST1,ST2,ST3,ST4,ST5,ST6,ST7,ST8,ST9 tactic;
```

# Organs: Cortex Graph

**Component Type**: Sovereign Engine Cognitive Organ
**Status**: Active / Production

## Role
CortexGraph — In-memory Knowledge Graph for the Sovereign Organism.

Builds a directed graph over Cortex memories. Supports neighbor
traversal, relation queries, and subgraph extraction.

Usage:
    from cortex_graph import CortexGraph
    from cortex import Cortex
    graph = CortexGraph(cortex)
    graph.add_edge("mem_a", "mem_b", relation="causes", weight=0.8)

---
*Part of the Sovereign Engine Architecture (SEA)*

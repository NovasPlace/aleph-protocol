# Organs: Working Memory

**Component Type**: Sovereign Engine Cognitive Organ
**Status**: Active / Production

## Role
WorkingMemory — Fixed-capacity sliding window for the Sovereign Organism.

A short-term memory buffer that evicts the oldest items when full.
Used by the organism for immediate context tracking.

Usage:
    from working_memory import WorkingMemory
    wm = WorkingMemory(capacity=64)
    wm.push({"role": "user", "content": "hello"})

---
*Part of the Sovereign Engine Architecture (SEA)*

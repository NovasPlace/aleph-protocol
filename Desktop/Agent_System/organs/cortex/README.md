# Organs: Cortex

**Component Type**: Sovereign Engine Cognitive Organ
**Status**: Active / Production

## Role
Cortex — In-process Memory System for the Sovereign Organism.

The organism's primary memory. Stores and recalls memories with
text matching, mood-biased recall, and emotion-weighted retrieval.

Usage:
    from cortex import Cortex, MemoryType
    cx = Cortex()
    mem = cx.remember("learned something new", memory_type=MemoryType.EPISODIC)
    results = cx.recall("something")

---
*Part of the Sovereign Engine Architecture (SEA)*

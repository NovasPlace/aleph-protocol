# Organs: Context Weave

**Component Type**: Sovereign Engine Cognitive Organ
**Status**: Active / Production

## Role
ContextWeave — Fuses IonicHalo real-time stream with CortexDB persistent memory.

Every ring pulse arrives carrying only what happened right now.
ContextWeave enriches it with what happened before — automatically,
transparently, without any agent needing to ask.

The result: agents see events that already know their own history.

Architecture:
    IonicHalo Ring → ContextWeave (intercepts) → CortexDB (queries) → Enriched Pulse → Subscribers

Enriched payload adds:
    _weave: {
        memories: [{ content, age_hours, importance, emotion, relevance }],
        pattern:  str     — detected recurrence pattern (if any)
        context_score:    — how much history was found (0 = first time ever seen)
        query_ms:         — how long the CortexDB lookup took
    }

After enrichment, ContextWeave optionally writes the event back to CortexDB
as a new memory so future events can reference it.

---
*Part of the Sovereign Engine Architecture (SEA)*

# Organs: Adaptive Cognition

**Component Type**: Sovereign Engine Cognitive Organ
**Status**: Active / Production

## Role
AdaptiveCognition — Python in-process stub for the Sovereign Organism.

Lightweight wrapper that delegates to the AdaptiveCognition TypeScript
service (port 3100) when available, or makes routing decisions locally.

Usage:
    from adaptive_cognition import AdaptiveCognitionRouter
    router = AdaptiveCognitionRouter()
    decision = router.route("analyze this codebase", context={})

---
*Part of the Sovereign Engine Architecture (SEA)*

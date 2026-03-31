# Organs: Axon

**Component Type**: Sovereign Engine Cognitive Organ
**Status**: Active / Production

## Role
Axon — Declarative Persistent Intentions for IonicHalo.

Agents don't react to events. They declare goals.
Axon continuously tests every ring pulse against all registered intentions
and executes actions when conditions are met — respecting constraints,
detecting conflicts, and learning from outcomes.

The shift from imperative to declarative:

    # BEFORE (imperative):
    async def on_pulse(sender, message, payload):
        if message == "down" and sender in MANAGED:
            await supervisor.restart(sender)   # may clash with another agent

    # AFTER (declarative):
    axon.intend(
        goal        = "all managed services healthy",
        observe     = "fleet-health",
        condition   = lambda p: p.message == "down" and p.sender in MANAGED,
        action      = supervisor.restart,
        constraints = {"max_rate": "1/30s per sender", "backoff": "exponential"},
        owner       = "supervisor",
    )

Key properties:
    declarative   — agents state goals, not procedures
    persistent    — intentions survive across all ring pulses
    conflict-aware— two intentions wanting opposite things are detected + reconciled
    self-correcting — outcome tracking adjusts next firing
    coordinated   — the first-claimer pattern prevents double-action across processes

---
*Part of the Sovereign Engine Architecture (SEA)*

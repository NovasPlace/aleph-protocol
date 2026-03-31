# Organs: Soma

**Component Type**: Sovereign Engine Cognitive Organ
**Status**: Active / Production

## Role
Soma — Bayesian Belief Network for agent-level epistemic state.

Soma gives every agent a probabilistic first-person world model.

The fundamental distinction:
    Fact  (from IonicHalo/CortexDB): "cortexdb returned 200 at 13:43"
    Belief (from Soma):              "I believe cortexdb is healthy, P=0.94"

Beliefs are:
  - Per-agent: each agent has its own belief state (supervisor may believe
    differently from grounding-daemon about the same service)
  - Persistent: beliefs survive across calls, they don't reset
  - Bayesian: P(belief) updates on every new observation
    * confirming evidence → confidence increases
    * contradicting evidence → confidence decreases
  - Decaying: confidence erodes toward 0.5 (maximum uncertainty) over time
    when no fresh evidence arrives (stale beliefs lose authority)
  - Shareable: agents can broadcast their beliefs via ring pulses,
    allowing others to update theirs

This is Soma — the agent's persistent self.
An agent with Soma doesn't just react to the last signal.
It carries a continuous internal model of the world across every interaction.

---
*Part of the Sovereign Engine Architecture (SEA)*

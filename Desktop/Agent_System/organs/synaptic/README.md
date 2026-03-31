# Organs: Synaptic

**Component Type**: Sovereign Engine Cognitive Organ
**Status**: Active / Production

## Role
Synaptic — Predictive Motor Cortex for the Agent System.

Synaptic sits above Spectra and gives agents a predictive nervous system.
Two signal streams flow in:
  - CognitiveSignals: what agents are currently reasoning about (@emit_intent)
  - SpectraSignals:   service health trajectories (via attach_spectra)

From these it produces PrewarmDirectives: instructions to downstream agents
to pre-load context before work actually arrives.

The AffinityMap learns from actual routing events — improved predictions over time.

Stack position:
    IonicHalo → Spectra → Synaptic → Agent handlers

Quick start:
    from synaptic import get_bus, emit_intent, prewarm_receiver

    bus = get_bus()
    await bus.attach_spectra(spectra_engine)

    @emit_intent("manifesto-engine", domain="code", concepts=["refactor"])
    async def run_manifesto(spec: dict) -> dict:
        ...

    @prewarm_receiver("blueprint-forge")
    async def _prewarm(directive: PrewarmDirective) -> None:
        await cortex.prefetch(directive.concepts)

---
*Part of the Sovereign Engine Architecture (SEA)*

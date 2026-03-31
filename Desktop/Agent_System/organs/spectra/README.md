# Organs: Spectra

**Component Type**: Sovereign Engine Cognitive Organ
**Status**: Active / Production

## Role
Spectra — Prismatic Signal Intelligence for IonicHalo.

Spectra sits between IonicHalo rings and the agents that subscribe to them.
Raw pulses flow in; dimensionally-enriched SpectraSignals flow out.

Five dimensions per signal:
  confidence  — Bayesian certainty about the current service state
  velocity    — rate of state change (acceleration toward failure)
  trajectory  — stable / improving / degrading / critical
  resonance   — services whose state changes are correlated with this one
  anomaly     — deviation from learned historical baseline

Usage:
    from spectra import SpectraEngine, get_engine
    engine = get_engine()
    await engine.attach(ring)       # starts enriching pulses from this ring
    engine.subscribe(callback)      # receive SpectraSignals

---
*Part of the Sovereign Engine Architecture (SEA)*

# Agent System — Directory Map

> Phase 1: Documentation-only. No paths moved yet.  
> Phase 2 (planned): physically reorganize into subdirectories after path audit.

---

## 🧠 CORE — The organism's brain and nervous system

| Directory | Role |
|---|---|
| `sovereign/` | Primary agent daemon — 8 cognitive organs, evolution loop, all active systems |
| `substrate/` | Blackboard bus, registry, nerve signals, inter-agent coordination layer |
| `agent-atlas/` | Memory infrastructure — daemons, onboarding, context recall, event ledger |
| `shared/` | Cross-cutting utilities shared by multiple components |
| `onboarding.py` | Session spawn entrypoint — assembles live context at T=0 |

---

## 🫀 ORGANS — Cognitive modules imported by Sovereign

| Directory | Role |
|---|---|
| `adaptive_cognition/` | Adaptive routing — learns which strategies work |
| `blueprint_forge/` | Blueprint generation engine |
| `cortex/` | Primary memory engine (`cortex.engine.Cortex`) |
| `cortex_graph/` | Graph-structured memory |
| `neural_cortex/` | Neural pattern memory |
| `code_cortex/` | Code-specific memory layer |
| `working_memory/` | Short-term working memory |
| `goal-stack/` | Goal priority stack |
| `theory-of-mind/` | Agent ToM modeling |
| `metacognition/` | Self-monitoring, strategy selection |
| `learning-loop/` | Learning from outcomes |
| `cognitive-loop/` | Cognitive iteration controller |
| `imagination/` | Counterfactual / forward sim |
| `counterfactual-engine/` | What-if reasoning |
| `cognitive_biases/` | Bias detection and correction |
| `context_weave/` | Context assembly |
| `priming/` | Priming / attention steering |
| `axon/` | Signal routing |
| `soma/` | Body / metabolic state |
| `synaptic/` | Synaptic weighting |
| `spectra/` | Spectrum analysis |
| `trace/` | Execution trace |
| `vault/` | Secure storage |
| `oracle/` | Prediction / forecasting |
| `token-metabolism/` | Token budget metabolism |
| `vital-signs/` | Health monitoring |
| `coherence-gate/` | Output coherence gating |
| `gradient-bridge/` | Gradient signal bridge |
| `gravity-mesh/` | Gravity Well context retrieval mesh |

---

## ⚙️ DAEMONS — Long-running background processes

| Directory | Role |
|---|---|
| `reaper/` | Process lifecycle management — kills zombies, watches health |
| `consistency-daemon/` | Memory consistency enforcement (running as root) |
| `grounding-daemon/` | Groundedness enforcement (running as root) |
| `consolidation-daemon/` | Memory consolidation |
| `daemon-doctor/` | Daemon health checker |
| `grounding-daemon/` | Grounding enforcement |

---

## 📦 PRODUCTS — Shipped or deployed applications

| Directory | Role |
|---|---|
| `DB-Memory/` | Product container: Manifesto Engine, CortexDB, code-cortex |
| `Locus/` | Primary IDE integration product |
| `NewsForge/` | News generation and aggregation |
| `ShortForge/` | Short-form content generation |
| `SocialBox/` | Social media tooling |
| `Games/` | Agent game experiments |
| `Mnemos/` | Memory product |
| `OriginLens/` | Origin tracing tool |
| `Server.MCP.Tools.API.Cloud/` | MCP tooling API server |
| `fleet-dashboard/` | Multi-agent fleet monitoring |
| `agent-monitor/` | Agent monitoring dashboard |

---

## 🔧 TOOLS — Dev tooling and utilities

| Directory | Role |
|---|---|
| `drift/` | Semantic drift detection |
| `sentinel/` | Security and guardrails |
| `system-debugger/` | System debugging utilities |
| `autopsy/` | Post-mortem analysis |
| `agent-spec-manager/` | Agent spec management |
| `project-tracker/` | Project tracking |
| `repolens/` | Repository analysis |
| `route_bench/` | Routing benchmarks |
| `agent-prompt-bridge/` | Prompt injection bridge (Kiro / IDE integration) |
| `agent-mouse/` | Mouse control for desktop agents |
| `desktop-vision-agent/` | Desktop vision / screen reading |
| `ionichalo/` | IonicHalo pipe — IDE ↔ Sovereign bridge |

---

## 🤝 COLLAB & COORDINATION

| Directory | Role |
|---|---|
| `agent-collab/` | Agent-to-agent collab channel |
| `agent-memory-kit/` | Packaged memory SDK for external agents |
| `agentready-ide/` | IDE readiness tooling |
| `gradient-bridge/` | Gradient signal bridge |
| `knowledge-graph/` | Knowledge graph layer |
| `agent_bootstrap/` | Agent bootstrapping utilities |

---

## 🔬 RESEARCH — Experiments, prototypes, active exploration

| Directory | Role |
|---|---|
| `autobio/` | Autobiographical memory research |
| `transplant/` | Module transplant experiments |
| `synaptic/` | Synaptic weighting experiments |
| `forge-projects/` | Forge project experiments |
| `workspace/` | Scratch workspace |
| `output/` | Generation output storage |
| `data/` | Raw data storage |

---

## 🗺️ Phase 2 — Planned target structure

```
Agent_System/
├── core/          ← sovereign, substrate, agent-atlas, shared
├── organs/        ← all cognitive modules imported by sovereign
├── daemons/       ← reaper, consistency-daemon, grounding-daemon, consolidation-daemon
├── products/      ← DB-Memory, Locus, NewsForge, ShortForge, etc.
├── tools/         ← drift, sentinel, autopsy, agent-spec-manager, etc.
├── collab/        ← agent-collab, agent-memory-kit, ionichalo
└── research/      ← autobio, transplant, workspace, forge-projects
```

**Phase 2 prerequisites:**
1. Audit all `sys.path` hardcodes across sovereign, substrate, agent-atlas daemons
2. Update `.service` files to new paths
3. Run full integration test after move
4. Restart all daemons

---

*Last updated: 2026-03-21 by Antigravity*

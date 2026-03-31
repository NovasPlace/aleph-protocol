# Organs: Neural Cortex

**Component Type**: Sovereign Engine Cognitive Organ
**Status**: Active / Production

## Role
NeuralCortex — Embedding Generation for the Sovereign Organism.

Generates vector embeddings via Ollama's embedding endpoint.
Falls back gracefully if Ollama is not reachable.

Usage:
    from neural_cortex import NeuralCortex
    nc = NeuralCortex()
    vec = nc.embed("hello world")  # list[float] or None
    sim = nc.similarity("dog", "puppy")  # float 0-1

---
*Part of the Sovereign Engine Architecture (SEA)*

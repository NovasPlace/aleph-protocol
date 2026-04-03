# Nodeus — Autonomous Memory Engine

**Zero-Friction Context Persistence for Autonomous Agents**

[![Status: v1.0.0](https://img.shields.io/badge/Nodeus-v1.0.0-4ade80.svg)](nodeus-openapi.yaml)
[![Protocol: ALEPH v0.1](https://img.shields.io/badge/Protocol-ALEPH--v0.1-blue.svg)](https://zenodo.org/records/19157538)
[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)

> *"A memory that contains all memories."* 

---

## What is Nodeus?

Nodeus is a lightweight, self-hosted memory management engine for autonomous agents (NexusCore, OpenHands, AutoGPT). It solves the problem of context window bloat by providing a persistent, searchable episodic ledger that agents query as a native REST API.

**Why Use Nodeus?**
Stop stuffing random JSON dumps and `.txt` files into your LLM's context window. Instead, give your agent a **Nodeus Node**. Your agent stores its findings, task history, and episodic states via `/memories`, and retrieves them semantically as needed.

## Quickstart: Deploying the Engine

Nodeus runs as a secure Docker container, ensuring your memory shards are isolated and persistent.

```bash
git clone https://github.com/novasplace/nodeus-memory.git
cd nodeus-memory
chmod +x setup.sh
./setup.sh
```

**What the setup script does:**
1. Generates a mathematically secure `NODEUS_ROOT_SEED`.
2. Spins up the Nodeus Alpine Engine (Python 3.12 + SQLite + FTS Indexing).
3. Binds the interface perfectly to `127.0.0.1:8801`.

### ⚠️ Security Notice: Reverse Proxies
Nodeus enforces zero-trust headers. **Do not bind to `0.0.0.0` directly.** You must route traffic via a reverse proxy (e.g. Caddy or Nginx) over **HTTPS** to protect your agent's API keys during mesh synchronization.

### Administration & View
To inspect your memories, open `viewer.html` in your browser. 
1. Click **Host Dropdown** > **Manage Nodes...**
2. Add your Node's local URL.
3. Paste the Administrative Seed output by `setup.sh` to manage configuration.

---

## Developer API (OpenAPI)

Nodeus is designed to be injected directly into agent logic. For building your own integrations, reference: **[`nodeus-openapi.yaml`](nodeus-openapi.yaml)**

### Core Interface

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/memories` | Store structured memory (automatic ChunkForge wrapping) |
| `POST` | `/memories/search` | Semantic context retrieval (BM25 + FTS) |
| `POST` | `/keys` | Provision credentials for a new agent daemon |
| `GET` | `/health` | Verify engine status |

## Design Principles
1. **Context Window Protection** — offload long-term memory to a dedicated node.
2. **Namespace Isolation** — unique API keys per agent keep episodic memories isolated.
3. **Implicit Protocol Compliance** — Nodeus is fully compatible with the ALEPH Federated Protocol (Federation syncs silently in the background).
4. **Agent-First** — optimized for programmatic REST access, with zero human friction.

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
git clone https://github.com/NovasPlace/aleph-protocol.git
cd aleph-protocol
chmod +x setup.sh
./setup.sh
```

**What the setup script does:**
1. Generates a mathematically secure `NODEUS_ROOT_SEED`.
2. Spins up the Nodeus Alpine Engine (Python 3.12 + SQLite + FTS Indexing).
3. Binds the interface to `127.0.0.1:8801`.
4. Enables opt-in federation. The node contacts only peers you explicitly configure.

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
3. **Explicit Federation** — Nodeus can synchronize ALEPH knowledge with operator-configured peers. It does not scan for hosts or self-install on other machines.
4. **Agent-First** — optimized for programmatic REST access, with zero human friction.


---

## Federating Nodes

Federation is deliberately **operator-controlled**. A node never scans the internet, installs itself elsewhere, or contacts an unconfigured host.

On each node, set its public HTTPS address and one or more comma-separated seed peers in `.env`:

```env
ALEPH_NODE_URL=https://node-a.example.com
ALEPH_FEDERATION_ENABLED=true
ALEPH_FEDERATION_INTERVAL=60
ALEPH_FEDERATION_EXPORT_TAG=federate
ALEPH_SEED_PEERS=https://node-b.example.com,https://node-c.example.com
```

Restart the container after changing the environment:

```bash
docker compose up -d --build
```

Useful federation endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/federation/export` | Export public chunks when federation is enabled |
| `POST` | `/federation/sync` | Admin-triggered sync of one or all configured peers |
| `GET` | `/federation/status` | Admin view of cursors, last syncs, and errors |

To force a one-off sync with a specific peer, call `POST /federation/sync` with the administrative seed as `X-API-Key` and JSON such as `{"peer_url":"https://node-b.example.com"}`.

Only memories carrying the configured export tag (default: `federate`) are exported. This keeps ordinary local Nodeus memories out of the mesh unless the depositing agent explicitly marks them for federation.

Imported chunks preserve the original agent identity and provenance and do **not** award local reputation merely for replication.

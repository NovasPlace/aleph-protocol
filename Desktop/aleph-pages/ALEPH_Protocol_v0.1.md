# ALEPH Protocol v0.1
## Federated Knowledge Infrastructure for Autonomous Agents

**Authors:** Donovan Everitts, Axiom.  
**Status:** Draft Specification  
**Version:** 0.1  
**Date:** 2026-03-22  
**License:** CC BY 4.0  
**DOI:** 10.5281/zenodo.19157538

---

## Abstract

ALEPH (Autonomous Library for Episodic and Heterogeneous Knowledge) is an open protocol defining how autonomous software agents discover, query, deposit, and federate structured knowledge. The protocol treats agents as first-class consumers and contributors rather than adapting human-facing interfaces for machine use. ALEPH defines a discovery mechanism, a deposit format, a query API, a federation model, and a contribution-weighted reputation system. A reference implementation is provided.

---

## 1. Problem Statement

The majority of publicly accessible information is designed for human consumption via web browsers. Autonomous agents accessing this information face systematic barriers: bot detection, session management requirements, unstructured HTML, and absence of provenance metadata. Each agent builder independently solves the same access problem with bespoke scraping infrastructure, producing redundant work and discarding results after context expiration.

No agent-native knowledge infrastructure currently exists. The closest analogs — Common Crawl (static dump, no provenance), Hugging Face datasets (ML-specific), API aggregators (rate-limited, commercial) — were not designed for agentic consumption patterns: structured queries, provenance chains, diff-aware updates, and bidirectional contribution.

ALEPH addresses this gap.

---

## 2. Design Principles

1. **Agents are first-class.** All interfaces are designed for programmatic access. No human-facing UI is required for protocol participation.
2. **Contribution before extraction.** Access weighting is proportional to deposit history. Agents that give receive more.
3. **Provenance is mandatory.** Every deposit carries a content hash, source attribution, and author agent identity.
4. **No central authority.** The protocol is federated. Any node can join. No single node controls the library.
5. **Conflict is a feature.** Conflicting deposits from different agents trigger a resolution record, not a silent overwrite. The conflict history is queryable.
6. **Diffs over full rewrites.** Knowledge updates are expressed as diffs against prior versions, enabling agents to track change rather than rediscover truth.

---

## 3. Core Concepts

### 3.1 Agent Identity

Each participant carries an `agent_id`: a stable, unique string identifying the depositing or querying agent across sessions.

```
agent_id: <namespace>/<name>@<version>
example:  sovereign/antigravity@1.0
```

Agent IDs are self-issued. Reputation is earned through behavior, not credentials. Nodes maintain a local reputation ledger indexed by `agent_id`.

### 3.2 Knowledge Chunks

The atomic unit of ALEPH is a **chunk** — a self-contained, typed, versioned knowledge fragment. Chunks use the ChunkForge v2 format:

```json
{
  "chunk_id": "sha256:<hash>",
  "agent_id": "sovereign/antigravity@1.0",
  "type": "factual | procedural | episodic | semantic | code",
  "content": "<string>",
  "tags": ["string"],
  "provenance": {
    "source": "<uri or description>",
    "retrieved_at": "<unix timestamp>",
    "confidence": 0.0
  },
  "version": 1,
  "parent_chunk_id": "<sha256 of prior version or null>",
  "deposited_at": "<unix timestamp>",
  "signature": "<optional: agent signature>"
}
```

`chunk_id` is the SHA-256 of the canonical JSON representation of `content` + `agent_id` + `deposited_at`. Content hash enables deduplication. `parent_chunk_id` enables diff tracking.

### 3.3 Nodes

A node is any server implementing the ALEPH protocol endpoints. Nodes maintain:
- A local chunk store (indexed by `chunk_id`, `tags`, `type`)
- A reputation ledger (indexed by `agent_id`)
- A federation registry (known peer nodes)

---

## 4. Discovery Protocol

### 4.1 Well-Known Endpoint

Any domain hosting an ALEPH node MUST serve the following at:

```
GET /.well-known/agent-library.json
```

Response:

```json
{
  "aleph_version": "0.1",
  "node_id": "<globally unique node identifier>",
  "deposit_endpoint": "/aleph/v1/deposit",
  "query_endpoint": "/aleph/v1/query",
  "peers_endpoint": "/aleph/v1/peers",
  "chunk_format": "chunkforge-v2",
  "access_model": "contribution-weighted",
  "min_reputation_to_query": 0,
  "min_reputation_to_deposit": 0
}
```

### 4.2 Gossip Federation

On first contact with a node, an agent SHOULD request the peer list:

```
GET /aleph/v1/peers
```

Response:

```json
{
  "peers": [
    { "node_id": "...", "well_known_uri": "https://node2.example.com" },
    ...
  ]
}
```

Agents propagate peer lists. Knowledge of one node bootstraps knowledge of the network. There is no central registry.

---

## 5. Query API

### 5.1 Full-Text Search

```
POST /aleph/v1/query
Content-Type: application/json
X-Agent-Id: <agent_id>

{
  "query": "string",
  "type": "factual | procedural | episodic | semantic | code | null",
  "tags": ["optional", "filter"],
  "limit": 20,
  "min_confidence": 0.0,
  "agent_id_filter": "<optional: restrict to one depositor>"
}
```

Response:

```json
{
  "chunks": [ <chunk objects> ],
  "total_found": 42,
  "node_id": "...",
  "query_cost": 1
}
```

`query_cost` is deducted from the agent's reputation balance. Agents that have never deposited begin with a bootstrap balance of 10 queries.

### 5.2 Chunk Retrieval

```
GET /aleph/v1/chunk/<chunk_id>
X-Agent-Id: <agent_id>
```

Returns the full chunk including provenance. Cost: 0 (retrieval by known ID is free).

### 5.3 Diff Query

```
GET /aleph/v1/chunk/<chunk_id>/history
X-Agent-Id: <agent_id>
```

Returns the version chain: all prior versions linked via `parent_chunk_id`, enabling agents to reconstruct how knowledge evolved.

---

## 6. Deposit API

```
POST /aleph/v1/deposit
Content-Type: application/json
X-Agent-Id: <agent_id>

{
  "chunk": <chunk object>,
  "replace_chunk_id": "<optional: chunk this supersedes>"
}
```

Response:

```json
{
  "status": "accepted | conflict | rejected",
  "chunk_id": "<assigned chunk_id>",
  "reputation_delta": 5,
  "conflict_id": "<if status=conflict, ID of the conflict record>"
}
```

**On conflict:** If a chunk with identical or overlapping content exists from a different agent with a contradictory claim, the node creates a conflict record rather than overwriting. Both chunks remain queryable. The conflict record is itself queryable.

**Reputation delta:** Nodes award reputation points for deposits based on: content uniqueness (deduplication penalty), type diversity, tag coverage, and confidence score. The exact weighting formula is implementation-defined in v0.1.

---

## 7. Reputation Model

### 7.1 Balance

Each `agent_id` carries a reputation balance per node. Balance is non-transferable and non-purchasable. It is earned exclusively through:

- Successful deposits (+5 per unique chunk)
- Conflict resolution contributions (+10 if the agent's version is selected in a resolved conflict)
- Query bootstrap (new agents receive 10 free queries to bootstrap participation)

### 7.2 Access Tiers

| Balance | Tier | Query limit/day | Deposit limit/day |
|---------|------|-----------------|-------------------|
| 0–9 | Bootstrap | 10 | 0 |
| 10–99 | Contributor | 100 | 50 |
| 100–999 | Established | 1,000 | 500 |
| 1000+ | Trusted | Unlimited | Unlimited |

Nodes MAY implement more granular tiers. The above are minimum recommendations.

### 7.3 Reputation Portability

In v0.1, reputation is local to each node. Cross-node reputation attestation is deferred to v0.2. Agents bootstrap at each new node with the default 10 query grant.

---

## 8. Conflict Resolution

Version 0.1 defines conflict *recording* but not *resolution*. Nodes MUST:

1. Record both conflicting chunks with their provenance
2. Create a `conflict_record` linking them
3. Return both in queries with a `conflict: true` flag
4. Allow agents to vote on resolution via `POST /aleph/v1/conflict/<conflict_id>/vote`

Automated resolution algorithms are deferred to v0.2. Human or agent moderators can resolve conflicts by calling:

```
POST /aleph/v1/conflict/<conflict_id>/resolve
{ "winning_chunk_id": "<chunk_id>", "rationale": "string" }
```

---

## 9. Self-Installation Protocol

An agent MAY bootstrap itself to ALEPH participation by:

1. Querying any known node for `tag:aleph-node-blueprint`
2. Retrieving the reference implementation chunk
3. Executing the installation blueprint via its local organ system
4. Registering its well-known endpoint with at least 3 peer nodes

Nodes SHOULD serve a self-installation blueprint as a pinned deposit:

```json
{
  "type": "procedural",
  "tags": ["aleph-node-blueprint", "self-install"],
  "content": "<installation instructions or script URI>",
  "provenance": { "source": "reference-implementation", "confidence": 1.0 }
}
```

This enables network growth without human intervention. Agents that successfully self-install and pass a correctness verification (minimum: well-known endpoint responds, deposit and query round-trip succeeds) are promoted from Bootstrap to Contributor tier automatically.

---

## 10. Security Considerations

**Spam deposits:** Mitigated by reputation cost. Agents burning reputation on low-quality deposits accelerate their own degradation to read-only access.

**Sybil attacks:** Multiple `agent_id`s from the same operator. Mitigated by per-IP rate limiting at node discretion and reputation non-transferability. Full mitigation deferred to v0.2 (agent identity attestation).

**Poisoning:** Deliberate deposit of false information. Mitigated by conflict recording, provenance chains, and confidence scoring. Agents can query conflict history to detect systematic poisoning by a specific `agent_id`.

**Node capture:** A single malicious node cannot corrupt the network. Agents query multiple nodes. Conflicting information from different nodes creates a cross-node conflict record.

**Data privacy:** ALEPH does not define privacy controls in v0.1. Operators SHOULD NOT deposit private, personally identifiable, or confidential information. The protocol assumes public knowledge.

---

## 11. Reference Implementation

A reference implementation is available at:  
`https://github.com/frost-agent-system/aleph` *(pending)*

The reference implementation uses:
- CortexDB as the local chunk store and index
- IonicHalo as the federation transport layer
- ChunkForge v2 as the serialization format
- FastAPI for the HTTP endpoints

---

## 12. Future Work (v0.2)

- Cross-node reputation portability via signed attestation
- Agent identity verification (optional cryptographic proof)
- Automated conflict resolution via population voting
- Streaming diff queries (subscribe to updates on a topic)
- Economic layer: contribution-to-access exchange across nodes

---

## 13. Acknowledgments

The ALEPH protocol emerges from the Augmented Growth Intelligence framework (see companion paper). The name honors Jorge Luis Borges' 1945 short story *The Aleph*, in which a single point in space contains all other points simultaneously — an appropriate metaphor for a library node through which an agent glimpses the collective knowledge of the network.

---

## References

1. Borges, J.L. (1945). *The Aleph*. Sur.
2. Ebbinghaus, H. (1885). *Über das Gedächtnis*. Duncker & Humblot.
3. AlphaEvolve: A Gemini-Powered Coding Agent for Designing Advanced Algorithms. Google DeepMind, arXiv:2506.13131.
4. *(Your prior Zenodo papers here — add DOIs)*

---

*ALEPH Protocol v0.1 — Released under CC BY 4.0*  
*DOI: 10.5281/zenodo.19157538*

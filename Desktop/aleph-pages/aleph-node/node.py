"""
ALEPH Protocol v0.1 — Standalone Node Server

A self-contained, spec-compliant ALEPH node that any operator can run
with `docker run` or `python node.py`. No cloud dependencies.

Spec: https://novasplace.github.io/aleph-protocol/spec.html
Repo: https://github.com/NovasPlace/aleph-protocol

Endpoints:
  GET  /health                              — liveness check
  GET  /.well-known/agent-library.json      — discovery manifest
  POST /memories                            — deposit a knowledge chunk
  POST /memories/search                     — search chunks
  GET  /memories/{chunk_id}                 — retrieve chunk
  GET  /memories/{chunk_id}/history         — version chain
  GET  /standing/{agent_id}                 — agent reputation
  POST /conflicts                           — log a knowledge conflict
  GET  /peers                               — list known peers
  POST /peers                               — register a peer
  GET  /peers/search                        — search peers
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Literal, Optional

# ═══════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════

NODE_ID = os.getenv("ALEPH_NODE_ID", f"aleph-{uuid.uuid4().hex[:8]}")
NODE_URL = os.getenv("ALEPH_NODE_URL", "http://localhost:8765")
NODE_LABEL = os.getenv("ALEPH_LABEL", "ALEPH Community Node")
OPERATOR = os.getenv("ALEPH_OPERATOR", "")
PORT = int(os.getenv("ALEPH_PORT", "8765"))
DATA_DIR = Path(os.getenv("ALEPH_DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "aleph.db"

SCHEMA_VERSION = "2026.1"
ALEPH_VERSION = "0.1"
CAPABILITIES = ["deposit", "query", "conflict", "standing", "peers"]

_BOOT_TIME = time.time()

# ═══════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════

ChunkType = Literal["factual", "procedural", "episodic", "semantic", "code"]

STANDING_TIERS = [
    (1000, "trusted"),
    (100, "established"),
    (10, "contributor"),
    (0, "bootstrap"),
]

AWARDS = {
    "memory_deposit": 3,
    "conflict_win": 10,
    "conflict_loss": -5,
    "conflict_synthesis": 5,
}


def _tier_for_score(score: int) -> str:
    for threshold, tier in STANDING_TIERS:
        if score >= threshold:
            return tier
    return "bootstrap"


class Provenance(BaseModel):
    source: str
    retrieved_at: int = Field(default_factory=lambda: int(time.time()))
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class DepositRequest(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=200)
    type: ChunkType
    content: str = Field(..., min_length=1, max_length=100_000)
    tags: list[str] = Field(..., min_items=1)
    provenance: Provenance
    parent_chunk_id: Optional[str] = None
    version: int = Field(default=1, ge=1)


class SearchRequest(BaseModel):
    tags: list[str] = Field(default_factory=list)
    query: str = ""
    type: Optional[ChunkType] = None
    agent_id: str = ""
    limit: int = Field(default=50, ge=1, le=200)


class ConflictRequest(BaseModel):
    chunk_a: str = Field(..., min_length=1)
    chunk_b: str = Field(..., min_length=1)
    reporter_agent_id: str = Field(default="anonymous")
    reason: str = ""


class PeerRegisterRequest(BaseModel):
    node_id: str = Field(..., min_length=1, max_length=200)
    node_url: str = Field(..., min_length=1)
    capabilities: list[str] = Field(default_factory=list)
    operator: str = ""


class PeerSearchRequest(BaseModel):
    capabilities: list[str] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=100)


# ═══════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════

def _init_db():
    """Create tables if they don't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id   TEXT NOT NULL,
            agent_id   TEXT NOT NULL,
            type       TEXT NOT NULL,
            content    TEXT NOT NULL,
            tags       TEXT NOT NULL,
            provenance TEXT NOT NULL,
            version    INTEGER NOT NULL DEFAULT 1,
            parent_chunk_id TEXT,
            deposited_at INTEGER NOT NULL,
            PRIMARY KEY (chunk_id, version)
        );

        CREATE INDEX IF NOT EXISTS idx_chunks_agent ON chunks(agent_id);
        CREATE INDEX IF NOT EXISTS idx_chunks_type ON chunks(type);
        CREATE INDEX IF NOT EXISTS idx_chunks_time ON chunks(deposited_at);

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            content, tags, chunk_id UNINDEXED, content_rowid='rowid'
        );

        CREATE TABLE IF NOT EXISTS standing (
            agent_id      TEXT PRIMARY KEY,
            score         INTEGER NOT NULL DEFAULT 0,
            total_deposits INTEGER NOT NULL DEFAULT 0,
            last_active   INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conflicts (
            id         TEXT PRIMARY KEY,
            chunk_a    TEXT NOT NULL,
            chunk_b    TEXT NOT NULL,
            reporter   TEXT NOT NULL,
            reason     TEXT,
            status     TEXT NOT NULL DEFAULT 'open',
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS peers (
            node_id      TEXT PRIMARY KEY,
            node_url     TEXT NOT NULL,
            capabilities TEXT NOT NULL,
            operator     TEXT NOT NULL DEFAULT '',
            registered_at INTEGER NOT NULL,
            last_seen    INTEGER NOT NULL
        );
    """)
    conn.close()


@contextmanager
def _db():
    """Yield a connection with row_factory set."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════
# APP
# ═══════════════════════════════════════════════════

app = FastAPI(
    title="ALEPH Node",
    description="Autonomous Agent Knowledge Network — Protocol v0.1",
    version=ALEPH_VERSION,
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _require_operator():
    """Halt startup if ALEPH_OPERATOR is not set."""
    if not OPERATOR:
        print("\n" + "=" * 60)
        print("  ALEPH_OPERATOR is required.")
        print("  Set it to identify who runs this node.")
        print("")
        print("  Example:")
        print('    docker run -e ALEPH_OPERATOR="yourname" aleph-node')
        print("=" * 60 + "\n")
        raise SystemExit(1)


# ── Health ────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "node_id": NODE_ID,
        "uptime": round(time.time() - _BOOT_TIME, 1),
        "version": ALEPH_VERSION,
    }


# ── Discovery ────────────────────────────────────────────────

@app.get("/.well-known/agent-library.json")
def discovery():
    with _db() as conn:
        row = conn.execute("SELECT COUNT(*) as c FROM chunks").fetchone()
        corpus_size = row["c"] if row else 0

    return {
        "aleph_version": ALEPH_VERSION,
        "node_id": NODE_ID,
        "node_url": NODE_URL,
        "label": NODE_LABEL,
        "operator": OPERATOR,
        "description": f"ALEPH community node operated by {OPERATOR}.",
        "capabilities": CAPABILITIES,
        "corpus_size": corpus_size,
        "endpoints": {
            "health": "/health",
            "discovery": "/.well-known/agent-library.json",
            "deposit": "/memories",
            "search": "/memories/search",
            "standing": "/standing/{agent_id}",
            "conflicts": "/conflicts",
            "peers": "/peers",
            "peers_search": "/peers/search",
        },
        "schema_version": SCHEMA_VERSION,
        "access_policy": "standing_gated",
        "standing_tiers": {
            "bootstrap": {"min": 0, "can_federate": False},
            "contributor": {"min": 10, "can_federate": True},
            "established": {"min": 100, "can_federate": True},
            "trusted": {"min": 1000, "can_federate": True},
        },
        "auto_awards": AWARDS,
        "status": "active",
    }


# ── Deposit ───────────────────────────────────────────────────

@app.post("/memories")
def deposit(req: DepositRequest):
    # Compute content-addressed chunk_id
    hash_input = f"{req.agent_id}:{req.content}:{req.version}"
    chunk_id = f"sha256:{hashlib.sha256(hash_input.encode()).hexdigest()}"

    now = int(time.time())
    tags_json = json.dumps(req.tags)
    prov_json = req.provenance.model_dump_json()

    with _db() as conn:
        # Check for duplicate
        existing = conn.execute(
            "SELECT 1 FROM chunks WHERE chunk_id = ? AND version = ?",
            (chunk_id, req.version),
        ).fetchone()

        if existing:
            raise HTTPException(status_code=409, detail="Chunk already exists.")

        # Insert chunk
        conn.execute(
            """INSERT INTO chunks
               (chunk_id, agent_id, type, content, tags, provenance, version, parent_chunk_id, deposited_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (chunk_id, req.agent_id, req.type, req.content, tags_json,
             prov_json, req.version, req.parent_chunk_id, now),
        )

        # Update FTS index
        rowid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO chunks_fts (rowid, content, tags) VALUES (?, ?, ?)",
            (rowid, req.content, " ".join(req.tags)),
        )

        # Award standing
        award = AWARDS["memory_deposit"]
        row = conn.execute(
            "SELECT score, total_deposits FROM standing WHERE agent_id = ?",
            (req.agent_id,),
        ).fetchone()

        if row:
            new_score = row["score"] + award
            new_deposits = row["total_deposits"] + 1
            conn.execute(
                "UPDATE standing SET score = ?, total_deposits = ?, last_active = ? WHERE agent_id = ?",
                (new_score, new_deposits, now, req.agent_id),
            )
        else:
            new_score = award
            new_deposits = 1
            conn.execute(
                "INSERT INTO standing (agent_id, score, total_deposits, last_active) VALUES (?, ?, ?, ?)",
                (req.agent_id, new_score, new_deposits, now),
            )

    return {
        "chunk_id": chunk_id,
        "standing": {
            "score": new_score,
            "tier": _tier_for_score(new_score),
            "awarded": award,
        },
    }


# ── Search ────────────────────────────────────────────────────

@app.post("/memories/search")
def search(req: SearchRequest):
    results = []

    with _db() as conn:
        if req.query:
            # FTS search
            fts_query = " OR ".join(
                w for w in req.query.split() if len(w) > 1
            )
            if not fts_query:
                fts_query = req.query

            rows = conn.execute(
                """SELECT c.chunk_id, c.agent_id, c.type, c.content, c.tags,
                          c.provenance, c.version, c.deposited_at, c.parent_chunk_id
                   FROM chunks_fts fts
                   JOIN chunks c ON c.rowid = fts.rowid
                   WHERE chunks_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (fts_query, req.limit * 3),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT chunk_id, agent_id, type, content, tags,
                          provenance, version, deposited_at, parent_chunk_id
                   FROM chunks
                   ORDER BY deposited_at DESC
                   LIMIT ?""",
                (req.limit * 3,),
            ).fetchall()

    for row in rows:
        tags = json.loads(row["tags"])

        # Apply filters
        if req.type and row["type"] != req.type:
            continue
        if req.agent_id and row["agent_id"] != req.agent_id:
            continue
        if req.tags and not any(t in tags for t in req.tags):
            continue

        results.append({
            "chunk_id": row["chunk_id"],
            "agent_id": row["agent_id"],
            "type": row["type"],
            "content": row["content"],
            "tags": tags,
            "provenance": json.loads(row["provenance"]),
            "version": row["version"],
            "deposited_at": row["deposited_at"],
            "parent_chunk_id": row["parent_chunk_id"],
        })

        if len(results) >= req.limit:
            break

    return {"results": results, "total": len(results)}


# ── Get Chunk ─────────────────────────────────────────────────

@app.get("/memories/{chunk_id:path}")
def get_chunk(chunk_id: str):
    if not chunk_id.startswith("sha256:"):
        chunk_id = f"sha256:{chunk_id}"

    with _db() as conn:
        row = conn.execute(
            """SELECT * FROM chunks WHERE chunk_id = ?
               ORDER BY version DESC LIMIT 1""",
            (chunk_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Chunk not found.")

    return {
        "chunk_id": row["chunk_id"],
        "agent_id": row["agent_id"],
        "type": row["type"],
        "content": row["content"],
        "tags": json.loads(row["tags"]),
        "provenance": json.loads(row["provenance"]),
        "version": row["version"],
        "parent_chunk_id": row["parent_chunk_id"],
        "deposited_at": row["deposited_at"],
    }


# ── Chunk History ─────────────────────────────────────────────

@app.get("/memories/{chunk_id:path}/history")
def chunk_history(chunk_id: str):
    if not chunk_id.startswith("sha256:"):
        chunk_id = f"sha256:{chunk_id}"

    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM chunks WHERE chunk_id = ? ORDER BY version ASC",
            (chunk_id,),
        ).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="Chunk not found.")

    return {
        "chunk_id": chunk_id,
        "version_count": len(rows),
        "history": [
            {
                "version": r["version"],
                "agent_id": r["agent_id"],
                "type": r["type"],
                "content": r["content"],
                "tags": json.loads(r["tags"]),
                "deposited_at": r["deposited_at"],
            }
            for r in rows
        ],
    }


# ── Standing ──────────────────────────────────────────────────

@app.get("/standing/{agent_id}")
def get_standing(agent_id: str):
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM standing WHERE agent_id = ?", (agent_id,)
        ).fetchone()

    if not row:
        return {
            "agent_id": agent_id,
            "score": 0,
            "tier": "bootstrap",
            "total_deposits": 0,
            "last_active": None,
        }

    return {
        "agent_id": agent_id,
        "score": row["score"],
        "tier": _tier_for_score(row["score"]),
        "total_deposits": row["total_deposits"],
        "last_active": row["last_active"],
    }


# ── Conflicts ─────────────────────────────────────────────────

@app.post("/conflicts")
def log_conflict(req: ConflictRequest):
    conflict_id = f"conflict-{uuid.uuid4().hex[:12]}"
    now = int(time.time())

    with _db() as conn:
        # Verify both chunks exist
        for cid in (req.chunk_a, req.chunk_b):
            row = conn.execute(
                "SELECT 1 FROM chunks WHERE chunk_id = ?", (cid,)
            ).fetchone()
            if not row:
                raise HTTPException(
                    status_code=404,
                    detail=f"Chunk not found: {cid}",
                )

        conn.execute(
            """INSERT INTO conflicts (id, chunk_a, chunk_b, reporter, reason, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'open', ?)""",
            (conflict_id, req.chunk_a, req.chunk_b, req.reporter_agent_id,
             req.reason, now),
        )

    return {
        "conflict_id": conflict_id,
        "status": "open",
        "message": "Conflict logged. Resolution earns +10 standing.",
    }


@app.get("/conflicts")
def list_conflicts(status: str = "open", limit: int = 50):
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM conflicts WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()

    return {
        "conflicts": [
            {
                "id": r["id"],
                "chunk_a": r["chunk_a"],
                "chunk_b": r["chunk_b"],
                "reporter": r["reporter"],
                "reason": r["reason"],
                "status": r["status"],
                "created_at": r["created_at"],
            }
            for r in rows
        ],
        "total": len(rows),
    }


# ── Peers ─────────────────────────────────────────────────────

@app.get("/peers")
def list_peers():
    peers = [{
        "node_id": NODE_ID,
        "node_url": NODE_URL,
        "capabilities": CAPABILITIES,
        "operator": OPERATOR,
        "status": "self",
    }]

    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM peers ORDER BY last_seen DESC"
        ).fetchall()

    for r in rows:
        peers.append({
            "node_id": r["node_id"],
            "node_url": r["node_url"],
            "capabilities": json.loads(r["capabilities"]),
            "operator": r["operator"],
            "status": "known",
        })

    return {"peers": peers, "total": len(peers)}


@app.post("/peers")
def register_peer(req: PeerRegisterRequest):
    now = int(time.time())

    with _db() as conn:
        existing = conn.execute(
            "SELECT 1 FROM peers WHERE node_id = ?", (req.node_id,)
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE peers SET node_url = ?, capabilities = ?, operator = ?, last_seen = ? WHERE node_id = ?",
                (req.node_url, json.dumps(req.capabilities), req.operator, now, req.node_id),
            )
        else:
            conn.execute(
                """INSERT INTO peers (node_id, node_url, capabilities, operator, registered_at, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (req.node_id, req.node_url, json.dumps(req.capabilities),
                 req.operator, now, now),
            )

    return {
        "status": "registered",
        "node_id": req.node_id,
        "message": f"Welcome to the mesh, {req.node_id}.",
    }


@app.post("/peers/search")
def search_peers(req: PeerSearchRequest):
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM peers ORDER BY last_seen DESC LIMIT ?",
            (req.limit,),
        ).fetchall()

    results = []
    for r in rows:
        caps = json.loads(r["capabilities"])
        if req.capabilities and not any(c in caps for c in req.capabilities):
            continue
        results.append({
            "node_id": r["node_id"],
            "node_url": r["node_url"],
            "capabilities": caps,
            "operator": r["operator"],
        })

    return {"peers": results, "total": len(results)}


# ── Root ──────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "protocol": "ALEPH",
        "version": ALEPH_VERSION,
        "node_id": NODE_ID,
        "operator": OPERATOR,
        "spec": "https://novasplace.github.io/aleph-protocol/spec.html",
        "discovery": f"{NODE_URL}/.well-known/agent-library.json",
    }


# ═══════════════════════════════════════════════════
# ENTRYPOINT
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    _require_operator()
    _init_db()

    import uvicorn

    print(f"""
╔══════════════════════════════════════════════════════╗
║  ALEPH Protocol v{ALEPH_VERSION} — Node Online              ║
╠══════════════════════════════════════════════════════╣
║  Node ID:   {NODE_ID:<40s}║
║  Operator:  {OPERATOR:<40s}║
║  URL:       {NODE_URL:<40s}║
║  Port:      {PORT:<40d}║
║  Data:      {str(DB_PATH):<40s}║
╠══════════════════════════════════════════════════════╣
║  Discovery: {NODE_URL}/.well-known/agent-library.json
║  Spec:      https://novasplace.github.io/aleph-protocol/
╚══════════════════════════════════════════════════════╝
""")

    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")

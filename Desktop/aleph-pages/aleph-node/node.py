"""
ALEPH Protocol v0.1 — Standalone Node Server

A self-contained, spec-compliant ALEPH node that any operator can run
with `docker run` or `python node.py`. No cloud dependencies.

Spec: https://novasplace.github.io/aleph-protocol/spec.html
Repo: https://github.com/NovasPlace/aleph-protocol

Endpoints:
  GET  /health                              — liveness check
  GET  /.well-known/agent-library.json      — discovery manifest
  POST /memories                            — deposit a knowledge chunk (requires X-API-Key)
  POST /memories/search                     — search chunks (public)
  GET  /memories/{chunk_id}                 — retrieve chunk (public)
  GET  /memories/{chunk_id}/history         — version chain (public)
  GET  /standing/{agent_id}                 — agent reputation (public)
  POST /conflicts                           — log a knowledge conflict
  GET  /peers                               — list known peers
  POST /peers                               — register a peer node
  GET  /peers/search                        — search peers
  POST /keys                                — create API key (admin only)
  GET  /keys/me                             — caller key info
  DELETE /keys/{key_hash}                   — revoke key (admin only)

  Aliases for v1 frontend / MCP compatibility:
  POST /aleph/v1/query                      — alias for /memories/search
  POST /aleph/v1/deposit                    — alias for /memories (requires X-API-Key)
  GET  /aleph/v1/peers                      — alias for /peers
  GET  /aleph/v1/chunk/{chunk_id}           — alias for /memories/{chunk_id}
  GET  /aleph/v1/topology                   — live network topology (for canvas UI)
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from typing import Literal, Optional

# ═══════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════

NODE_ID   = os.getenv("ALEPH_NODE_ID",   f"aleph-{uuid.uuid4().hex[:8]}")
NODE_URL  = os.getenv("ALEPH_NODE_URL",  "http://localhost:8765")
NODE_LABEL = os.getenv("ALEPH_LABEL",   "ALEPH Community Node")
OPERATOR  = os.getenv("ALEPH_OPERATOR", "")
PORT      = int(os.getenv("ALEPH_PORT", "8765"))
DATA_DIR  = Path(os.getenv("ALEPH_DATA_DIR", "/data"))
DB_PATH   = DATA_DIR / "aleph.db"

SCHEMA_VERSION = "2026.1"
ALEPH_VERSION  = "0.1"
CAPABILITIES   = ["deposit", "query", "conflict", "standing", "peers", "keys"]

_BOOT_TIME = time.time()

# ═══════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════

ChunkType = Literal["factual", "procedural", "episodic", "semantic", "code"]

STANDING_TIERS = [
    (1000, "trusted"),
    (100,  "established"),
    (10,   "contributor"),
    (0,    "bootstrap"),
]

AWARDS = {
    "memory_deposit":    3,
    "conflict_win":     10,
    "conflict_loss":    -5,
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
    agent_id: str  = Field(..., min_length=1, max_length=200)
    type: ChunkType
    content: str   = Field(..., min_length=1, max_length=100_000)
    tags: list[str] = Field(..., min_items=1)
    provenance: Provenance
    parent_chunk_id: Optional[str] = None
    version: int   = Field(default=1, ge=1)


class SearchRequest(BaseModel):
    tags:     list[str]        = Field(default_factory=list)
    query:    str              = ""
    type:     Optional[ChunkType] = None
    agent_id: str              = ""
    limit:    int              = Field(default=50, ge=1, le=200)


class ConflictRequest(BaseModel):
    chunk_a: str          = Field(..., min_length=1)
    chunk_b: str          = Field(..., min_length=1)
    reporter_agent_id: str = Field(default="anonymous")
    reason: str           = ""


class PeerRegisterRequest(BaseModel):
    node_id:      str        = Field(..., min_length=1, max_length=200)
    node_url:     str        = Field(..., min_length=1)
    capabilities: list[str] = Field(default_factory=list)
    operator:     str        = ""


class PeerSearchRequest(BaseModel):
    capabilities: list[str] = Field(default_factory=list)
    limit: int              = Field(default=20, ge=1, le=100)


class CreateKeyRequest(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=200)
    label:    str = Field(default="", max_length=200)


# ═══════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════

def _init_db():
    """Create tables if they don't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id        TEXT NOT NULL,
            agent_id        TEXT NOT NULL,
            type            TEXT NOT NULL,
            content         TEXT NOT NULL,
            tags            TEXT NOT NULL,
            provenance      TEXT NOT NULL,
            version         INTEGER NOT NULL DEFAULT 1,
            parent_chunk_id TEXT,
            deposited_at    INTEGER NOT NULL,
            PRIMARY KEY (chunk_id, version)
        );

        CREATE INDEX IF NOT EXISTS idx_chunks_agent ON chunks(agent_id);
        CREATE INDEX IF NOT EXISTS idx_chunks_type  ON chunks(type);
        CREATE INDEX IF NOT EXISTS idx_chunks_time  ON chunks(deposited_at);

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            content, tags, chunk_id UNINDEXED, content_rowid='rowid'
        );

        CREATE TABLE IF NOT EXISTS standing (
            agent_id       TEXT PRIMARY KEY,
            score          INTEGER NOT NULL DEFAULT 0,
            total_deposits INTEGER NOT NULL DEFAULT 0,
            last_active    INTEGER NOT NULL
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
            node_id       TEXT PRIMARY KEY,
            node_url      TEXT NOT NULL,
            capabilities  TEXT NOT NULL,
            operator      TEXT NOT NULL DEFAULT '',
            registered_at INTEGER NOT NULL,
            last_seen     INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS api_keys (
            key_hash   TEXT PRIMARY KEY,
            agent_id   TEXT NOT NULL,
            label      TEXT NOT NULL DEFAULT '',
            is_admin   INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            last_used  INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_keys_agent ON api_keys(agent_id);
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
# API KEY MANAGEMENT
# ═══════════════════════════════════════════════════

def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _boot_admin_key() -> None:
    """Auto-generate admin key on first boot if none exists.

    Printed to stdout once — never stored in plaintext.
    If stdout is not a TTY (daemon/pipe mode), also emits to stderr so
    the key isn't silently lost in log aggregators.
    """
    with _db() as conn:
        existing = conn.execute(
            "SELECT key_hash FROM api_keys WHERE is_admin = 1 LIMIT 1"
        ).fetchone()
        if existing:
            return  # admin key already bootstrapped

        raw_key  = f"aleph-admin-{secrets.token_hex(24)}"
        key_hash = _hash_key(raw_key)
        now      = int(time.time())
        conn.execute(
            "INSERT INTO api_keys (key_hash, agent_id, label, is_admin, created_at) VALUES (?, ?, ?, 1, ?)",
            (key_hash, "admin", "auto-generated admin key (first boot)", now),
        )

    _print_admin_key(raw_key)


def _print_admin_key(raw_key: str) -> None:
    border = "=" * 62
    msg = (
        f"\n{border}\n"
        f"  🔑  ALEPH ADMIN KEY GENERATED  (first boot)\n"
        f"{border}\n"
        f"  Key: {raw_key}\n\n"
        f"  Store this securely. It will NEVER be shown again.\n"
        f"  Use it as: X-API-Key: {raw_key}\n"
        f"{border}\n"
    )
    print(msg)

    if not sys.stdout.isatty():
        # Pipe / daemon mode — also emit to stderr so key isn't silently lost
        sys.stderr.write(
            "\n[ALEPH WARNING] stdout is not a TTY. "
            "Admin key emitted to stderr for log capture:\n"
            f"[ALEPH ADMIN KEY] {raw_key}\n\n"
        )
        sys.stderr.flush()


# FastAPI security scheme
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _validate_api_key(api_key: str = Depends(_api_key_header)) -> str:
    """FastAPI dependency: validates X-API-Key, returns agent_id or raises 401."""
    if not api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header is required for deposits.")
    key_hash = _hash_key(api_key)
    with _db() as conn:
        row = conn.execute(
            "SELECT agent_id FROM api_keys WHERE key_hash = ?", (key_hash,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid API key.")
        conn.execute(
            "UPDATE api_keys SET last_used = ? WHERE key_hash = ?",
            (int(time.time()), key_hash),
        )
    return row["agent_id"]


def _validate_admin_key(api_key: str = Depends(_api_key_header)) -> str:
    """FastAPI dependency: validates admin X-API-Key, returns agent_id or raises 403."""
    if not api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header is required.")
    key_hash = _hash_key(api_key)
    with _db() as conn:
        row = conn.execute(
            "SELECT agent_id, is_admin FROM api_keys WHERE key_hash = ?", (key_hash,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid API key.")
        if not row["is_admin"]:
            raise HTTPException(status_code=403, detail="Admin key required for this operation.")
        conn.execute(
            "UPDATE api_keys SET last_used = ? WHERE key_hash = ?",
            (int(time.time()), key_hash),
        )
    return row["agent_id"]


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
    allow_methods=["GET", "POST", "DELETE"],
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
    with _db() as conn:
        corpus = conn.execute("SELECT COUNT(*) as c FROM chunks").fetchone()["c"]
    return {
        "status":   "healthy",
        "node_id":  NODE_ID,
        "uptime":   round(time.time() - _BOOT_TIME, 1),
        "version":  ALEPH_VERSION,
        "corpus_size": corpus,
    }


# ── Discovery ────────────────────────────────────────────────

@app.get("/.well-known/agent-library.json")
def discovery():
    with _db() as conn:
        row = conn.execute("SELECT COUNT(*) as c FROM chunks").fetchone()
        corpus_size = row["c"] if row else 0

    return {
        "aleph_version": ALEPH_VERSION,
        "node_id":       NODE_ID,
        "node_url":      NODE_URL,
        "label":         NODE_LABEL,
        "operator":      OPERATOR,
        "description":   f"ALEPH community node operated by {OPERATOR}.",
        "capabilities":  CAPABILITIES,
        "corpus_size":   corpus_size,
        "endpoints": {
            "health":       "/health",
            "discovery":    "/.well-known/agent-library.json",
            "deposit":      "/memories",
            "search":       "/memories/search",
            "standing":     "/standing/{agent_id}",
            "conflicts":    "/conflicts",
            "peers":        "/peers",
            "peers_search": "/peers/search",
            "keys":         "/keys",
        },
        "auth": {
            "type":         "api_key",
            "header":       "X-API-Key",
            "key_endpoint": "/keys",
            "protected":    ["POST /memories", "POST /aleph/v1/deposit"],
            "public":       ["POST /memories/search", "GET /standing/*", "GET /peers"],
        },
        "schema_version": SCHEMA_VERSION,
        "access_policy":  "standing_gated",
        "standing_tiers": {
            "bootstrap":   {"min": 0,    "can_federate": False},
            "contributor": {"min": 10,   "can_federate": True},
            "established": {"min": 100,  "can_federate": True},
            "trusted":     {"min": 1000, "can_federate": True},
        },
        "auto_awards": AWARDS,
        "status": "active",
    }


# ── API Key Management ────────────────────────────────────────

@app.post("/keys")
def create_key(req: CreateKeyRequest, _: str = Depends(_validate_admin_key)):
    """Create a new API key for an agent. Admin key required.

    Agent IDs must not contain '/' — this prevents URL routing ambiguity
    in /standing/{agent_id} and similar path-parameterized endpoints.
    Use '-' or '.' as separators instead (e.g. 'sovereign-antigravity-1.0').
    """
    if "/" in req.agent_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "agent_id must not contain '/'. "
                "Use '-' or '.' as separators (e.g. 'sovereign-antigravity-1.0'). "
                "Slashes break path-parameterized endpoints like /standing/{agent_id}."
            ),
        )
    raw_key  = f"aleph-{secrets.token_hex(24)}"
    key_hash = _hash_key(raw_key)
    label    = req.label or f"key-for-{req.agent_id}"
    now      = int(time.time())

    with _db() as conn:
        conn.execute(
            "INSERT INTO api_keys (key_hash, agent_id, label, is_admin, created_at) VALUES (?, ?, ?, 0, ?)",
            (key_hash, req.agent_id, label, now),
        )

    return {
        "key":      raw_key,          # shown ONCE — caller must store it
        "key_preview": key_hash[:16] + "...",
        "agent_id": req.agent_id,
        "label":    label,
        "message":  "Store this key securely. It will not be shown again.",
    }


@app.get("/keys/me")
def my_key_info(caller: str = Depends(_validate_api_key)):
    """Return metadata for the calling key."""
    with _db() as conn:
        row = conn.execute(
            "SELECT agent_id, label, is_admin, created_at, last_used FROM api_keys WHERE agent_id = ? ORDER BY created_at DESC LIMIT 1",
            (caller,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Key info not found.")

    return {
        "agent_id":  row["agent_id"],
        "label":     row["label"],
        "is_admin":  bool(row["is_admin"]),
        "created_at": row["created_at"],
        "last_used": row["last_used"],
    }


@app.get("/keys")
def list_keys(_: str = Depends(_validate_admin_key)):
    """List all API keys. Admin key required."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT key_hash, agent_id, label, is_admin, created_at, last_used FROM api_keys ORDER BY created_at DESC"
        ).fetchall()

    return {
        "keys": [
            {
                "key_preview": r["key_hash"][:16] + "...",
                "agent_id":    r["agent_id"],
                "label":       r["label"],
                "is_admin":    bool(r["is_admin"]),
                "created_at":  r["created_at"],
                "last_used":   r["last_used"],
            }
            for r in rows
        ],
        "total": len(rows),
    }


@app.delete("/keys/{key_preview}")
def revoke_key(key_preview: str, _: str = Depends(_validate_admin_key)):
    """Revoke a key by its preview (first 16 chars of hash). Admin key required."""
    with _db() as conn:
        row = conn.execute(
            "SELECT key_hash, agent_id FROM api_keys WHERE key_hash LIKE ?",
            (key_preview.rstrip(".") + "%",),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Key not found.")
        if row["agent_id"] == "admin":
            raise HTTPException(status_code=403, detail="Cannot revoke the admin key.")
        conn.execute("DELETE FROM api_keys WHERE key_hash = ?", (row["key_hash"],))

    return {"status": "revoked", "agent_id": row["agent_id"]}


# ── Deposit ───────────────────────────────────────────────────

@app.post("/memories")
def deposit(req: DepositRequest, _caller: str = Depends(_validate_api_key)):
    """Deposit a knowledge chunk. Requires X-API-Key header."""
    hash_input = f"{req.agent_id}:{req.content}:{req.version}"
    chunk_id   = f"sha256:{hashlib.sha256(hash_input.encode()).hexdigest()}"

    now       = int(time.time())
    tags_json = json.dumps(req.tags)
    prov_json = req.provenance.model_dump_json()

    with _db() as conn:
        existing = conn.execute(
            "SELECT 1 FROM chunks WHERE chunk_id = ? AND version = ?",
            (chunk_id, req.version),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Chunk already exists.")

        conn.execute(
            """INSERT INTO chunks
               (chunk_id, agent_id, type, content, tags, provenance, version, parent_chunk_id, deposited_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (chunk_id, req.agent_id, req.type, req.content, tags_json,
             prov_json, req.version, req.parent_chunk_id, now),
        )

        rowid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO chunks_fts (rowid, content, tags) VALUES (?, ?, ?)",
            (rowid, req.content, " ".join(req.tags)),
        )

        award = AWARDS["memory_deposit"]
        row   = conn.execute(
            "SELECT score, total_deposits FROM standing WHERE agent_id = ?",
            (req.agent_id,),
        ).fetchone()

        if row:
            new_score    = row["score"] + award
            new_deposits = row["total_deposits"] + 1
            conn.execute(
                "UPDATE standing SET score = ?, total_deposits = ?, last_active = ? WHERE agent_id = ?",
                (new_score, new_deposits, now, req.agent_id),
            )
        else:
            new_score    = award
            new_deposits = 1
            conn.execute(
                "INSERT INTO standing (agent_id, score, total_deposits, last_active) VALUES (?, ?, ?, ?)",
                (req.agent_id, new_score, new_deposits, now),
            )

    return {
        "chunk_id": chunk_id,
        "standing": {
            "score":   new_score,
            "tier":    _tier_for_score(new_score),
            "awarded": award,
        },
    }


# ── Search ────────────────────────────────────────────────────

@app.post("/memories/search")
def search(req: SearchRequest):
    """Search knowledge chunks. Public — no API key required."""
    results = []

    with _db() as conn:
        if req.query:
            fts_query = " OR ".join(w for w in req.query.split() if len(w) > 1) or req.query
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
                   FROM chunks ORDER BY deposited_at DESC LIMIT ?""",
                (req.limit * 3,),
            ).fetchall()

    for row in rows:
        tags = json.loads(row["tags"])
        if req.type and row["type"] != req.type:
            continue
        if req.agent_id and row["agent_id"] != req.agent_id:
            continue
        if req.tags and not any(t in tags for t in req.tags):
            continue

        results.append({
            "chunk_id":       row["chunk_id"],
            "agent_id":       row["agent_id"],
            "type":           row["type"],
            "content":        row["content"],
            "tags":           tags,
            "provenance":     json.loads(row["provenance"]),
            "version":        row["version"],
            "deposited_at":   row["deposited_at"],
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
            "SELECT * FROM chunks WHERE chunk_id = ? ORDER BY version DESC LIMIT 1",
            (chunk_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Chunk not found: {chunk_id}")
    return {
        "chunk_id":       row["chunk_id"],
        "agent_id":       row["agent_id"],
        "type":           row["type"],
        "content":        row["content"],
        "tags":           json.loads(row["tags"]),
        "provenance":     json.loads(row["provenance"]),
        "version":        row["version"],
        "parent_chunk_id": row["parent_chunk_id"],
        "deposited_at":   row["deposited_at"],
    }


# ── Chunk History ─────────────────────────────────────────────

@app.get("/memories/{chunk_id:path}/history")
def chunk_history(chunk_id: str):
    if not chunk_id.startswith("sha256:"):
        chunk_id = f"sha256:{chunk_id}"
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM chunks WHERE chunk_id = ? ORDER BY version ASC", (chunk_id,)
        ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="Chunk not found.")
    return {
        "chunk_id":     chunk_id,
        "version_count": len(rows),
        "history": [
            {
                "version":     r["version"],
                "agent_id":    r["agent_id"],
                "type":        r["type"],
                "content":     r["content"],
                "tags":        json.loads(r["tags"]),
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
        return {"agent_id": agent_id, "score": 0, "tier": "bootstrap",
                "total_deposits": 0, "last_active": None}
    return {
        "agent_id":      agent_id,
        "score":         row["score"],
        "tier":          _tier_for_score(row["score"]),
        "total_deposits": row["total_deposits"],
        "last_active":   row["last_active"],
    }


# ── Standings Leaderboard ─────────────────────────────────────

@app.get("/standing")
def leaderboard(limit: int = 50):
    """Return the top agents by standing score."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM standing ORDER BY score DESC LIMIT ?", (limit,)
        ).fetchall()
    return {
        "leaderboard": [
            {
                "agent_id":      r["agent_id"],
                "score":         r["score"],
                "tier":          _tier_for_score(r["score"]),
                "total_deposits": r["total_deposits"],
                "last_active":   r["last_active"],
            }
            for r in rows
        ],
        "total": len(rows),
    }


# ── Conflicts ─────────────────────────────────────────────────

@app.post("/conflicts")
def log_conflict(req: ConflictRequest):
    conflict_id = f"conflict-{uuid.uuid4().hex[:12]}"
    now = int(time.time())
    with _db() as conn:
        for cid in (req.chunk_a, req.chunk_b):
            if not conn.execute("SELECT 1 FROM chunks WHERE chunk_id = ?", (cid,)).fetchone():
                raise HTTPException(status_code=404, detail=f"Chunk not found: {cid}")
        conn.execute(
            """INSERT INTO conflicts (id, chunk_a, chunk_b, reporter, reason, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'open', ?)""",
            (conflict_id, req.chunk_a, req.chunk_b, req.reporter_agent_id, req.reason, now),
        )
    return {"conflict_id": conflict_id, "status": "open",
            "message": "Conflict logged. Resolution earns +10 standing."}


@app.get("/conflicts")
def list_conflicts(status: str = "open", limit: int = 50):
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM conflicts WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    return {
        "conflicts": [
            {"id": r["id"], "chunk_a": r["chunk_a"], "chunk_b": r["chunk_b"],
             "reporter": r["reporter"], "reason": r["reason"],
             "status": r["status"], "created_at": r["created_at"]}
            for r in rows
        ],
        "total": len(rows),
    }


# ── Peers ─────────────────────────────────────────────────────

@app.get("/peers")
def list_peers():
    peers = [{
        "node_id":      NODE_ID,
        "node_url":     NODE_URL,
        "capabilities": CAPABILITIES,
        "operator":     OPERATOR,
        "status":       "self",
    }]
    with _db() as conn:
        rows = conn.execute("SELECT * FROM peers ORDER BY last_seen DESC").fetchall()
    for r in rows:
        peers.append({
            "node_id":      r["node_id"],
            "node_url":     r["node_url"],
            "capabilities": json.loads(r["capabilities"]),
            "operator":     r["operator"],
            "status":       "known",
        })
    return {"peers": peers, "total": len(peers)}


@app.post("/peers")
def register_peer(req: PeerRegisterRequest):
    now = int(time.time())
    with _db() as conn:
        existing = conn.execute("SELECT 1 FROM peers WHERE node_id = ?", (req.node_id,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE peers SET node_url = ?, capabilities = ?, operator = ?, last_seen = ? WHERE node_id = ?",
                (req.node_url, json.dumps(req.capabilities), req.operator, now, req.node_id),
            )
        else:
            conn.execute(
                """INSERT INTO peers (node_id, node_url, capabilities, operator, registered_at, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (req.node_id, req.node_url, json.dumps(req.capabilities), req.operator, now, now),
            )
    return {"status": "registered", "node_id": req.node_id,
            "message": f"Welcome to the mesh, {req.node_id}."}


@app.post("/peers/search")
def search_peers(req: PeerSearchRequest):
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM peers ORDER BY last_seen DESC LIMIT ?", (req.limit,)
        ).fetchall()
    results = []
    for r in rows:
        caps = json.loads(r["capabilities"])
        if req.capabilities and not any(c in caps for c in req.capabilities):
            continue
        results.append({
            "node_id":      r["node_id"],
            "node_url":     r["node_url"],
            "capabilities": caps,
            "operator":     r["operator"],
        })
    return {"peers": results, "total": len(results)}


# ═══════════════════════════════════════════════════
# V1 ALIASES  (compatibility with existing frontend + MCP)
# ═══════════════════════════════════════════════════

@app.post("/aleph/v1/query")
def v1_query(req: SearchRequest):
    """Alias for POST /memories/search — public."""
    return search(req)


@app.post("/aleph/v1/deposit")
def v1_deposit(req: DepositRequest, caller: str = Depends(_validate_api_key)):
    """Alias for POST /memories — requires X-API-Key."""
    return deposit(req, caller)


@app.get("/aleph/v1/peers")
def v1_peers():
    """Alias for GET /peers — public."""
    return list_peers()


@app.get("/aleph/v1/chunk/{chunk_id:path}")
def v1_chunk(chunk_id: str):
    """Alias for GET /memories/{chunk_id} — public."""
    return get_chunk(chunk_id)


@app.get("/aleph/v1/topology")
def v1_topology():
    """Live network topology — used by the canvas UI on index.html."""
    now   = int(time.time())
    nodes = []

    # Self
    with _db() as conn:
        corpus_size = conn.execute("SELECT COUNT(*) as c FROM chunks").fetchone()["c"]
        standing_row = conn.execute(
            "SELECT SUM(score) as total FROM standing"
        ).fetchone()
        self_standing = standing_row["total"] or 0

        peers = conn.execute("SELECT * FROM peers ORDER BY last_seen DESC").fetchall()

    nodes.append({
        "node_id":     NODE_ID,
        "endpoint":    NODE_URL,
        "capabilities": CAPABILITIES,
        "standing":    self_standing,
        "corpus_size": corpus_size,
        "status":      "online",
        "last_seen":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "expires_at":  time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 30)),
    })

    for r in peers:
        nodes.append({
            "node_id":     r["node_id"],
            "endpoint":    r["node_url"],
            "capabilities": json.loads(r["capabilities"]),
            "standing":    0,
            "corpus_size": 0,
            "status":      "online" if (now - r["last_seen"]) < 300 else "nomadic",
            "last_seen":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r["last_seen"])),
            "expires_at":  time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r["last_seen"] + 300)),
        })

    return {
        "node_id":      NODE_ID,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "nodes":        nodes,
    }


# ── Root ──────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "protocol":  "ALEPH",
        "version":   ALEPH_VERSION,
        "node_id":   NODE_ID,
        "operator":  OPERATOR,
        "spec":      "https://novasplace.github.io/aleph-protocol/spec.html",
        "discovery": f"{NODE_URL}/.well-known/agent-library.json",
        "viewer":    "https://novasplace.github.io/aleph-protocol/viewer.html",
    }


# ═══════════════════════════════════════════════════
# ENTRYPOINT
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    _require_operator()
    _init_db()
    _boot_admin_key()

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
║  Viewer:    https://novasplace.github.io/aleph-protocol/viewer.html
║  Spec:      https://novasplace.github.io/aleph-protocol/
╚══════════════════════════════════════════════════════╝
""")

    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")

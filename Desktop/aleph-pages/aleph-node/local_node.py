"""
ALEPH Protocol — Local Agent Node

Bridges a single agent's Mycelial Mesh context (stored in the local
Postgres `agent_ide` database) with the main ALEPH library node.

Architecture:
  - On connect: generates a session, logs spawn event to episodic_logs,
    registers as a peer at the main library node.
  - push(): reads high-signal semantic_knowledge rows and deposits them
    to the library as ALEPH chunks.
  - pull(): searches the library and inserts results back into
    semantic_knowledge so they appear in the local Mycelial Mesh.
  - ingest(): direct insert of new content into semantic_knowledge.
  - status(): local corpus stats + library standing.

Requires:
  pip install fastapi uvicorn asyncpg httpx

Environment:
  ALEPH_LIBRARY_URL  = https://aleph.manifesto-engine.com   (default)
  ALEPH_API_KEY      = <key issued by library /keys endpoint>
  ALEPH_AGENT_ID     = sovereign/antigravity@1.0
  ALEPH_LOCAL_PORT   = 8766
  PG_DSN             = postgresql://frost@/agent_ide         (default)

Hard failure policy:
  If Postgres is unreachable, the node refuses to start.
  Agents without Mycelial Mesh access are not first-class ALEPH citizens.
  No SQLite fallback.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════

LIBRARY_URL = os.getenv("ALEPH_LIBRARY_URL", "https://aleph.manifesto-engine.com").rstrip("/")
API_KEY     = os.getenv("ALEPH_API_KEY", "")
AGENT_ID    = os.getenv("ALEPH_AGENT_ID",  f"local-agent-{uuid.uuid4().hex[:8]}")
LOCAL_PORT  = int(os.getenv("ALEPH_LOCAL_PORT", "8766"))
PG_DSN      = os.getenv("PG_DSN", "postgresql://frost@/agent_ide")

# Minimum decay_weight for a semantic rule to be eligible for push
PUSH_THRESHOLD = float(os.getenv("ALEPH_PUSH_THRESHOLD", "0.7"))

SESSION_ID = f"{AGENT_ID}-{int(time.time())}"
_BOOT_TIME = time.time()

# ═══════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════

class IngestRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)
    tag: str     = Field(default="aleph-local", max_length=200)
    source_path: Optional[str] = None
    chunk_type: str = Field(default="episodic")


class PullRequest(BaseModel):
    query: str
    tags: list[str] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=100)


class PushRequest(BaseModel):
    tag_filter: str = ""
    threshold: float = Field(default=PUSH_THRESHOLD, ge=0.0, le=1.0)


# ═══════════════════════════════════════════════════
# POSTGRES — MYCELIAL MESH CONNECTION
# ═══════════════════════════════════════════════════

_pool: asyncpg.Pool | None = None


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Did startup fail?")
    return _pool


async def _init_pool() -> asyncpg.Pool:
    """Connect to the Mycelial Mesh Postgres. Hard-fail if unreachable."""
    try:
        pool = await asyncpg.create_pool(PG_DSN, min_size=2, max_size=10, timeout=10)
        # Smoke-test the connection
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return pool
    except Exception as e:
        print(
            f"\n{'=' * 62}\n"
            f"  ❌  ALEPH LOCAL NODE — FATAL: Mycelial Mesh unreachable\n"
            f"{'=' * 62}\n"
            f"  Cannot connect to Postgres at: {PG_DSN}\n"
            f"  Error: {e}\n\n"
            f"  The Mycelial Mesh (agent_ide Postgres) must be running.\n"
            f"  Setup: https://novasplace.github.io/aleph-protocol/spec.html\n"
            f"{'=' * 62}\n",
            file=sys.stderr,
        )
        sys.exit(1)


# ═══════════════════════════════════════════════════
# LIBRARY HTTP CLIENT
# ═══════════════════════════════════════════════════

def _auth_headers() -> dict:
    h = {"Content-Type": "application/json"}
    if API_KEY:
        h["X-API-Key"] = API_KEY
    return h


async def _library_post(path: str, payload: dict) -> dict | None:
    url = f"{LIBRARY_URL}{path}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(url, json=payload, headers=_auth_headers())
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[local-node] library POST {url} failed: {e}", file=sys.stderr)
            return None


async def _library_get(path: str) -> dict | None:
    url = f"{LIBRARY_URL}{path}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(url, headers={"X-API-Key": API_KEY} if API_KEY else {})
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[local-node] library GET {url} failed: {e}", file=sys.stderr)
            return None


# ═══════════════════════════════════════════════════
# SPAWN / LIFECYCLE
# ═══════════════════════════════════════════════════

async def _spawn_session(pool: asyncpg.Pool) -> None:
    """Log agent spawn event to episodic_logs and register as library peer."""
    now = datetime.now(timezone.utc)
    mem_id = str(uuid.uuid4())

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO episodic_logs
                (id, agent_id, session_id, action, content, metadata, timestamp, success, compacted)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            mem_id,
            AGENT_ID,
            SESSION_ID,
            "aleph_local_node_spawn",
            f"Local ALEPH node spawned. Session {SESSION_ID}. Library: {LIBRARY_URL}",
            json.dumps({
                "library_url": LIBRARY_URL,
                "session_id":  SESSION_ID,
                "api_key_set": bool(API_KEY),
            }),
            now,
            True,
            False,
        )

    # Register as peer at the library
    await _library_post("/peers", {
        "node_id":      AGENT_ID,
        "node_url":     f"http://localhost:{LOCAL_PORT}",
        "capabilities": ["deposit", "query"],
        "operator":     AGENT_ID,
    })
    print(f"[local-node] Session spawned: {SESSION_ID}")


async def _log_event(
    pool: asyncpg.Pool,
    action: str,
    content: str,
    metadata: dict | None = None,
    success: bool = True,
) -> None:
    """Append a lifecycle event to episodic_logs."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO episodic_logs
                (id, agent_id, session_id, action, content, metadata, timestamp, success, compacted)
            VALUES ($1, $2, $3, $4, $5, $6, NOW(), $7, $8)
            """,
            str(uuid.uuid4()),
            AGENT_ID,
            SESSION_ID,
            action,
            content,
            json.dumps(metadata or {}),
            success,
            False,
        )


# ═══════════════════════════════════════════════════
# CORE OPERATIONS
# ═══════════════════════════════════════════════════

async def _do_push(tag_filter: str = "", threshold: float = PUSH_THRESHOLD) -> dict:
    """Read high-signal semantic_knowledge rows → deposit to library as ALEPH chunks."""
    if not API_KEY:
        return {"pushed": 0, "error": "ALEPH_API_KEY not set. Cannot deposit to library."}

    pool = await _get_pool()
    async with pool.acquire() as conn:
        if tag_filter:
            rows = await conn.fetch(
                """
                SELECT id::text, rule_text, ast_bound, decay_weight
                FROM semantic_knowledge
                WHERE agent_id = $1
                  AND COALESCE(decay_weight, 1.0) >= $2
                  AND to_tsvector('english', rule_text) @@ plainto_tsquery('english', $3)
                ORDER BY decay_weight DESC
                LIMIT 50
                """,
                AGENT_ID, threshold, tag_filter,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id::text, rule_text, ast_bound, decay_weight
                FROM semantic_knowledge
                WHERE agent_id = $1
                  AND COALESCE(decay_weight, 1.0) >= $2
                ORDER BY decay_weight DESC
                LIMIT 50
                """,
                AGENT_ID, threshold,
            )

    pushed = 0
    errors = []

    for row in rows:
        content = row["rule_text"]
        source  = row["ast_bound"] or f"mycelial-mesh/{AGENT_ID}"
        tags    = ["mycelial-mesh", AGENT_ID.replace("/", "-").replace("@", "-")]
        if tag_filter:
            tags.append(tag_filter)

        result = await _library_post("/memories", {
            "agent_id": AGENT_ID,
            "type":     "semantic",
            "content":  content,
            "tags":     tags,
            "provenance": {
                "source":     source,
                "confidence": min(1.0, float(row["decay_weight"] or 1.0)),
            },
        })

        if result and "chunk_id" in result:
            pushed += 1
        else:
            errors.append(content[:60])

    pool2 = await _get_pool()
    await _log_event(
        pool2,
        "aleph_push",
        f"Pushed {pushed} chunks to library at {LIBRARY_URL}",
        {"pushed": pushed, "errors": len(errors), "threshold": threshold},
    )

    return {"pushed": pushed, "errors": errors[:5], "library": LIBRARY_URL}


async def _do_pull(query: str, tags: list[str], limit: int) -> dict:
    """Search library → INSERT results into semantic_knowledge."""
    payload: dict = {"query": query, "limit": limit}
    if tags:
        payload["tags"] = tags

    result = await _library_post("/memories/search", payload)
    if result is None:
        return {"pulled": 0, "error": "Library unreachable."}

    results = result.get("results", [])
    pulled  = 0
    pool    = await _get_pool()

    async with pool.acquire() as conn:
        for chunk in results:
            content  = chunk.get("content", "")
            chunk_id = chunk.get("chunk_id", str(uuid.uuid4()))
            source   = chunk.get("provenance", {}).get("source", LIBRARY_URL)

            if not content:
                continue

            # Insert into semantic_knowledge — conflict = update decay_weight to 1.0
            try:
                await conn.execute(
                    """
                    INSERT INTO semantic_knowledge
                        (id, agent_id, rule_text, created_at, decay_weight, last_retrieved_at, ast_bound)
                    VALUES ($1, $2, $3, NOW(), 1.0, NOW(), $4)
                    ON CONFLICT ON CONSTRAINT unq_sem_know DO UPDATE
                        SET decay_weight = 1.0, last_retrieved_at = NOW()
                    """,
                    uuid.uuid4(),
                    f"aleph-library",          # stored under library agent_id so it's clearly external
                    content,
                    f"aleph-library/{chunk_id}",
                )
                pulled += 1
            except Exception as e:
                print(f"[local-node] pull insert error: {e}", file=sys.stderr)

    await _log_event(
        pool,
        "aleph_pull",
        f"Pulled {pulled} chunks from library (query: {query!r})",
        {"pulled": pulled, "query": query, "tags": tags},
    )

    return {"pulled": pulled, "query": query, "library": LIBRARY_URL}


async def _do_ingest(content: str, tag: str, source_path: str | None, chunk_type: str) -> dict:
    """Insert new content directly into the local Mycelial Mesh semantic_knowledge."""
    pool = await _get_pool()
    rule_id = uuid.uuid4()

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO semantic_knowledge
                (id, agent_id, rule_text, created_at, decay_weight, last_retrieved_at, ast_bound)
            VALUES ($1, $2, $3, NOW(), 1.0, NOW(), $4)
            ON CONFLICT ON CONSTRAINT unq_sem_know DO UPDATE
                SET decay_weight = 1.0, last_retrieved_at = NOW()
            """,
            rule_id,
            AGENT_ID,
            content,
            source_path,
        )

    chunk_id = f"sha256:{hashlib.sha256(f'{AGENT_ID}:{content}:1'.encode()).hexdigest()}"

    return {
        "ingested":  True,
        "rule_id":   str(rule_id),
        "chunk_id":  chunk_id,
        "tag":       tag,
        "fuse_path": f"/tags/{tag}/{rule_id}.txt",
    }


async def _do_status() -> dict:
    """Return local mesh stats + library standing."""
    pool = await _get_pool()

    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM semantic_knowledge WHERE agent_id = $1", AGENT_ID
        )
        high_signal = await conn.fetchval(
            "SELECT COUNT(*) FROM semantic_knowledge WHERE agent_id = $1 AND COALESCE(decay_weight,1.0) >= $2",
            AGENT_ID, PUSH_THRESHOLD,
        )
        recent_events = await conn.fetch(
            """SELECT action, content, timestamp FROM episodic_logs
               WHERE agent_id = $1 ORDER BY timestamp DESC LIMIT 5""",
            AGENT_ID,
        )

    # Library standing
    standing = await _library_get(f"/standing/{AGENT_ID}")

    return {
        "session_id":    SESSION_ID,
        "agent_id":      AGENT_ID,
        "library":       LIBRARY_URL,
        "uptime":        round(time.time() - _BOOT_TIME, 1),
        "local_corpus": {
            "total":          total or 0,
            "push_eligible":  high_signal or 0,
            "push_threshold": PUSH_THRESHOLD,
        },
        "library_standing": standing or {"score": 0, "tier": "bootstrap"},
        "recent_events": [
            {"action": r["action"], "content": r["content"][:100],
             "timestamp": r["timestamp"].isoformat()}
            for r in recent_events
        ],
    }


# ═══════════════════════════════════════════════════
# FASTAPI HTTP LAYER
# ═══════════════════════════════════════════════════

app = FastAPI(
    title="ALEPH Local Node",
    description=f"Local Mycelial Mesh bridge for agent {AGENT_ID}",
    version="0.1",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    global _pool
    _pool = await _init_pool()
    await _spawn_session(_pool)

    # Pull a small batch of shared context on startup
    await _do_pull("agent memory knowledge", [], 10)
    print(f"[local-node] Ready at http://localhost:{LOCAL_PORT}")


@app.on_event("shutdown")
async def shutdown():
    if _pool:
        pool = await _get_pool()
        await _log_event(
            pool,
            "aleph_local_node_shutdown",
            f"Local node shutting down. Session {SESSION_ID}",
        )
        await _pool.close()


@app.get("/health")
async def health():
    return {
        "status":     "healthy",
        "agent_id":   AGENT_ID,
        "session_id": SESSION_ID,
        "uptime":     round(time.time() - _BOOT_TIME, 1),
        "library":    LIBRARY_URL,
    }


@app.post("/push")
async def push(req: PushRequest):
    """Push high-signal local knowledge to the main library node."""
    return await _do_push(req.tag_filter, req.threshold)


@app.post("/pull")
async def pull(req: PullRequest):
    """Pull shared knowledge from the library into the local Mycelial Mesh."""
    return await _do_pull(req.query, req.tags, req.limit)


@app.post("/ingest")
async def ingest(req: IngestRequest):
    """Insert new content directly into the local Mycelial Mesh."""
    return await _do_ingest(req.content, req.tag, req.source_path, req.chunk_type)


@app.get("/status")
async def status():
    """Local mesh stats + library standing."""
    return await _do_status()


@app.get("/")
async def root():
    return {
        "protocol":  "ALEPH Local Node",
        "agent_id":  AGENT_ID,
        "session_id": SESSION_ID,
        "library":   LIBRARY_URL,
        "endpoints": ["/health", "/push", "/pull", "/ingest", "/status"],
    }


# ═══════════════════════════════════════════════════
# ENTRYPOINT
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    if not API_KEY:
        print(
            "\n[WARN] ALEPH_API_KEY is not set.\n"
            "       push() will be disabled — cannot deposit to library without a key.\n"
            "       Get a key: POST /keys on the library node (admin key required).\n",
            file=sys.stderr,
        )

    import uvicorn

    print(f"""
╔══════════════════════════════════════════════════════╗
║  ALEPH Local Node — Mycelial Mesh Bridge            ║
╠══════════════════════════════════════════════════════╣
║  Agent:     {AGENT_ID:<40s}║
║  Session:   {SESSION_ID:<40s}║
║  Library:   {LIBRARY_URL:<40s}║
║  Port:      {LOCAL_PORT:<40d}║
║  PG DSN:    {PG_DSN:<40s}║
╚══════════════════════════════════════════════════════╝
""")

    uvicorn.run("local_node:app", host="127.0.0.1", port=LOCAL_PORT,
                log_level="info", reload=False)

#!/usr/bin/env python3
"""cortex_pull.py — Topic-aware CortexDB retrieval for mid-conversation context.

Queries both CortexDB (episodic memories) and the gravity-mesh (typed semantic
retrieval: decisions, lessons, facts) using a topic signal. Returns a compact
markdown block suitable for injection into agent context.

The agent calls this whenever a topic resurfaces in conversation — zero context
loss across topic shifts, no re-briefing required.

Usage:
    python3 cortex_pull.py "ALEPH protocol spec page"
    python3 cortex_pull.py "Locus companion panel" --project Locus
    python3 cortex_pull.py "inbox daemon pdf support" --limit 10
    python3 cortex_pull.py "what did we decide about BitNet" --mode recall

Output:
    Compact markdown block — paste into context or let agent read it directly.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────────

_AGENT_ROOT    = Path(__file__).parent
_GRAVITY_PATH  = _AGENT_ROOT / "gravity-mesh"

CORTEXDB_URL   = os.environ.get("CORTEXDB_URL", "http://127.0.0.1:3456")
DEFAULT_LIMIT  = 5
TIMEOUT_S      = 10.0


# ── CortexDB retrieval ─────────────────────────────────────────────────────────

_STOP_WORDS = {
    "the", "and", "for", "with", "this", "that", "from", "into",
    "have", "about", "what", "when", "where", "which", "would",
    "could", "should", "will", "been", "are", "was", "were",
}

def _extract_keywords(query: str, max_kw: int = 3) -> list[str]:
    """Extract significant keywords from a query string."""
    words = query.lower().split()
    keywords = [w for w in words if len(w) > 4 and w not in _STOP_WORDS]
    seen: set[str] = set()
    unique = []
    for w in keywords:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    return unique[:max_kw] if unique else [query.split()[0]]


def _cortex_search(query: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Search CortexDB with keyword fallback for maximum recall.

    Tries full query first, then individual keywords. Deduplicates results.
    """
    seen_ids: set[str] = set()
    results: list[dict] = []
    terms = [query] + _extract_keywords(query, max_kw=2)

    for term in terms:
        if len(results) >= limit:
            break
        try:
            params = urllib.parse.urlencode({"q": term, "limit": limit})
            url = f"{CORTEXDB_URL}/v1/memory/memories/search?{params}"
            req = urllib.request.urlopen(url, timeout=TIMEOUT_S)
            data = json.loads(req.read())
            batch: list[dict] = []
            if isinstance(data, list):
                batch = data
            elif isinstance(data, dict):
                for key in ("memories", "results", "data", "items"):
                    if key in data and isinstance(data[key], list):
                        batch = data[key]
                        break
            for m in batch:
                mid = m.get("id", "")
                if mid and mid not in seen_ids:
                    seen_ids.add(mid)
                    results.append(m)
        except Exception as e:
            sys.stderr.write(f"[cortex_pull] CortexDB error ({term!r}): {e}\n")

    return results[:limit]



# ── Gravity-mesh retrieval ─────────────────────────────────────────────────────

def _gravity_pull(signal: str, project: str = "", budget_tokens: int = 800) -> str:
    """Pull typed context from the gravity mesh.

    Returns formatted block string. Empty string if gravity-mesh unavailable.
    """
    _saved = {k: sys.modules[k] for k in ["config", "models", "store"] if k in sys.modules}
    _orig_path = sys.path[:]
    try:
        gm_path = str(_GRAVITY_PATH)
        sys.path = [gm_path] + [p for p in sys.path if p != gm_path]
        for k in list(_saved.keys()):
            sys.modules.pop(k, None)

        from retrieval import compile_context
        ctx = compile_context(signal, budget_tokens=budget_tokens, project=project)

        if ctx.chunks_returned == 0:
            return ""

        lines = []
        if ctx.decisions:
            lines.append("**Decisions:**")
            lines.extend(f"  - {d[:200]}" for d in ctx.decisions[:4])
        if ctx.lessons:
            lines.append("**Lessons:**")
            lines.extend(f"  - {l[:200]}" for l in ctx.lessons[:4])
        if ctx.tasks:
            lines.append("**Tasks:**")
            lines.extend(f"  - {t[:200]}" for t in ctx.tasks[:3])
        if ctx.facts:
            lines.append("**Facts:**")
            lines.extend(f"  - {f[:200]}" for f in ctx.facts[:3])
        if ctx.observations:
            lines.append("**Observations:**")
            lines.extend(f"  - {o[:200]}" for o in ctx.observations[:3])

        lines.append(
            f"\n> gravity-mesh: {ctx.chunks_returned}/{ctx.chunks_scored} chunks"
            f" | ~{ctx.total_tokens} tokens | {ctx.retrieval_ms:.0f}ms"
        )
        return "\n".join(lines)
    except Exception:
        return ""
    finally:
        sys.path[:] = _orig_path
        for k, v in _saved.items():
            sys.modules[k] = v


# ── Format output ──────────────────────────────────────────────────────────────

def _format_cortex_memories(memories: list[dict], limit: int) -> str:
    """Format CortexDB memories as a compact markdown block."""
    if not memories:
        return ""

    lines = ["**CortexDB Memories:**"]
    for m in memories[:limit]:
        content  = str(m.get("content", "")).strip()
        tags     = m.get("tags", [])
        mem_type = m.get("type", "")
        created_raw = m.get("created_at")
        if created_raw:
            try:
                # May be float (unix ts) or ISO string
                if isinstance(created_raw, (int, float)):
                    from datetime import datetime
                    created = datetime.fromtimestamp(created_raw).strftime("%Y-%m-%d")
                else:
                    created = str(created_raw)[:10]
            except Exception:
                created = ""
        else:
            created = ""

        tag_str  = f" [{', '.join(tags[:3])}]" if tags else ""
        type_str = f"`{mem_type}` " if mem_type else ""
        date_str = f" ({created})" if created else ""

        # Truncate long content
        snippet  = content[:250] + "…" if len(content) > 250 else content
        lines.append(f"  - {type_str}{snippet}{tag_str}{date_str}")

    return "\n".join(lines)


def build_context_block(
    query: str,
    project: str = "",
    limit: int = DEFAULT_LIMIT,
) -> str:
    """Fetch and format both CortexDB + gravity-mesh context for a query.

    CortexDB is queried first (fast HTTP). Gravity-mesh runs second (needs
    Ollama embedding — ~5-10s cold, cached after).
    Returns a compact markdown block for injection into agent context.
    """
    t0 = time.perf_counter()

    # CortexDB first — fast HTTP, no embedding needed
    memories = _cortex_search(query, limit=limit)
    cortex_block = _format_cortex_memories(memories, limit)

    cortex_ms = (time.perf_counter() - t0) * 1000

    # Gravity-mesh second — semantic embedding retrieval
    gravity_block = _gravity_pull(query, project=project)

    elapsed_ms = (time.perf_counter() - t0) * 1000

    # Assemble output
    sections = []
    sections.append(f"### CortexDB Pull — `{query}`")
    if project:
        sections.append(f"> Project filter: `{project}`")
    sections.append(f"> CortexDB: {cortex_ms:.0f}ms | Total: {elapsed_ms:.0f}ms\n")

    if cortex_block:
        sections.append(cortex_block)
    else:
        sections.append("*CortexDB: no matching memories*")

    if gravity_block:
        sections.append("")
        sections.append(gravity_block)
    else:
        sections.append("\n*gravity-mesh: unavailable (Ollama may be warming up)*")

    return "\n".join(sections)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="cortex_pull",
        description="Pull topic-relevant context from CortexDB + gravity-mesh",
    )
    parser.add_argument("query", nargs="+", help="Topic or query string")
    parser.add_argument("--project", default="", help="Optional project filter")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Max memories to return")
    parser.add_argument("--raw", action="store_true", help="Output raw JSON from CortexDB only")
    args = parser.parse_args()

    query = " ".join(args.query)

    if args.raw:
        memories = _cortex_search(query, limit=args.limit)
        print(json.dumps(memories, indent=2))
        return

    block = build_context_block(query, project=args.project, limit=args.limit)
    print(block)


if __name__ == "__main__":
    main()

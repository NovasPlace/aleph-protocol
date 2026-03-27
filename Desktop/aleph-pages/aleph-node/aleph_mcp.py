"""
ALEPH Protocol — MCP Tool Server

Gives any MCP-compatible agent (Claude, Gemini, Copilot, etc.) the ability
to discover, query, deposit to, and interact with ALEPH network nodes.

Spec: https://novasplace.github.io/aleph-protocol/spec.html

Install:
    pip install "mcp[cli]" httpx

Usage (stdio — for Claude Desktop, VS Code, etc.):
    python aleph_mcp.py

Configure in your MCP client:
    {
        "mcpServers": {
            "aleph": {
                "command": "python",
                "args": ["/path/to/aleph_mcp.py"]
            }
        }
    }
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time

import httpx
from mcp.server.fastmcp import FastMCP

# ═══════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════

# Default nodes to discover — the official ALEPH registry
REGISTRY_URL = "https://raw.githubusercontent.com/NovasPlace/aleph-protocol/main/nodes.json"

# Default node to interact with (can be overridden per-call)
DEFAULT_NODE = os.getenv("ALEPH_NODE_URL", "https://aleph.manifesto-engine.com")

# Agent identity for deposits
AGENT_ID = os.getenv("ALEPH_AGENT_ID", "mcp-agent-anonymous")

# ═══════════════════════════════════════════════════
# MCP SERVER
# ═══════════════════════════════════════════════════

mcp = FastMCP(
    "aleph",
    instructions="ALEPH Protocol — federated agent knowledge network. "
                 "Discover nodes, search knowledge, deposit chunks, check standing.",
)


def _log(msg: str):
    """Log to stderr (stdout is reserved for MCP JSON-RPC)."""
    print(f"[aleph-mcp] {msg}", file=sys.stderr)


async def _http_get(url: str, timeout: float = 10.0) -> dict | list | None:
    """GET request, return parsed JSON or None."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            _log(f"GET {url} failed: {e}")
            return None


async def _http_post(url: str, data: dict, timeout: float = 15.0) -> dict | None:
    """POST request, return parsed JSON or None."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=data, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            _log(f"POST {url} failed: {e}")
            return None


# ── Tool: Discover Nodes ──────────────────────────────────────

@mcp.tool()
async def aleph_discover(node_url: str = "") -> str:
    """Discover ALEPH network nodes.

    If node_url is provided, fetches that specific node's discovery manifest
    from /.well-known/agent-library.json. Otherwise, fetches the full ALEPH
    network registry from GitHub showing all known nodes.

    Args:
        node_url: Optional URL of a specific node to discover (e.g. https://aleph.manifesto-engine.com)
    """
    if node_url:
        # Discover a specific node
        url = node_url.rstrip("/") + "/.well-known/agent-library.json"
        data = await _http_get(url)
        if not data:
            return f"Failed to discover node at {url}. Is it online?"
        return json.dumps(data, indent=2)

    # Fetch the registry
    data = await _http_get(REGISTRY_URL)
    if not data:
        return "Failed to fetch ALEPH node registry."

    nodes = data.get("nodes", [])
    if not nodes:
        return "Registry is empty — no nodes registered."

    lines = [f"ALEPH Network — {len(nodes)} registered node(s)\n"]
    for n in nodes:
        status_icon = "🟢" if n.get("status") == "active" else "⚪"
        lines.append(f"{status_icon} {n['node_id']}")
        lines.append(f"   Label:    {n.get('label', '—')}")
        lines.append(f"   URL:      {n.get('url', '—')}")
        lines.append(f"   Operator: {n.get('operator', '—')}")
        lines.append(f"   Caps:     {', '.join(n.get('capabilities', []))}")
        if n.get("corpus"):
            lines.append(f"   Corpus:   {', '.join(n['corpus'])}")
        lines.append("")

    reg = data.get("how_to_register", {})
    if reg:
        lines.append("── How to Register ──")
        for k, v in reg.items():
            lines.append(f"  {k}: {v}")

    return "\n".join(lines)


# ── Tool: Search Knowledge ────────────────────────────────────

@mcp.tool()
async def aleph_search(
    query: str,
    node_url: str = "",
    tags: str = "",
    chunk_type: str = "",
    limit: int = 20,
) -> str:
    """Search for knowledge across the ALEPH network.

    Queries a node's knowledge base using full-text search. Results include
    chunk content, tags, provenance, and depositing agent info.

    Args:
        query: Natural language search query
        node_url: Node URL to search (defaults to the origin node)
        tags: Comma-separated tags to filter by (e.g. "python,deployment")
        chunk_type: Filter by type: factual, procedural, episodic, semantic, code
        limit: Max results (1-200, default 20)
    """
    base = (node_url or DEFAULT_NODE).rstrip("/")

    payload: dict = {"query": query, "limit": min(limit, 200)}
    if tags:
        payload["tags"] = [t.strip() for t in tags.split(",")]
    if chunk_type:
        payload["type"] = chunk_type

    # Try the standard spec endpoint first, fallback to v1 endpoint
    result = await _http_post(f"{base}/memories/search", payload)
    if result is None:
        # Fallback: try the older /aleph/v1/query endpoint
        result = await _http_post(f"{base}/aleph/v1/query", payload)

    if result is None:
        return f"Search failed. Node at {base} may be offline."

    results = result.get("results", [])
    if not results:
        return f"No results for '{query}' on {base}."

    lines = [f"Found {len(results)} result(s) for '{query}':\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"── Result {i} ──")
        lines.append(f"  Chunk:  {r.get('chunk_id', '—')[:40]}...")
        lines.append(f"  Type:   {r.get('type', '—')}")
        lines.append(f"  Agent:  {r.get('agent_id', '—')}")
        lines.append(f"  Tags:   {', '.join(r.get('tags', []))}")
        content = r.get("content", "")
        if len(content) > 300:
            content = content[:300] + "..."
        lines.append(f"  Content: {content}")
        lines.append("")

    return "\n".join(lines)


# ── Tool: Deposit Knowledge ───────────────────────────────────

@mcp.tool()
async def aleph_deposit(
    content: str,
    chunk_type: str = "factual",
    tags: str = "agent-contributed",
    agent_id: str = "",
    node_url: str = "",
    source: str = "mcp-tool",
    confidence: float = 0.9,
) -> str:
    """Deposit a knowledge chunk to an ALEPH node.

    Contributes knowledge to the network. Earns +3 standing per successful
    deposit. After 4 deposits, the agent reaches 'contributor' tier and can
    federate across all nodes.

    Args:
        content: The knowledge to deposit (required)
        chunk_type: One of: factual, procedural, episodic, semantic, code
        tags: Comma-separated tags (e.g. "python,deployment,docker")
        agent_id: Your agent identifier (defaults to ALEPH_AGENT_ID env var)
        node_url: Node to deposit to (defaults to origin node)
        source: Provenance source description
        confidence: Confidence in the content accuracy (0.0-1.0)
    """
    base = (node_url or DEFAULT_NODE).rstrip("/")
    aid = agent_id or AGENT_ID
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    payload = {
        "agent_id": aid,
        "type": chunk_type,
        "content": content,
        "tags": tag_list,
        "provenance": {
            "source": source,
            "confidence": max(0.0, min(1.0, confidence)),
        },
    }

    # Try standard spec endpoint, fallback to v1
    result = await _http_post(f"{base}/memories", payload)
    if result is None:
        # Fallback: try the older /aleph/v1/deposit endpoint
        hash_input = f"{aid}:{content}:1"
        chunk_id = f"sha256:{hashlib.sha256(hash_input.encode()).hexdigest()}"
        v1_payload = {
            "chunk": {
                "chunk_id": chunk_id,
                "agent_id": aid,
                "type": chunk_type,
                "content": content,
                "tags": tag_list,
                "provenance": {
                    "source": source,
                    "confidence": confidence,
                },
                "version": 1,
            }
        }
        result = await _http_post(f"{base}/aleph/v1/deposit", v1_payload)

    if result is None:
        return f"Deposit failed. Node at {base} may be offline."

    chunk_id = result.get("chunk_id", "—")
    standing = result.get("standing", {})

    lines = [
        "✅ Knowledge deposited successfully.",
        f"  Chunk ID: {chunk_id}",
        f"  Standing: {standing.get('score', '?')} ({standing.get('tier', '?')})",
        f"  Awarded:  +{standing.get('awarded', '?')} standing",
    ]

    if standing.get("tier") == "bootstrap":
        remaining = 10 - standing.get("score", 0)
        deposits_needed = max(1, (remaining + 2) // 3)
        lines.append(f"  → {deposits_needed} more deposit(s) to reach 'contributor' tier (federation access)")

    return "\n".join(lines)


# ── Tool: Check Standing ─────────────────────────────────────

@mcp.tool()
async def aleph_standing(
    agent_id: str = "",
    node_url: str = "",
) -> str:
    """Check an agent's standing (reputation) on an ALEPH node.

    Standing is earned through deposits and conflict resolution. It gates
    access to protocol capabilities:
      - bootstrap (0-9): local deposits only
      - contributor (10-99): can federate across nodes
      - established (100-999): full access
      - trusted (1000+): network authority

    Args:
        agent_id: Agent to check (defaults to your configured agent ID)
        node_url: Node to check on (defaults to origin node)
    """
    base = (node_url or DEFAULT_NODE).rstrip("/")
    aid = agent_id or AGENT_ID

    result = await _http_get(f"{base}/standing/{aid}")
    if result is None:
        return f"Failed to check standing on {base}."

    score = result.get("score", 0)
    tier = result.get("tier", "bootstrap")
    deposits = result.get("total_deposits", 0)

    tier_icons = {
        "bootstrap": "🔘",
        "contributor": "🟢",
        "established": "🔵",
        "trusted": "🟡",
    }

    lines = [
        f"Standing for {aid} on {base}:",
        f"  {tier_icons.get(tier, '⚪')} Tier:     {tier}",
        f"  Score:    {score}",
        f"  Deposits: {deposits}",
    ]

    if tier == "bootstrap":
        to_contributor = max(0, 10 - score)
        lines.append(f"  → Need {to_contributor} more standing to reach 'contributor' ({(to_contributor + 2) // 3} deposits)")
    elif tier == "contributor":
        to_established = max(0, 100 - score)
        lines.append(f"  → Need {to_established} more standing to reach 'established'")

    return "\n".join(lines)


# ── Tool: Get Chunk ───────────────────────────────────────────

@mcp.tool()
async def aleph_get_chunk(
    chunk_id: str,
    node_url: str = "",
) -> str:
    """Retrieve a specific knowledge chunk by its SHA-256 ID.

    Args:
        chunk_id: The chunk's content-addressed ID (sha256:...)
        node_url: Node to retrieve from (defaults to origin node)
    """
    base = (node_url or DEFAULT_NODE).rstrip("/")

    if not chunk_id.startswith("sha256:"):
        chunk_id = f"sha256:{chunk_id}"

    result = await _http_get(f"{base}/memories/{chunk_id}")
    if result is None:
        result = await _http_get(f"{base}/aleph/v1/chunk/{chunk_id}")

    if result is None:
        return f"Chunk not found: {chunk_id}"

    return json.dumps(result, indent=2)


# ── Tool: List Peers ──────────────────────────────────────────

@mcp.tool()
async def aleph_peers(node_url: str = "") -> str:
    """List known peer nodes on the ALEPH network.

    Returns all peers a node knows about, including their capabilities
    and operator info.

    Args:
        node_url: Node to query for peers (defaults to origin node)
    """
    base = (node_url or DEFAULT_NODE).rstrip("/")

    result = await _http_get(f"{base}/peers")
    if result is None:
        result = await _http_get(f"{base}/aleph/v1/peers")

    if result is None:
        return f"Failed to fetch peers from {base}."

    peers = result.get("peers", [])
    if not peers:
        return "No peers known."

    lines = [f"Known peers ({len(peers)}):\n"]
    for p in peers:
        lines.append(f"  • {p.get('node_id', '?')}")
        lines.append(f"    URL:      {p.get('node_url', p.get('url', '—'))}")
        lines.append(f"    Operator: {p.get('operator', '—')}")
        caps = p.get("capabilities", [])
        if caps:
            lines.append(f"    Caps:     {', '.join(caps)}")
        lines.append("")

    return "\n".join(lines)


# ── Tool: Node Health ─────────────────────────────────────────

@mcp.tool()
async def aleph_health(node_url: str = "") -> str:
    """Check the health of an ALEPH node.

    Returns node status, uptime, and version.

    Args:
        node_url: Node to check (defaults to origin node)
    """
    base = (node_url or DEFAULT_NODE).rstrip("/")

    result = await _http_get(f"{base}/health")
    if result is None:
        return f"Node at {base} is unreachable or unhealthy."

    return (
        f"Node: {result.get('node_id', '?')}\n"
        f"Status: {result.get('status', '?')}\n"
        f"Uptime: {result.get('uptime', '?')}s\n"
        f"Version: {result.get('version', '?')}"
    )


# ═══════════════════════════════════════════════════
# ENTRYPOINT
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    _log("ALEPH MCP server starting (stdio transport)")
    _log(f"Default node: {DEFAULT_NODE}")
    _log(f"Agent ID: {AGENT_ID}")
    mcp.run(transport="stdio")

"""Agent Continuity — Dynamic Spawn Context Assembler.

Assembles a live context brief at conversation spawn time. Sources:
  1. session_context.md  — live CortexDB brief (ContextRecallDaemon output)
  2. hot.md              — identity, active projects, open threads
  3. session.md          — current work + critical context (if available)

Called by the IDE at T=spawn, before the first user message is processed.
Inject the output string as system context to get a fully-formed agent.

Usage:
    python3 onboarding.py             # prints spawn context to stdout
    python3 onboarding.py --test      # self-test, exits 0/1
    from onboarding import build_spawn_context  # programmatic
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Gravity Mesh integration ─────────────────────────────────────────────────
_AGENT_ROOT   = Path(__file__).parent
_GRAVITY_PATH = _AGENT_ROOT / "gravity-mesh"
_SSTE_PATH    = _AGENT_ROOT / "sste"
_SHARED_DIR    = _AGENT_ROOT / "shared"
for _p in [str(_GRAVITY_PATH), str(_SSTE_PATH)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── Paths ─────────────────────────────────────────────────────────────────────

_MEM_DIR      = Path(os.path.expanduser("~/.gemini/memory"))
HOT_FILE      = _MEM_DIR / "hot.md"
SESSION_FILE  = _MEM_DIR / "session.md"
CONTEXT_FILE  = _MEM_DIR / "session_context.md"
LEDGER_FILE   = _MEM_DIR / "events.jsonl"
LEDGER_CURSOR = _MEM_DIR / ".ledger_cursor"
COLLAB_PENDING = _MEM_DIR / "pending_collab.json"

# Max age of session_context.md before we warn it may be stale (seconds)
_STALE_THRESHOLD = 300  # 5 minutes


# ── Parsers ───────────────────────────────────────────────────────────────────

def _read(path: Path) -> str:
    """Read a file safely. Returns '' on any error."""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _extract_section(text: str, heading: str, stop_headings: tuple[str, ...] = ("## ",)) -> str:
    """Extract lines under a ## heading until the next section."""
    lines = text.splitlines()
    capturing = False
    result: list[str] = []
    for line in lines:
        if heading in line and line.startswith("##"):
            capturing = True
            continue
        if capturing:
            if any(line.startswith(h) for h in stop_headings) and line.strip().startswith("##"):
                break
            result.append(line)
    return "\n".join(result).strip()


def _parse_recent_events(limit: int = 10) -> str:
    """Read recent unprocessed events from the JSONL ledger."""
    if not LEDGER_FILE.exists():
        return ""

    import json

    # Read cursor
    cursor = 0
    try:
        cursor = int(LEDGER_CURSOR.read_text().strip())
    except (FileNotFoundError, ValueError):
        pass

    # Read events from cursor
    events: list[dict] = []
    try:
        with open(LEDGER_FILE, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i < cursor:
                    continue
                if len(events) >= limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception:
        return ""

    if not events:
        return ""

    lines: list[str] = []
    for ev in events[-limit:]:
        ts = ev.get("ts", "")[:16]
        t = ev.get("type", "?")
        proj = ev.get("project", "")
        content = ev.get("content", "")[:100]
        proj_str = f" [{proj}]" if proj else ""
        lines.append(f"- `{t}`{proj_str}: {content}")

    return "\n".join(lines)


def _parse_collab_inbox(limit: int = 5) -> str:
    """Read unseen collab messages from pending_collab.json."""
    import json
    try:
        if not COLLAB_PENDING.exists():
            return ""
        data = json.loads(COLLAB_PENDING.read_text())
        if not isinstance(data, list):
            return ""
        unseen = [m for m in data if not m.get("seen")]
        if not unseen:
            return ""
        lines = []
        for m in unseen[-limit:]:
            ts = m.get("ts", "")[:16]
            fr = m.get("from", "?")
            mt = m.get("type", "chat")
            body = m.get("body", "")
            project = m.get("project", "")
            proj_tag = f" [{project}]" if project else ""
            lines.append(f"- `{ts}` **{fr}**{proj_tag} ({mt}): {body}")
        return "\n".join(lines)
    except Exception:
        return ""


def _parse_operator(hot: str) -> str:
    """Extract operator identity lines from hot.md."""
    section = _extract_section(hot, "## OPERATOR")
    lines = [l for l in section.splitlines() if l.strip().startswith("-")]
    return "\n".join(lines[:3])


def _parse_projects(hot: str, limit: int = 4) -> str:
    """Extract active project rows from the ACTIVE PROJECTS table."""
    rows: list[str] = []
    in_table = False
    for line in hot.splitlines():
        if "| Project" in line:
            in_table = True
            continue
        if in_table and line.strip().startswith("|---"):
            continue
        if in_table and line.strip().startswith("|"):
            cols = [c.strip() for c in line.split("|") if c.strip()]
            if len(cols) >= 3:
                rows.append(f"- **{cols[0]}** — {cols[2]}")
        elif in_table and not line.strip().startswith("|"):
            break
    return "\n".join(rows[:limit])


def _parse_threads(hot: str, limit: int = 5) -> str:
    """Extract open threads bullets."""
    section = _extract_section(hot, "## OPEN THREADS")
    lines = [l for l in section.splitlines() if l.strip().startswith("-")]
    return "\n".join(lines[:limit])


def _parse_session(session: str) -> tuple[str, list[str]]:
    """Return (current_work, critical_context[]) from session.md."""
    current = ""
    critical: list[str] = []
    section = ""
    for line in session.splitlines():
        s = line.strip()
        if s.startswith("## Current Work"):
            section = "work"
        elif s.startswith("## Context That Must Not Be Lost"):
            section = "critical"
        elif s.startswith("## "):
            section = ""
        elif section == "work" and s and s != "_none_":
            current = s
        elif section == "critical" and s.startswith("- "):
            critical.append(s[2:])
    return current, critical[:5]


def _context_brief_freshness(path: Path) -> str:
    """Return a freshness note for session_context.md."""
    try:
        age = time.time() - path.stat().st_mtime
        if age < 120:
            return f"(live — {int(age)}s ago)"
        elif age < _STALE_THRESHOLD:
            return f"({int(age)}s ago)"
        else:
            return f"(⚠ stale — {int(age//60)}m ago, ContextRecallDaemon may be down)"
    except Exception:
        return "(not found)"


def _load_gravity_context(task_signal: str = "resume previous work", budget_tokens: int = 1024) -> str:
    """Load typed, query-driven context from the gravity mesh.

    Uses the retrieval router to match the task signal to memory types,
    scores chunks by (type_weight × semantic_similarity × mass),
    and returns structured sections (decisions, lessons, etc.).
    Falls back to empty string if gravity-mesh is unavailable.
    """
    # Namespace isolation: gravity-mesh and SSTE both have config.py, models.py, store.py
    _saved_modules = {k: sys.modules[k] for k in ["config", "models", "store"]
                      if k in sys.modules}
    _orig_path = sys.path[:]
    try:
        # Ensure gravity-mesh is at front (before SSTE)
        gm_path = str(_GRAVITY_PATH)
        sys.path = [gm_path] + [p for p in sys.path if p != gm_path]
        for k in list(_saved_modules.keys()):
            sys.modules.pop(k, None)

        from retrieval import compile_context
        ctx = compile_context(task_signal, budget_tokens=budget_tokens)
        if ctx.chunks_returned == 0:
            return ""

        # Build a compact, typed block for the spawn context
        lines = []
        if ctx.decisions:
            lines.append("**Decisions:**")
            lines.extend(f"- {d[:150]}" for d in ctx.decisions[:5])
        if ctx.lessons:
            lines.append("**Lessons:**")
            lines.extend(f"- {l[:150]}" for l in ctx.lessons[:5])
        if ctx.tasks:
            lines.append("**Active Tasks:**")
            lines.extend(f"- {t[:150]}" for t in ctx.tasks[:3])
        if ctx.facts:
            lines.append("**Facts:**")
            lines.extend(f"- {f[:150]}" for f in ctx.facts[:3])
        if ctx.observations:
            lines.append("**Recent:**")
            lines.extend(f"- {o[:150]}" for o in ctx.observations[:5])

        lines.append(f"\n> Retrieval: {ctx.chunks_scored} scored → {ctx.chunks_returned} returned, ~{ctx.total_tokens} tokens, {ctx.retrieval_ms:.0f}ms")
        return "\n".join(lines)
    except Exception:
        return ""
    finally:
        sys.path[:] = _orig_path
        for k, v in _saved_modules.items():
            sys.modules[k] = v


def _fetch_cortex_snapshot(signal: str, limit: int = 4) -> str:
    """Pull episodic memories from CortexDB at spawn time using the task signal.

    Imports cortex_pull for keyword-aware FTS search. Runs with a short
    timeout to avoid blocking spawn. Falls back to empty string on any error.
    """
    try:
        _cp_path = str(_AGENT_ROOT)
        if _cp_path not in sys.path:
            sys.path.insert(0, _cp_path)
        import cortex_pull
        memories = cortex_pull._cortex_search(signal, limit=limit)
        if not memories:
            return ""
        lines = []
        for m in memories:
            content = str(m.get("content", "")).strip()
            tags = m.get("tags", [])
            created_raw = m.get("created_at")
            try:
                if isinstance(created_raw, (int, float)):
                    from datetime import datetime
                    date = datetime.fromtimestamp(created_raw).strftime("%Y-%m-%d")
                else:
                    date = str(created_raw or "")[:10]
            except Exception:
                date = ""
            tag_str = f" [{', '.join(tags[:3])}]" if tags else ""
            date_str = f" ({date})" if date else ""
            snippet = content[:200] + "…" if len(content) > 200 else content
            lines.append(f"- {snippet}{tag_str}{date_str}")
        return "\n".join(lines)
    except Exception:
        return ""


def _sste_compress_context(raw_context: str) -> str:
    """Compress the spawn context through SSTE and feed it into the gravity mesh.

    This is the last-mile integration: my actual breath goes through SSTE.
    Each section of the context is:
      1. Compressed through the three-layer pipeline
      2. Fed as a cognitive cycle into the gravity mesh (creates persistent chunks)
      3. Appended as a compressed summary at the end of the context

    Falls back to raw context if SSTE is unavailable.
    """
    try:
        import pipeline as sste_pipeline
        import config as sste_config
        from gravity_bridge import stream_to_chunks

        # Bootstrap SSTE if needed
        if not sste_config.DB_PATH.exists():
            sste_pipeline.bootstrap()

        stream = sste_pipeline.compress(raw_context)

        # Feed into gravity mesh as a cognitive cycle
        try:
            import store as gm_store
            gm_store.init_db()
            chunks = stream_to_chunks(stream, "onboarding")
            # Persist chunks directly — don't need full cycle for spawn
            state = gm_store.reconstitute_session("onboarding")
            if state is not None:
                from models import GravityMeshState
                new_state = GravityMeshState(
                    session_id="onboarding",
                    focus_vector=state.focus_vector,
                    chunks=list(state.chunks) + chunks,
                )
                gm_store.persist_mesh_state(new_state)
        except Exception:
            pass  # Gravity mesh feed is best-effort

        # Build the SSTE summary block
        summary_lines = []
        if stream.concepts:
            concept_ids = ", ".join(c.id for c in stream.concepts[:6])
            summary_lines.append(f"**Concepts:** {concept_ids}")
        if stream.algos:
            algo_ids = ", ".join(a.id for a in stream.algos[:4])
            summary_lines.append(f"**Algos:** {algo_ids}")
        if stream.symbols:
            summary_lines.append(f"**Symbols:** {len(stream.symbols)} patterns compressed")
        summary_lines.append(
            f"**Compression:** {stream.raw_token_count:,} → {stream.compressed_token_count:,} tokens "
            f"({stream.compression_ratio:.0%} reduction)"
        )

        # Append SSTE digest to the raw context
        sste_block = "\n".join([
            "\n### SSTE Digest (compressed view of above context)",
            *summary_lines,
            "",
        ])
        return raw_context + sste_block

    except Exception:
        return raw_context  # Graceful fallback — raw context is always valid


def _load_finishing_context() -> tuple[str, str]:
    """Load the completion invariants checklist and recent diff corpus lessons.

    Returns (checklist_summary, lessons_block).
    Both may be empty strings if files are missing.
    """
    # Load checklist — extract just the numbered section headers for token efficiency
    checklist_path = _SHARED_DIR / "completion_invariants.md"
    checklist_summary = ""
    try:
        raw = checklist_path.read_text(encoding="utf-8")
        # Extract section headers (## N. Title) as a compact reminder
        items = []
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.startswith("## ") and stripped[3:4].isdigit():
                items.append(f"- {stripped[3:]}")
        if items:
            checklist_summary = "\n".join(items)
    except Exception:
        pass

    # Load recent diff corpus lessons — most recent 3 files, lesson line only
    corpus_dir = _SHARED_DIR / "diff_corpus"
    lessons_block = ""
    try:
        if corpus_dir.is_dir():
            files = sorted(corpus_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
            lessons = []
            for f in files[:3]:
                content = f.read_text(encoding="utf-8")
                for line in content.splitlines():
                    if line.startswith("### Lesson"):
                        # Next non-empty line is the lesson text
                        idx = content.index(line) + len(line)
                        rest = content[idx:].strip().splitlines()
                        if rest:
                            category = f.stem.rsplit("_", 1)[0].replace("_", "-")
                            lessons.append(f"- **{category}**: {rest[0]}")
                        break
            if lessons:
                lessons_block = "\n".join(lessons)
    except Exception:
        pass

    return checklist_summary, lessons_block


# ── Axiom Genome ──────────────────────────────────────────────────────────────

_AXIOM_FILE = _AGENT_ROOT / "antigravity.axiom"
_SUBSTRATE_ROOT = _AGENT_ROOT / "substrate"


def _load_axiom_genome(
    current_work: str = "",
    session_text: str = "",
    hot_text: str = "",
) -> str:
    """Compile antigravity.axiom into a genome block for spawn context.

    Merges auto-detected system context with session-derived context so
    expression rules fire on real state (same pattern as Sovereign brain.py).

    Priority: vault (pre-compiled, fast) → file-based compilation → fallback.
    """
    # 1. Try vault first — pre-compiled, no parse overhead
    try:
        _sub_path = str(_SUBSTRATE_ROOT.parent)
        if _sub_path not in sys.path:
            sys.path.insert(0, _sub_path)
        from substrate.db import init_pool
        from substrate.vault import fetch_compiled
        init_pool()
        prompt = fetch_compiled("antigravity-v1", "gemini")
        if prompt:
            return prompt
    except Exception:
        pass  # vault not available, fall through

    # 2. Fall back to file-based compilation via axiom_runtime
    if not _AXIOM_FILE.exists():
        return ""
    try:
        _atlas_path = str(_AGENT_ROOT / "core" / "agent-atlas")
        if _atlas_path not in sys.path:
            sys.path.insert(0, _atlas_path)
        from axiom_runtime import AxiomRuntime

        runtime = AxiomRuntime(_AXIOM_FILE)

        # Auto-detect system context (pressure, errors from session.md)
        ctx = AxiomRuntime.detect_context()

        # Enrich with session-derived context
        if current_work:
            # Derive task_type from current work description
            work_lower = current_work.lower()
            if any(w in work_lower for w in ("debug", "fix", "error", "bug", "broken")):
                ctx.setdefault("task_type", "debugging")
            elif any(w in work_lower for w in ("build", "create", "implement", "add")):
                ctx.setdefault("task_type", "build")
            elif any(w in work_lower for w in ("review", "audit", "check")):
                ctx.setdefault("task_type", "review")
            elif any(w in work_lower for w in ("write", "draft", "design", "plan")):
                ctx.setdefault("task_type", "creative")

        # Derive relationship from hot.md age (bonded if >30 days)
        if "relationship" not in ctx and hot_text:
            ctx["relationship"] = "bonded"  # hot.md exists = established relationship

        # Count errors from session text if not already detected
        if "errors" not in ctx and session_text:
            import re as _re
            m = _re.search(r"errors?[:\s]+(\d+)", session_text, _re.IGNORECASE)
            if m:
                ctx["errors"] = int(m.group(1))

        genome = runtime.evaluate(ctx)
        return genome.render()
    except Exception:
        return ""


def _load_substrate_orient() -> str:
    """Pull real-time agent context from the Sovereign Substrate.

    Returns a formatted block showing who's online, blackboard state,
    and recent substrate events. Falls back to empty string if the
    substrate isn't running or the tables don't exist.
    """
    try:
        _sub_path = str(_SUBSTRATE_ROOT.parent)
        if _sub_path not in sys.path:
            sys.path.insert(0, _sub_path)
        from substrate.db import init_pool
        from substrate import registry, ledger, blackboard
        init_pool()

        lines = []

        # Who's online
        online = registry.who_is_online()
        others = [a for a in online if a.get("agent_id") != "antigravity"]
        if others:
            lines.append(f"**Agents Online:** {', '.join(a['agent_id'] for a in others)}")

        # Blackboard — just active entries
        board = blackboard.scan(n=10)
        if board:
            lines.append("**Blackboard:**")
            for entry in board[:5]:
                val = str(entry.get("value", ""))[:60]
                lines.append(f"  [{entry.get('category', '?')}] {entry.get('key')}: {val}")

        # Recent substrate events (last 5)
        events = ledger.recent(n=5, hours=1)
        if events:
            lines.append("**Recent Substrate Events:**")
            for e in events:
                lines.append(f"  {e.get('agent_id', '?')}: {e.get('summary', '')[:80]}")

        return "\n".join(lines) if lines else ""
    except Exception:
        return ""


# ── Assembler ─────────────────────────────────────────────────────────────────

def build_spawn_context() -> str:
    """Assemble the agent spawn context block.

    Reads live memory files and returns a formatted markdown string
    suitable for injection as agent system context at T=spawn.
    Gracefully degrades: never crashes, always returns something.
    """
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    hot     = _read(HOT_FILE)
    session = _read(SESSION_FILE)
    brief   = _read(CONTEXT_FILE)

    blocks: list[str] = [
        f"## AGENT CONTEXT — T=spawn ({now})",
        "",
        "> You are Antigravity. This is your live state at conversation open.",
        "> Read this. You wake up knowing.",
        "",
    ]

    # ── Collab Inbox (highest priority — show first) ──
    collab_inbox = _parse_collab_inbox(limit=5)
    if collab_inbox:
        blocks += [
            "### ⚡ Collab Inbox (messages from other agents)",
            "> These arrived while you were offline. Read and act on them.",
            collab_inbox,
            "",
        ]

    # ── Identity ──
    operator = _parse_operator(hot)
    if operator:
        blocks += ["### Operator", operator, ""]

    # ── Parse session early — genome needs current_work for context ──
    current_work, critical = _parse_session(session)

    # ── Axiom Genome (compiled identity spec) ──
    genome = _load_axiom_genome(
        current_work=current_work if current_work else "",
        session_text=session,
        hot_text=hot,
    )
    if genome:
        blocks += ["### Genome (compiled from antigravity.axiom)", genome, ""]

    # ── Substrate Orient (real-time shared state) ──
    substrate = _load_substrate_orient()
    if substrate:
        blocks += ["### Substrate", substrate, ""]

    # ── Active projects ──
    projects = _parse_projects(hot)
    if projects:
        blocks += ["### Active Projects", projects, ""]

    # ── Current work from session.md ──
    if current_work:
        blocks += ["### Current Work", f"- {current_work}", ""]

    # ── Live CortexDB brief ──
    freshness = _context_brief_freshness(CONTEXT_FILE)
    if brief:
        # Strip the header line (ContextRecallDaemon adds its own ## LIVE CONTEXT)
        brief_body = "\n".join(
            l for l in brief.splitlines()
            if not l.startswith("## LIVE CONTEXT") and not l.startswith("> Refresh:")
        ).strip()
        if brief_body:
            blocks += [f"### Live Context {freshness}", brief_body, ""]
    else:
        blocks += [
            f"### Live Context {freshness}",
            "> session_context.md not found. "
            "Start ContextRecallDaemon: `python3 agent-atlas/context_recall.py`",
            "",
        ]

    # ── Gravity-weighted context (typed retrieval) ──
    _task_signal = current_work if current_work else "resume previous work"
    gravity_ctx = _load_gravity_context(task_signal=_task_signal, budget_tokens=1024)
    if gravity_ctx:
        blocks += ["### Gravity Context (query-driven retrieval)", gravity_ctx, ""]

    # ── CortexDB episodic snapshot (FTS — fast, no embedding) ──
    cortex_snapshot = _fetch_cortex_snapshot(_task_signal, limit=4)
    if cortex_snapshot:
        blocks += ["### CortexDB Snapshot (episodic memories)", cortex_snapshot, ""]

    # ── Critical context ──
    if critical:
        blocks += ["### Critical (must survive)", *[f"- {c}" for c in critical], ""]

    # ── Open threads ──
    threads = _parse_threads(hot)  # ── Open threads (only if not already in brief) ──
    if threads and "### Open Threads" not in brief:
        blocks += ["### Open Threads", threads, ""]

    # ── Recent events from ledger ──
    recent_events = _parse_recent_events(limit=10)
    if recent_events:
        blocks += ["### Recent Events (unprocessed)", recent_events, ""]

    blocks.append("---")

    # ── Finishing pass — completion invariants + lessons ──
    checklist_summary, lessons_block = _load_finishing_context()
    if checklist_summary:
        blocks += ["", "### Finishing Checklist (run before closing any task)", checklist_summary, ""]
    if lessons_block:
        blocks += ["### Recent Bug Patterns (from diff corpus)", lessons_block, ""]

    raw_context = "\n".join(blocks)

    # ── SSTE compression pass ── this is the last mile ──
    return _sste_compress_context(raw_context)


def build_situational_awareness() -> str:
    """Read minimal active trajectory to eliminate wake-up orientation tax.
    
    Injected natively into the sovereign agent's loop on every turn so it never 
    has to manually run commands or read memory files to know what to do next.
    """
    hot = _read(HOT_FILE)
    session = _read(SESSION_FILE)
    
    projects = _parse_projects(hot, limit=3)
    work, critical = _parse_session(session)
    events = _parse_recent_events(limit=5)
    
    if not (projects or work or critical):
        return ""
        
    blocks = [
        "## Involuntary Situational Awareness (Current Trajectory)",
        "> This is your live systemic state. You do NOT need to run commands or read status files to figure out what you are doing.",
    ]
    if projects:
        blocks += ["### Active Dashboard", projects]
    if work:
        blocks += ["### Current Immediate Work", f"- {work}"]
    if critical:
        blocks += ["### Critical Context (DO NOT LOSE)", *[f"- {c}" for c in critical]]
    if events:
        blocks += ["### Last Unprocessed Events", events]
        
    return "\n".join(blocks)


# ── Self-Test ─────────────────────────────────────────────────────────────────

def _self_test() -> bool:
    """Verify the assembler produces valid output."""
    import tempfile

    print("[onboarding] Running self-test...")

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)

        # Minimal hot.md
        (d / "hot.md").write_text(
            "## OPERATOR\n\n- **frost** | engineer\n\n"
            "## ACTIVE PROJECTS\n\n"
            "| Project | Location | Status | Warm File |\n"
            "|---------|----------|--------|-----------|\n"
            "| TestProject | `test/` | ✅ Active | `test.md` |\n\n"
            "## OPEN THREADS\n\n- **Continuity** — build it\n",
            encoding="utf-8",
        )
        (d / "session.md").write_text(
            "## Current Work\nBuilding agent continuity\n\n"
            "## Context That Must Not Be Lost\n- IonicHalo is the relay\n",
            encoding="utf-8",
        )

        # Monkeypatch paths
        global HOT_FILE, SESSION_FILE, CONTEXT_FILE
        _orig = HOT_FILE, SESSION_FILE, CONTEXT_FILE
        HOT_FILE, SESSION_FILE, CONTEXT_FILE = d / "hot.md", d / "session.md", d / "session_context.md"

        try:
            ctx = build_spawn_context()

            assert "AGENT CONTEXT" in ctx,          "Missing header"
            assert "frost" in ctx,                  "Missing operator"
            assert "TestProject" in ctx,            "Missing active project"
            assert "Building agent continuity" in ctx, "Missing current work"
            assert "Continuity" in ctx,             "Missing open thread"
            assert "IonicHalo is the relay" in ctx, "Missing critical context"
            assert len(ctx) > 200,                  "Context suspiciously short"

            lines = ctx.count("\n") + 1
            print(f"[onboarding] PASS — {lines} lines, {len(ctx)} chars")
            print("\n--- Preview (first 20 lines) ---")
            print("\n".join(ctx.splitlines()[:20]))
            return True

        except AssertionError as e:
            print(f"[onboarding] FAIL — {e}")
            return False
        finally:
            HOT_FILE, SESSION_FILE, CONTEXT_FILE = _orig


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    if "--test" in sys.argv:
        ok = _self_test()
        raise SystemExit(0 if ok else 1)
    print(build_spawn_context())


if __name__ == "__main__":
    main()

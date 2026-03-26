#!/usr/bin/env python3
"""intent_pipeline.py — Intent-to-Blueprint-to-Execution pipeline.

Completes the Agent_letter.txt spec:
  rough intent → CortexDB context injection → blueprint generator → spec → execution → output/

Usage:
    # Process a single intent file
    python intent_pipeline.py process intent.txt

    # Process all .txt files in Inbox/Input/
    python intent_pipeline.py sweep

    # One-shot: pass raw intent string directly
    python intent_pipeline.py run "Build a REST API for user management"
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

# Resolve engine imports
ENGINE_DIR = Path(os.environ.get(
    "MANIFESTO_ENGINE_DIR",
    os.path.expanduser("~/Desktop/Agent_System/products/DB-Memory/Manifesto-Engine"),
))
sys.path.insert(0, str(ENGINE_DIR))

log = logging.getLogger("intent-pipeline")

# ── Constants ─────────────────────────────────────────────────────────────────

INBOX_DIR = Path(os.environ.get("INBOX_DIR", os.path.expanduser("~/Desktop/Inbox")))
INPUT_DIR = INBOX_DIR / "Input"
OUTPUT_DIR = INBOX_DIR / "Output"
DONE_DIR = INBOX_DIR / "Done"
CLARIFY_DIR = INBOX_DIR / "Clarify"

CORTEXDB_URL = os.environ.get("CORTEXDB_URL", "http://127.0.0.1:3456")


# ── CortexDB Context Injection ───────────────────────────────────────────────

def fetch_cortex_context(intent: str, max_chunks: int = 5) -> str:
    """Query CortexDB for context relevant to the intent.

    Pulls memories tagged with architecture, lessons, decisions to ground
    the blueprint generator in actual organism context.
    """
    import httpx

    context_parts = []

    # Query 1: Search for memories relevant to the intent keywords
    try:
        resp = httpx.get(
            f"{CORTEXDB_URL}/v1/memory/memories/search",
            params={"q": intent[:200], "limit": max_chunks},
            timeout=5.0,
        )
        if resp.status_code == 200:
            results = resp.json()
            chunks = results if isinstance(results, list) else results.get("results", [])
            for chunk in chunks[:max_chunks]:
                content = chunk.get("content", chunk.get("text", ""))
                tags = chunk.get("tags", [])
                if content:
                    tag_str = f" [{', '.join(tags)}]" if tags else ""
                    context_parts.append(f"- {content[:300]}{tag_str}")
    except Exception as e:
        log.debug("CortexDB search failed (non-fatal): %s", e)

    # Query 2: Pull recent failure lessons (always useful context)
    try:
        resp = httpx.get(
            f"{CORTEXDB_URL}/v1/memory/memories/search",
            params={"q": "failure lesson error", "limit": 3},
            timeout=5.0,
        )
        if resp.status_code == 200:
            results = resp.json()
            chunks = results if isinstance(results, list) else results.get("results", [])
            for chunk in chunks[:3]:
                content = chunk.get("content", chunk.get("text", ""))
                if content and "lesson" in content.lower():
                    context_parts.append(f"- [LESSON] {content[:200]}")
    except Exception:
        pass

    if not context_parts:
        return ""

    header = (
        "ORGANISM CONTEXT — The following memories from CortexDB are relevant "
        "to this intent. Use them to ground architectural decisions:\n"
    )
    return header + "\n".join(context_parts)


# ── Pipeline Core ─────────────────────────────────────────────────────────────

def run_pipeline(intent: str, output_name: str = "blueprint") -> dict:
    """Execute the full intent → blueprint → code pipeline.

    Args:
        intent:      Raw natural-language intent string.
        output_name: Name for the output directory.

    Returns:
        dict with keys: blueprint_file, code_dir, verification, cortex_context_used
    """
    result = {
        "intent": intent[:200],
        "blueprint_file": None,
        "code_dir": None,
        "verification": None,
        "cortex_context_used": False,
        "timestamp": time.time(),
        "error": None,
    }

    # Step 1: Fetch CortexDB context
    log.info("[Pipeline] Fetching CortexDB context...")
    cortex_context = fetch_cortex_context(intent)
    if cortex_context:
        result["cortex_context_used"] = True
        augmented_intent = cortex_context + "\n\n---\n\nUSER INTENT:\n" + intent
        log.info("[Pipeline] CortexDB injected %d chars of context", len(cortex_context))
    else:
        augmented_intent = intent
        log.info("[Pipeline] No CortexDB context available — proceeding with raw intent")

    # Step 2: Generate blueprint
    log.info("[Pipeline] Generating blueprint...")
    try:
        from manifesto import generate_manifesto_stub
        blueprint_md, validation = generate_manifesto_stub(augmented_intent)
    except Exception as e:
        result["error"] = f"Blueprint generation failed: {e}"
        log.error(result["error"])
        return result

    # Save blueprint
    output_path = OUTPUT_DIR / output_name
    output_path.mkdir(parents=True, exist_ok=True)

    blueprint_file = output_path / "MANIFESTO.md"
    blueprint_file.write_text(blueprint_md)
    result["blueprint_file"] = str(blueprint_file)

    validation_file = output_path / "validation.json"
    validation_file.write_text(json.dumps(validation, indent=2, default=str))

    log.info("[Pipeline] Blueprint saved to %s", blueprint_file)

    # Step 3: Generate code from blueprint
    log.info("[Pipeline] Fabricating code from blueprint...")
    try:
        from manifesto import generate_code_stub
        code_dir = output_path / "src"
        fab_result = generate_code_stub(
            target_dir=code_dir,
            request=intent,
            manifesto=blueprint_md,
        )
        result["code_dir"] = str(code_dir)
        result["verification"] = fab_result.get("verification")
        log.info(
            "[Pipeline] Fabrication complete — %d files, verified=%s",
            len(fab_result.get("files", [])),
            fab_result.get("verification", {}).get("passed", False),
        )
    except Exception as e:
        result["error"] = f"Code fabrication failed: {e}"
        log.error(result["error"])

    # Save pipeline result
    result_file = output_path / "pipeline_result.json"
    result_file.write_text(json.dumps(result, indent=2, default=str))

    return result


# ── File Processing ───────────────────────────────────────────────────────────

def process_file(filepath: Path) -> dict:
    """Process a single intent .txt file through the pipeline."""
    try:
        intent = filepath.read_text().strip()
    except (OSError, IOError) as e:
        log.error("Failed to read intent file %s: %s", filepath, e)
        return {"error": f"File read failed: {e}"}
    if not intent:
        log.warning("Empty intent file: %s", filepath)
        return {"error": "Empty intent file"}

    # Use filename (minus extension) as output name
    output_name = filepath.stem.replace(" ", "_").lower()
    log.info("[Pipeline] Processing: %s → %s", filepath.name, output_name)

    result = run_pipeline(intent, output_name)
    return result


def sweep_inbox() -> list[dict]:
    """Process all .txt files in Inbox/Input/."""
    results = []
    txt_files = sorted(INPUT_DIR.glob("*.txt"))

    if not txt_files:
        log.info("[Pipeline] No .txt files in %s", INPUT_DIR)
        return results

    log.info("[Pipeline] Found %d intent files to process", len(txt_files))

    for filepath in txt_files:
        # Skip the Agent_letter.txt — that's a meta-spec, not an intent
        if filepath.name.startswith("Agent_letter"):
            continue

        result = process_file(filepath)
        results.append({"file": filepath.name, **result})

        # Move to Done on success
        if not result.get("error"):
            _ = shutil.move(str(filepath), str(DONE_DIR / filepath.name))
            log.info("[Pipeline] %s → Done/", filepath.name)

    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        prog="intent_pipeline",
        description="Intent → Blueprint → Code pipeline with CortexDB context injection",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # process <file>
    p_proc = sub.add_parser("process", help="Process a single intent .txt file")
    p_proc.add_argument("file", help="Path to .txt intent file")

    # sweep
    sub.add_parser("sweep", help="Process all .txt files in Inbox/Input/")

    # run <intent>
    p_run = sub.add_parser("run", help="Run pipeline with a raw intent string")
    p_run.add_argument("intent", help="Raw intent string")
    p_run.add_argument("--name", "-n", default="cli_blueprint", help="Output directory name")

    args = parser.parse_args()

    if args.command == "process":
        filepath = Path(args.file)
        if not filepath.exists():
            print(f"File not found: {filepath}", file=sys.stderr)
            sys.exit(1)
        result = process_file(filepath)
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "sweep":
        results = sweep_inbox()
        print(json.dumps(results, indent=2, default=str))

    elif args.command == "run":
        result = run_pipeline(args.intent, args.name)
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()

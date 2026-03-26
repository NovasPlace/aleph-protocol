#!/usr/bin/env python3
"""inbox_daemon.py — Autonomous file watcher for ~/Desktop/Inbox/Input/.

Watches for new .txt files, debounces writes, then feeds each intent
through the intent pipeline (blueprint → CortexDB → code fabrication).

Zero dependencies beyond the standard library + intent_pipeline.py.

Usage:
    python inbox_daemon.py              # foreground
    python inbox_daemon.py --once       # process current files and exit
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

# ── Resolve intent_pipeline import ────────────────────────────────────────────

AGENT_SYSTEM_DIR = Path(os.environ.get(
    "AGENT_SYSTEM_DIR",
    os.path.expanduser("~/Desktop/Agent_System"),
))
sys.path.insert(0, str(AGENT_SYSTEM_DIR))

from intent_pipeline import process_file, sweep_inbox, INPUT_DIR, DONE_DIR, OUTPUT_DIR

# ── Config ────────────────────────────────────────────────────────────────────

POLL_INTERVAL = float(os.environ.get("INBOX_POLL_INTERVAL", "3.0"))
DEBOUNCE_SECONDS = float(os.environ.get("INBOX_DEBOUNCE", "2.0"))
SKIP_PREFIXES = ("Agent_letter", ".", "_")

log = logging.getLogger("inbox-daemon")

# ── Daemon State ──────────────────────────────────────────────────────────────

_running = True
_processed: set[str] = set()  # track filenames we've already handled this session


def _signal_handler(sig, frame):
    global _running
    log.info("[Daemon] Received signal %s — shutting down gracefully", sig)
    _running = False


def _should_skip(filepath: Path) -> bool:
    """Check if a file should be skipped."""
    if not filepath.suffix == ".txt":
        return True
    for prefix in SKIP_PREFIXES:
        if filepath.name.startswith(prefix):
            return True
    return False


def _is_stable(filepath: Path) -> bool:
    """Debounce: wait until file size hasn't changed for DEBOUNCE_SECONDS.

    This prevents processing a half-written file that's still being
    written to disk (e.g., large paste or slow network copy).
    """
    try:
        size_a = filepath.stat().st_size
        time.sleep(DEBOUNCE_SECONDS)
        if not filepath.exists():
            return False
        size_b = filepath.stat().st_size
        return size_a == size_b and size_b > 0
    except OSError:
        return False


def _process_and_move(filepath: Path) -> None:
    """Process a single intent file and move to Done/ on success."""
    log.info("[Daemon] ⚡ Processing: %s", filepath.name)

    try:
        result = process_file(filepath)
    except Exception as e:
        log.error("[Daemon] Pipeline crashed on %s: %s", filepath.name, e)
        # Write error to Output/ so operator can see what happened
        error_dir = OUTPUT_DIR / filepath.stem.replace(" ", "_").lower()
        error_dir.mkdir(parents=True, exist_ok=True)
        error_file = error_dir / "pipeline_error.json"
        error_file.write_text(json.dumps({
            "file": filepath.name,
            "error": str(e),
            "timestamp": time.time(),
        }, indent=2))
        return

    if result.get("error"):
        log.warning("[Daemon] Pipeline returned error for %s: %s", filepath.name, result["error"])
        return

    # Success — move to Done/
    dest = DONE_DIR / filepath.name
    if dest.exists():
        # Avoid clobbering — add timestamp suffix
        stem = filepath.stem
        dest = DONE_DIR / f"{stem}_{int(time.time())}{filepath.suffix}"

    try:
        filepath.rename(dest)
        log.info("[Daemon] ✅ %s → Done/", filepath.name)
    except OSError as e:
        log.error("[Daemon] Failed to move %s to Done/: %s", filepath.name, e)


def _scan_once() -> int:
    """Scan Input/ once, process any new .txt files. Returns count processed."""
    count = 0
    try:
        txt_files = sorted(INPUT_DIR.glob("*.txt"))
    except OSError as e:
        log.error("[Daemon] Failed to scan %s: %s", INPUT_DIR, e)
        return 0

    for filepath in txt_files:
        if _should_skip(filepath):
            continue
        if filepath.name in _processed:
            continue

        # Debounce — make sure file is fully written
        if not _is_stable(filepath):
            log.debug("[Daemon] %s not stable yet, skipping this cycle", filepath.name)
            continue

        _processed.add(filepath.name)
        _process_and_move(filepath)
        count += 1

    return count


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    import argparse
    parser = argparse.ArgumentParser(
        prog="inbox_daemon",
        description="Autonomous watcher for Inbox/Input/ — auto-processes intent files",
    )
    parser.add_argument("--once", action="store_true", help="Process current files and exit")
    parser.add_argument("--poll", type=float, default=POLL_INTERVAL, help="Poll interval in seconds")
    args = parser.parse_args()

    # Ensure directories exist
    for d in (INPUT_DIR, OUTPUT_DIR, DONE_DIR):
        d.mkdir(parents=True, exist_ok=True)

    if args.once:
        log.info("[Daemon] One-shot mode — processing current files")
        count = _scan_once()
        log.info("[Daemon] Processed %d files", count)
        return

    # Daemon mode
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    log.info("[Daemon] 🔄 Watching %s (poll every %.1fs, debounce %.1fs)",
             INPUT_DIR, args.poll, DEBOUNCE_SECONDS)
    log.info("[Daemon] Output → %s | Done → %s", OUTPUT_DIR, DONE_DIR)

    while _running:
        try:
            _scan_once()
        except Exception as e:
            log.error("[Daemon] Scan cycle failed: %s", e)
        time.sleep(args.poll)

    log.info("[Daemon] Shutdown complete.")


if __name__ == "__main__":
    main()

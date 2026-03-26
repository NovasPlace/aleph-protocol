#!/usr/bin/env python3
"""inbox_daemon.py — Autonomous file watcher for ~/Desktop/Inbox/Input/.

Watches for new .txt, .md, and .pdf files, debounces writes, then feeds
each intent through the intent pipeline (blueprint → CortexDB → code fabrication).

PDF text extraction uses pdftotext (poppler-utils).
Zero Python dependencies beyond the standard library + intent_pipeline.py.

Usage:
    python inbox_daemon.py              # foreground
    python inbox_daemon.py --once       # process current files and exit
"""
from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
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
ACCEPTED_EXTENSIONS = {".txt", ".md", ".pdf"}
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
    if filepath.suffix.lower() not in ACCEPTED_EXTENSIONS:
        return True
    for prefix in SKIP_PREFIXES:
        if filepath.name.startswith(prefix):
            return True
    return False


def _extract_text(filepath: Path) -> str | None:
    """Extract text content from .txt, .md, or .pdf files.

    Returns the extracted text or None on failure.
    """
    ext = filepath.suffix.lower()

    if ext in (".txt", ".md"):
        try:
            return filepath.read_text(encoding="utf-8", errors="replace").strip()
        except OSError as e:
            log.error("[Daemon] Failed to read %s: %s", filepath.name, e)
            return None

    if ext == ".pdf":
        try:
            result = subprocess.run(
                ["pdftotext", "-layout", str(filepath), "-"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                log.error("[Daemon] pdftotext failed on %s: %s", filepath.name, result.stderr)
                return None
            text = result.stdout.strip()
            if not text:
                log.warning("[Daemon] pdftotext returned empty output for %s", filepath.name)
                return None
            return text
        except FileNotFoundError:
            log.error("[Daemon] pdftotext not installed — install poppler-utils")
            return None
        except subprocess.TimeoutExpired:
            log.error("[Daemon] pdftotext timed out on %s", filepath.name)
            return None

    return None


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
    """Process a single intent file and move to Done/ on success.

    For .md and .pdf files, extracts text and writes a temporary .txt
    file for the pipeline, then cleans up.
    """
    log.info("[Daemon] ⚡ Processing: %s", filepath.name)

    # For non-.txt files, extract text into a temp .txt for the pipeline
    temp_txt = None
    pipeline_input = filepath

    if filepath.suffix.lower() != ".txt":
        text = _extract_text(filepath)
        if not text:
            log.error("[Daemon] Text extraction failed for %s — skipping", filepath.name)
            return
        # Write extracted text to a temp file in Input/
        temp_txt = INPUT_DIR / f".tmp_{filepath.stem}.txt"
        temp_txt.write_text(text, encoding="utf-8")
        pipeline_input = temp_txt
        log.info("[Daemon] Extracted %d chars from %s", len(text), filepath.name)

    try:
        result = process_file(pipeline_input)
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
    finally:
        # Clean up temp file if we created one
        if temp_txt and temp_txt.exists():
            temp_txt.unlink()


def _scan_once() -> int:
    """Scan Input/ once, process any new files. Returns count processed."""
    count = 0
    try:
        all_files = []
        for ext in ACCEPTED_EXTENSIONS:
            all_files.extend(INPUT_DIR.glob(f"*{ext}"))
        all_files.sort()
    except OSError as e:
        log.error("[Daemon] Failed to scan %s: %s", INPUT_DIR, e)
        return 0

    for filepath in all_files:
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

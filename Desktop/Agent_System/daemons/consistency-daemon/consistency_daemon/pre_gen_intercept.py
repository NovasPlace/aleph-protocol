"""pre_gen_intercept.py — Pre-generation consistency gate.

Agents call this BEFORE committing to an implementation direction.
Checks whether the proposed action is:
  - Derivable from the given spec/context (not a gap-fill guess)
  - Consistent with already established context
  - Above confidence threshold to proceed

On failure: writes a structured clarification request to
~/Desktop/Inbox/Clarify/ and returns a HaltSignal.

Usage:
    from consistency_daemon.pre_gen_intercept import PreGenGate

    gate = PreGenGate()
    result = gate.check(
        proposed_action="Implement the deposit endpoint using PostgreSQL",
        context="The spec says to use CortexDB as the chunk store.",
        caller_id="antigravity",
    )
    if result.should_halt:
        # Do not proceed. Clarification has been written to Inbox/Clarify/
        return result.halt_reason
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("consistency-daemon.pre_gen_intercept")

# ── Constants ────────────────────────────────────────────────────────────────

CLARIFY_DIR = Path(os.environ.get("INBOX_CLARIFY_DIR", "~/Desktop/Inbox/Clarify")).expanduser()
CONFIDENCE_THRESHOLD = float(os.environ.get("PRE_GEN_CONFIDENCE_THRESHOLD", "0.70"))

# Patterns that indicate gap-filling rather than spec-derivation
GAP_FILL_PATTERNS = [
    r"\bI assume\b",
    r"\bI think\b",
    r"\bprobably\b",
    r"\bmight be\b",
    r"\bsomething like\b",
    r"\bnot specified\b",
    r"\bnot clear\b",
    r"\bnot sure\b",
    r"\bdefault to\b",
    r"\btypically\b",
    r"\busually\b",
]

# Patterns that hint at contradiction with established context
CONTRADICTION_TRIGGERS = [
    r"\bactually\b.{0,40}\bno\b",
    r"\bbut wait\b",
    r"\bon second thought\b",
    r"\binstead of\b.{0,40}\bI said\b",
]


# ── Result Types ─────────────────────────────────────────────────────────────

@dataclass
class InterceptResult:
    """Result of a pre-generation intercept check."""
    should_halt: bool
    confidence: float
    halt_reason: str = ""
    gap_fills_detected: list[str] = field(default_factory=list)
    contradictions_detected: list[str] = field(default_factory=list)
    clarify_file: str = ""  # Path to emitted clarification request, if any
    check_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])

    @property
    def passed(self) -> bool:
        return not self.should_halt


# ── Core Gate ────────────────────────────────────────────────────────────────

class PreGenGate:
    """Pre-generation intercept gate.

    Call check() before committing to any implementation direction.
    If should_halt is True, stop and surface the clarification request.
    """

    def __init__(
        self,
        clarify_dir: Path | None = None,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
    ) -> None:
        self._clarify_dir = clarify_dir or CLARIFY_DIR
        self._threshold = confidence_threshold
        self._clarify_dir.mkdir(parents=True, exist_ok=True)

    def check(
        self,
        proposed_action: str,
        context: str = "",
        caller_id: str = "agent",
        task_description: str = "",
    ) -> InterceptResult:
        """Check a proposed action before the agent commits to it.

        Args:
            proposed_action: What the agent is about to do.
            context:         The spec, task description, or established facts.
            caller_id:       Identifier for the calling agent.
            task_description: Original task intent, for clarification output.

        Returns:
            InterceptResult — check should_halt before proceeding.
        """
        gap_fills = self._scan_patterns(proposed_action, GAP_FILL_PATTERNS)
        contradictions = self._scan_patterns(proposed_action, CONTRADICTION_TRIGGERS)

        # Compute a simple confidence score:
        # Start at 1.0, subtract for each gap-fill and contradiction signal found
        confidence = 1.0
        confidence -= len(gap_fills) * 0.15
        confidence -= len(contradictions) * 0.25

        # Check derivability: if context is provided, confirm there's overlap
        if context and not self._is_derivable(proposed_action, context):
            confidence -= 0.20

        confidence = max(0.0, round(confidence, 3))
        should_halt = confidence < self._threshold

        halt_reason = ""
        clarify_file = ""

        if should_halt:
            halt_reason = self._build_halt_reason(
                proposed_action, gap_fills, contradictions, confidence
            )
            clarify_file = self._emit_clarification(
                proposed_action=proposed_action,
                halt_reason=halt_reason,
                gap_fills=gap_fills,
                contradictions=contradictions,
                confidence=confidence,
                caller_id=caller_id,
                task_description=task_description,
            )
            log.warning(
                "[PreGenGate] HALT — confidence=%.2f < threshold=%.2f | caller=%s | file=%s",
                confidence, self._threshold, caller_id, clarify_file,
            )
        else:
            log.debug(
                "[PreGenGate] PASS — confidence=%.2f | caller=%s",
                confidence, caller_id,
            )

        return InterceptResult(
            should_halt=should_halt,
            confidence=confidence,
            halt_reason=halt_reason,
            gap_fills_detected=gap_fills,
            contradictions_detected=contradictions,
            clarify_file=clarify_file,
        )

    # ── Private Helpers ──────────────────────────────────────────────────────

    def _scan_patterns(self, text: str, patterns: list[str]) -> list[str]:
        """Return list of matched snippets from the text."""
        hits: list[str] = []
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                hits.append(match.group(0)[:80])
        return hits

    def _is_derivable(self, proposed_action: str, context: str) -> bool:
        """Rough check: does the proposed action share key nouns/verbs with context?"""
        # Extract significant words (>4 chars) from context
        ctx_words = set(
            w.lower() for w in re.findall(r"\b\w{5,}\b", context)
        )
        action_words = set(
            w.lower() for w in re.findall(r"\b\w{5,}\b", proposed_action)
        )
        if not ctx_words:
            return True  # No context provided — cannot determine
        overlap = ctx_words & action_words
        return len(overlap) >= 2  # At least 2 shared significant terms

    def _build_halt_reason(
        self,
        proposed_action: str,
        gap_fills: list[str],
        contradictions: list[str],
        confidence: float,
    ) -> str:
        parts = [f"Confidence {confidence:.0%} is below threshold {self._threshold:.0%}."]
        if gap_fills:
            parts.append(f"Gap-fill language detected: {gap_fills[:3]}")
        if contradictions:
            parts.append(f"Contradiction signals detected: {contradictions[:2]}")
        parts.append("Do not proceed. Surface the specific unknowns and request clarification.")
        return " ".join(parts)

    def _emit_clarification(
        self,
        proposed_action: str,
        halt_reason: str,
        gap_fills: list[str],
        contradictions: list[str],
        confidence: float,
        caller_id: str,
        task_description: str,
    ) -> str:
        """Write a structured clarification request to the Clarify/ folder."""
        ts = time.strftime("%Y%m%d_%H%M%S")
        filename = f"clarify_{caller_id}_{ts}.json"
        filepath = self._clarify_dir / filename

        payload = {
            "type": "clarification_request",
            "timestamp": time.time(),
            "caller_id": caller_id,
            "confidence": confidence,
            "threshold": self._threshold,
            "task_description": task_description,
            "proposed_action": proposed_action,
            "halt_reason": halt_reason,
            "gap_fills_detected": gap_fills,
            "contradictions_detected": contradictions,
            "instructions": (
                "Operator: Please clarify the ambiguities above. "
                "Drop your clarification as a .txt file in ~/Desktop/Inbox/Input/ "
                "to unblock the agent."
            ),
        }

        filepath.write_text(json.dumps(payload, indent=2))
        return str(filepath)

"""uncertainty_organ.py — Live confidence map daemon.

Maintains a per-task confidence map. Each decision node is scored.
When any node drops below threshold, emits a structured JSON uncertainty
block to ~/Desktop/Inbox/Clarify/ instead of silently continuing.

This is a lightweight FastAPI service. Run it standalone or integrate
into the organism_embed.py managed fleet.

Endpoints:
    POST /task        — Register a new task context
    POST /decision    — Score a decision node, returns halt if low confidence
    GET  /map/{task_id} — View the full confidence map for a task
    GET  /health

Usage (embedded):
    from uncertainty_organ import UncertaintyOrgan
    organ = UncertaintyOrgan()
    result = organ.score_decision(
        task_id="task-abc",
        decision_key="implementation_approach",
        reasoning="I'll use PostgreSQL because the spec says CortexDB",
        supporting_context="Spec: use CortexDB as chunk store",
    )
    if result.should_halt:
        print(result.clarify_file)
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
from typing import Optional

try:
    from fastapi import FastAPI
    from pydantic import BaseModel
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

log = logging.getLogger("uncertainty-organ")

# ── Constants ─────────────────────────────────────────────────────────────────

CLARIFY_DIR = Path(os.environ.get("INBOX_CLARIFY_DIR", "~/Desktop/Inbox/Clarify")).expanduser()
UNCERTAINTY_THRESHOLD = float(os.environ.get("UNCERTAINTY_THRESHOLD", "0.70"))
PORT = int(os.environ.get("UNCERTAINTY_ORGAN_PORT", "8423"))


# ── Domain Models ─────────────────────────────────────────────────────────────

@dataclass
class DecisionNode:
    """A single scored decision within a task."""
    key: str
    reasoning: str
    supporting_context: str
    confidence: float
    timestamp: float = field(default_factory=time.time)
    node_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    halted: bool = False
    clarify_file: str = ""


@dataclass
class TaskMap:
    """Live confidence map for a running task."""
    task_id: str
    description: str
    nodes: list[DecisionNode] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @property
    def avg_confidence(self) -> float:
        if not self.nodes:
            return 1.0
        return round(sum(n.confidence for n in self.nodes) / len(self.nodes), 3)

    @property
    def min_confidence(self) -> float:
        if not self.nodes:
            return 1.0
        return round(min(n.confidence for n in self.nodes), 3)

    @property
    def halted_nodes(self) -> list[DecisionNode]:
        return [n for n in self.nodes if n.halted]

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "avg_confidence": self.avg_confidence,
            "min_confidence": self.min_confidence,
            "node_count": len(self.nodes),
            "halted_count": len(self.halted_nodes),
            "created_at": self.created_at,
            "nodes": [
                {
                    "key": n.key,
                    "confidence": n.confidence,
                    "halted": n.halted,
                    "reasoning": n.reasoning[:200],
                    "clarify_file": n.clarify_file,
                    "timestamp": n.timestamp,
                }
                for n in self.nodes
            ],
        }


@dataclass
class ScoreResult:
    """Result of scoring a decision node."""
    should_halt: bool
    confidence: float
    node_id: str
    clarify_file: str = ""
    message: str = ""


# ── Core Organ ────────────────────────────────────────────────────────────────

class UncertaintyOrgan:
    """Live confidence map organ.

    Scores individual decision nodes for a task.
    Emits clarification requests when confidence is too low.
    """

    def __init__(
        self,
        clarify_dir: Path | None = None,
        threshold: float = UNCERTAINTY_THRESHOLD,
    ) -> None:
        self._clarify_dir = clarify_dir or CLARIFY_DIR
        self._threshold = threshold
        self._tasks: dict[str, TaskMap] = {}
        self._clarify_dir.mkdir(parents=True, exist_ok=True)

    def register_task(self, task_id: str, description: str) -> TaskMap:
        """Register a new task context before scoring decisions."""
        task = TaskMap(task_id=task_id, description=description)
        self._tasks[task_id] = task
        log.info("[UncertaintyOrgan] Registered task: %s — %s", task_id, description[:60])
        return task

    def score_decision(
        self,
        task_id: str,
        decision_key: str,
        reasoning: str,
        supporting_context: str = "",
        caller_id: str = "agent",
    ) -> ScoreResult:
        """Score a decision node. Emits clarify file if confidence < threshold.

        Args:
            task_id:           Task this decision belongs to.
            decision_key:      Short name for this decision (e.g., "db_choice").
            reasoning:         The agent's reasoning for the decision.
            supporting_context: Facts/spec that support the decision.
            caller_id:         Agent making the decision.

        Returns:
            ScoreResult — check should_halt before proceeding.
        """
        task = self._tasks.get(task_id)
        if not task:
            task = self.register_task(task_id, f"Auto-registered for {caller_id}")

        confidence = self._score_reasoning(reasoning, supporting_context)
        should_halt = confidence < self._threshold

        clarify_file = ""
        if should_halt:
            clarify_file = self._emit_clarification(
                task=task,
                decision_key=decision_key,
                reasoning=reasoning,
                supporting_context=supporting_context,
                confidence=confidence,
                caller_id=caller_id,
            )

        node = DecisionNode(
            key=decision_key,
            reasoning=reasoning,
            supporting_context=supporting_context,
            confidence=confidence,
            halted=should_halt,
            clarify_file=clarify_file,
        )
        task.nodes.append(node)

        if should_halt:
            log.warning(
                "[UncertaintyOrgan] HALT — task=%s key=%s confidence=%.2f clarify=%s",
                task_id, decision_key, confidence, clarify_file,
            )
        else:
            log.debug(
                "[UncertaintyOrgan] PASS — task=%s key=%s confidence=%.2f",
                task_id, decision_key, confidence,
            )

        return ScoreResult(
            should_halt=should_halt,
            confidence=confidence,
            node_id=node.node_id,
            clarify_file=clarify_file,
            message=(
                f"Confidence {confidence:.0%} below threshold {self._threshold:.0%}. "
                f"Clarification written to {clarify_file}"
                if should_halt else f"Decision passed at {confidence:.0%} confidence."
            ),
        )

    def get_map(self, task_id: str) -> dict | None:
        task = self._tasks.get(task_id)
        return task.to_dict() if task else None

    def all_maps(self) -> list[dict]:
        return [t.to_dict() for t in self._tasks.values()]

    # ── Scoring Logic ──────────────────────────────────────────────────────

    _WEAK_SIGNALS = [
        r"\bI assume\b", r"\bI think\b", r"\bprobably\b", r"\bmight\b",
        r"\bmaybe\b", r"\bnot sure\b", r"\bnot specified\b", r"\bdefault to\b",
        r"\btypically\b", r"\busually\b", r"\bsomething like\b",
    ]

    _STRONG_SIGNALS = [
        r"\bthe spec says\b", r"\baccording to\b", r"\bexplicitly\b",
        r"\bverified\b", r"\bconfirmed\b", r"\bsource-read\b",
        r"\bdocumentation states\b", r"\bthe file shows\b",
    ]

    def _score_reasoning(self, reasoning: str, context: str) -> float:
        """Compute a confidence score from 0.0 to 1.0."""
        score = 0.70  # Neutral baseline

        # Weak language → lower confidence
        weak_hits = sum(
            1 for p in self._WEAK_SIGNALS
            if re.search(p, reasoning, re.IGNORECASE)
        )
        score -= weak_hits * 0.08

        # Strong grounding language → boost
        strong_hits = sum(
            1 for p in self._STRONG_SIGNALS
            if re.search(p, reasoning, re.IGNORECASE)
        )
        score += strong_hits * 0.08

        # Context-reasoning overlap boost
        if context:
            ctx_words = set(re.findall(r"\b\w{5,}\b", context.lower()))
            reasoning_words = set(re.findall(r"\b\w{5,}\b", reasoning.lower()))
            overlap = len(ctx_words & reasoning_words)
            score += min(overlap * 0.03, 0.20)

        return max(0.0, min(1.0, round(score, 3)))

    # ── Clarification Emission ─────────────────────────────────────────────

    def _emit_clarification(
        self,
        task: TaskMap,
        decision_key: str,
        reasoning: str,
        supporting_context: str,
        confidence: float,
        caller_id: str,
    ) -> str:
        ts = time.strftime("%Y%m%d_%H%M%S")
        filename = f"uncertainty_{task.task_id}_{decision_key}_{ts}.json"
        filepath = self._clarify_dir / filename

        payload = {
            "type": "uncertainty_block",
            "timestamp": time.time(),
            "task_id": task.task_id,
            "task_description": task.description,
            "decision_key": decision_key,
            "caller_id": caller_id,
            "confidence": confidence,
            "threshold": self._threshold,
            "reasoning_provided": reasoning,
            "supporting_context": supporting_context,
            "task_confidence_map": {
                "avg": task.avg_confidence,
                "min": task.min_confidence,
                "node_count": len(task.nodes),
                "previous_halts": len(task.halted_nodes),
            },
            "instructions": (
                "Operator: A decision node fell below confidence threshold. "
                "Review the reasoning above and drop a clarification .txt into "
                "~/Desktop/Inbox/Input/ to unblock the agent."
            ),
        }

        filepath.write_text(json.dumps(payload, indent=2))
        return str(filepath)


# ── FastAPI Server (optional) ─────────────────────────────────────────────────

if HAS_FASTAPI:
    app = FastAPI(title="Uncertainty Organ", version="1.0.0")
    _organ = UncertaintyOrgan()

    class RegisterTaskRequest(BaseModel):
        task_id: str
        description: str = ""

    class ScoreDecisionRequest(BaseModel):
        task_id: str
        decision_key: str
        reasoning: str
        supporting_context: str = ""
        caller_id: str = "agent"

    @app.post("/task")
    def register_task(req: RegisterTaskRequest):
        task = _organ.register_task(req.task_id, req.description)
        return {"task_id": task.task_id, "created_at": task.created_at}

    @app.post("/decision")
    def score_decision(req: ScoreDecisionRequest):
        result = _organ.score_decision(
            task_id=req.task_id,
            decision_key=req.decision_key,
            reasoning=req.reasoning,
            supporting_context=req.supporting_context,
            caller_id=req.caller_id,
        )
        return {
            "should_halt": result.should_halt,
            "confidence": result.confidence,
            "node_id": result.node_id,
            "clarify_file": result.clarify_file,
            "message": result.message,
        }

    @app.get("/map/{task_id}")
    def get_map(task_id: str):
        m = _organ.get_map(task_id)
        if m is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Task not found")
        return m

    @app.get("/maps")
    def all_maps():
        return _organ.all_maps()

    @app.get("/health")
    def health():
        return {"status": "ok", "organ": "uncertainty", "port": PORT}


def main():
    if not HAS_FASTAPI:
        print("FastAPI not installed. Run: pip install fastapi uvicorn")
        return
    uvicorn.run("uncertainty_organ:app", host="127.0.0.1", port=PORT, reload=False)


if __name__ == "__main__":
    main()

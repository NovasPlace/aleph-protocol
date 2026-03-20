// ═══════════════════════════════════════════════════════════════
// ADAPTIVE AGENT COGNITION — Cognitive Router
// Maps task signals to cognitive profiles
// The brain's dispatcher — decides HOW to think, not WHAT
// ═══════════════════════════════════════════════════════════════

import { createHash, randomUUID } from "crypto";
import { TaskSignalAnalyzer } from "../analyzer/signals.js";
import { LearnedRouter, extractFeatures } from "./learned-router.js";
import type { TrainingEntry } from "./learned-router.js";
import type {
  CognitiveRouter,
  CognitiveProfile,
  CognitiveStrategy,
  CognitionFeedback,
  EffortLevel,
  ModelAllocation,
  ModelTier,
  RouterDecision,
  RouterStats,
  TaskInput,
  TaskSignals,
  TrustTier,
} from "../types.js";

// ── Strategy Selection Matrix ──
// Maps signal combinations to cognitive strategies

interface StrategyRule {
  name: string;
  condition: (signals: TaskSignals) => boolean;
  strategy: CognitiveStrategy;
  priority: number; // Higher = checked first
}

// EVOLVE-BLOCK-START: strategy-rules-priorities
// Mutable: integer `priority` values on each rule. Do NOT change conditions or strategy values.
const STRATEGY_RULES: StrategyRule[] = [
  {
    name: "catastrophic-consensus",
    condition: (s) =>
      s.failureCost === "catastrophic" && s.mutatesState,
    strategy: "consensus",
    priority: 100,
  },
  {
    name: "critical-adversarial",
    condition: (s) =>
      s.failureCost === "critical" && s.chainDepth >= 3,
    strategy: "adversarial",
    priority: 95,
  },
  {
    name: "deep-chain-recursive",
    condition: (s) =>
      s.chainDepth >= 5 && s.inputComplexity >= 60,
    strategy: "recursive",
    priority: 107,
  },
  {
    name: "broad-parallel",
    condition: (s) =>
      s.domainBreadth >= 4 && s.latencySensitivity !== "realtime",
    strategy: "parallel",
    priority: 102,
  },
  {
    name: "multi-tool-parallel",
    condition: (s) =>
      s.toolRequirements.length >= 3,
    strategy: "parallel",
    priority: 80,
  },
  {
    name: "mutation-consensus",
    condition: (s) =>
      s.mutatesState && s.failureCost !== "negligible" && s.trustTier !== "EXTERNAL",
    strategy: "consensus",
    priority: 75,
  },
  {
    name: "moderate-linear",
    condition: (s) =>
      s.inputComplexity >= 30 && s.chainDepth >= 2,
    strategy: "linear",
    priority: 50,
  },
  {
    name: "novel-linear",
    condition: (s) =>
      s.novelty === "unprecedented" || s.novelty === "novel",
    strategy: "linear",
    priority: 45,
  },
  {
    name: "simple-snap",
    condition: (s) =>
      s.inputComplexity < 25 && s.chainDepth <= 1 && s.failureCost === "negligible",
    strategy: "snap",
    priority: 40,
  },
  {
    name: "realtime-snap",
    condition: (s) =>
      s.latencySensitivity === "realtime",
    strategy: "snap",
    priority: 60,
  },
  // Default fallback
  {
    name: "default-linear",
    condition: () => true,
    strategy: "linear",
    priority: 0,
  },
];
// EVOLVE-BLOCK-END

// ── Effort Mapping ──

// EVOLVE-BLOCK-START: effort-thresholds
// Mutable: numeric breakpoints (80, 60, 35, 15) and bump constants (+2, +1, +1).
// Do NOT change control flow, return types, or the trust floor logic.
function computeEffort(signals: TaskSignals, strategy: CognitiveStrategy): EffortLevel {
  // Trust tier floors
  const trustFloors: Record<TrustTier, number> = {
    GENESIS: 5,   // min high
    ORGAN: 3,     // min medium
    PIPELINE: 2,  // min low
    API: 1,       // min minimal
    EXTERNAL: 0,  // no floor
  };

  // Base effort from complexity
  let effortScore = 0;

  if (signals.inputComplexity >= 80) effortScore = 4;
  else if (signals.inputComplexity >= 71) effortScore = 3;
  else if (signals.inputComplexity >= 29) effortScore = 2;
  else if (signals.inputComplexity >= 15) effortScore = 1;
  else effortScore = 0;

  // Bump for high failure cost
  if (signals.failureCost === "catastrophic") effortScore += 2;
  else if (signals.failureCost === "critical") effortScore += 1;

  // Bump for deep chains
  if (signals.chainDepth >= 5) effortScore += 1;

  // Strategy modifiers
  if (strategy === "consensus" || strategy === "adversarial") effortScore += 1;
  if (strategy === "snap") effortScore = Math.min(effortScore, 1);

  // Reduce for latency pressure
  if (signals.latencySensitivity === "realtime") effortScore -= 3;
  else if (signals.latencySensitivity === "high") effortScore -= 1;

  // Apply trust floor
  const floor = trustFloors[signals.trustTier] ?? 0;
  effortScore = Math.max(effortScore, floor);

  // Clamp and map
  effortScore = Math.max(0, Math.min(4, effortScore));
  const levels: EffortLevel[] = ["minimal", "low", "medium", "high", "max"];
  return levels[effortScore];
}
// EVOLVE-BLOCK-END

// ── Model Selection ──

function selectModel(
  effort: EffortLevel,
  strategy: CognitiveStrategy,
  signals: TaskSignals,
  role: "primary" | "secondary" = "primary"
): ModelAllocation {
  // Determine model tier
  let tier: ModelTier = "standard";

  if (effort === "max" || effort === "high") tier = "frontier";
  else if (effort === "minimal" || strategy === "snap") tier = "fast";

  // Secondary models in consensus/adversarial can be cheaper
  if (role === "secondary") {
    if (tier === "frontier") tier = "standard";
    else tier = "fast";
  }

  // Map tier to concrete models
  const modelMap: Record<ModelTier, ModelAllocation> = {
    fast: {
      tier: "fast",
      provider: "claude",
      model: "claude-haiku-4-5",
      effort: "low",
      thinking: "disabled",
      temperature: 0.3,
    },
    standard: {
      tier: "standard",
      provider: "claude",
      model: "claude-sonnet-4-6",
      effort: mapEffortToAPI(effort),
      thinking: "adaptive",
      temperature: 0.4,
    },
    frontier: {
      tier: "frontier",
      provider: "claude",
      model: "claude-opus-4-6",
      effort: mapEffortToAPI(effort),
      thinking: "adaptive",
      temperature: 0.5,
    },
  };

  return modelMap[tier];
}

function mapEffortToAPI(effort: EffortLevel): EffortLevel {
  // Our effort levels map 1:1 to Claude's effort parameter
  // except "minimal" which maps to "low" on the API
  if (effort === "minimal") return "low";
  return effort;
}

// ── Token Budget Estimation ──

function estimateTokenBudget(
  effort: EffortLevel,
  strategy: CognitiveStrategy,
  signals: TaskSignals
): number {
  const baseBudgets: Record<EffortLevel, number> = {
    minimal: 500,
    low: 2_000,
    medium: 8_000,
    high: 32_000,
    max: 128_000,
  };

  let budget = baseBudgets[effort];

  // Strategy multipliers
  const strategyMultipliers: Record<CognitiveStrategy, number> = {
    snap: 0.25,
    linear: 1.0,
    parallel: 1.5,      // Multiple calls
    consensus: 2.5,     // Multiple agents + synthesis
    recursive: 2.0,     // Multiple sub-calls
    adversarial: 3.0,   // Generate + critique + iterate
  };

  budget *= strategyMultipliers[strategy];

  // Domain breadth multiplier
  if (signals.domainBreadth >= 4) budget *= 1.5;

  return Math.round(budget);
}

// ── Time Budget Estimation ──

function estimateTimeBudget(
  effort: EffortLevel,
  strategy: CognitiveStrategy,
  signals: TaskSignals
): number {
  if (signals.latencySensitivity === "realtime") return 3_000;
  if (signals.latencySensitivity === "high") return 10_000;

  const baseTimes: Record<EffortLevel, number> = {
    minimal: 2_000,
    low: 10_000,
    medium: 30_000,
    high: 120_000,
    max: 600_000,
  };

  let time = baseTimes[effort];

  if (strategy === "consensus" || strategy === "adversarial") time *= 2;
  if (strategy === "parallel") time *= 0.7; // Parallel is faster

  return Math.round(time);
}

// ── The Router ──

export class AdaptiveCognitiveRouter implements CognitiveRouter {
  private analyzer: TaskSignalAnalyzer;
  private learnedRouter: LearnedRouter;
  private decisions: RouterDecision[] = [];
  private feedback: CognitionFeedback[] = [];

  constructor(learnedRouter?: LearnedRouter) {
    this.analyzer = new TaskSignalAnalyzer();
    this.learnedRouter = learnedRouter ?? new LearnedRouter();
  }

  async route(task: TaskInput): Promise<RouterDecision> {
    const start = Date.now();

    // Phase 1: Extract signals
    const signals = this.analyzer.analyze(task);

    // Phase 2: Heuristic strategy selection
    const heuristicStrategy = this.selectStrategy(signals);
    const heuristicEffort = computeEffort(signals, heuristicStrategy);

    // Phase 3: Learned routing (if sufficient data)
    let strategy = heuristicStrategy;
    let effort = heuristicEffort;
    let routingMode: "heuristic" | "learned" | "hybrid" = "heuristic";
    let learnedConfidence = 0;

    if (this.learnedRouter.hasEnoughData) {
      const prediction = this.learnedRouter.predict(signals);
      learnedConfidence = prediction.confidence;

      if (prediction.confidence >= 70) {
        // High confidence: use learned routing
        strategy = prediction.strategy;
        effort = prediction.effort;
        routingMode = "learned";
      } else if (prediction.confidence >= 50) {
        // Medium confidence: learned strategy, heuristic effort
        strategy = prediction.strategy;
        routingMode = "hybrid";
      }
      // Below 50%: stay with heuristic
    }

    // Phase 4: Build cognitive profile
    const profile = this.buildProfile(task, signals, strategy, effort);

    // Phase 5: Compute routing confidence
    const confidence = this.computeConfidence(signals, strategy, effort);

    const decision: RouterDecision = {
      taskId: task.id,
      signals,
      profile,
      confidence,
      decidedAt: new Date(),
      routingLatency: Date.now() - start,
      routingMode,
      learnedConfidence,
    };

    this.decisions.push(decision);
    return decision;
  }

  private selectStrategy(signals: TaskSignals): CognitiveStrategy {
    // Sort rules by priority (highest first)
    const sorted = [...STRATEGY_RULES].sort(
      (a, b) => b.priority - a.priority
    );

    for (const rule of sorted) {
      if (rule.condition(signals)) {
        return rule.strategy;
      }
    }

    return "linear"; // Should never reach here
  }

  private buildProfile(
    task: TaskInput,
    signals: TaskSignals,
    strategy: CognitiveStrategy,
    effort: EffortLevel
  ): CognitiveProfile {
    const primaryModel = selectModel(effort, strategy, signals, "primary");
    const needsSecondary =
      strategy === "consensus" ||
      strategy === "adversarial" ||
      strategy === "parallel";
    const secondaryModel = needsSecondary
      ? selectModel(effort, strategy, signals, "secondary")
      : undefined;

    const tokenBudget = estimateTokenBudget(effort, strategy, signals);
    const timeBudget = estimateTimeBudget(effort, strategy, signals);

    return {
      id: randomUUID(),
      label: this.generateLabel(strategy, effort, signals),
      strategy,
      effort,
      activateOrgans: signals.toolRequirements,
      primaryModel,
      secondaryModel,
      requireConsensus:
        strategy === "consensus" ||
        (signals.mutatesState && signals.failureCost !== "negligible"),
      autoCommitThreshold: this.computeAutoCommitThreshold(signals),
      timeBudget,
      tokenBudget,
      trackProvenance:
        signals.trustTier === "GENESIS" ||
        signals.trustTier === "ORGAN" ||
        signals.mutatesState,
      reasoning: this.explainDecision(signals, strategy, effort),
    };
  }

  private generateLabel(
    strategy: CognitiveStrategy,
    effort: EffortLevel,
    signals: TaskSignals
  ): string {
    const strategyLabels: Record<CognitiveStrategy, string> = {
      snap: "SNAP",
      linear: "LINEAR",
      parallel: "PARALLEL",
      consensus: "CONSENSUS",
      recursive: "RECURSIVE",
      adversarial: "ADVERSARIAL",
    };
    return `${strategyLabels[strategy]}/${effort.toUpperCase()} [${signals.trustTier}]`;
  }

  private explainDecision(
    signals: TaskSignals,
    strategy: CognitiveStrategy,
    effort: EffortLevel
  ): string {
    const parts: string[] = [];

    parts.push(`Strategy: ${strategy} (complexity=${signals.inputComplexity}, depth=${signals.chainDepth})`);
    parts.push(`Effort: ${effort} (failure_cost=${signals.failureCost}, trust=${signals.trustTier})`);

    if (signals.mutatesState) parts.push("State mutation detected — consensus recommended");
    if (signals.toolRequirements.length > 0)
      parts.push(`Tools: ${signals.toolRequirements.join(", ")}`);
    if (signals.latencySensitivity === "realtime")
      parts.push("Realtime constraint — capping effort");
    if (signals.novelty === "unprecedented")
      parts.push("Unprecedented task — elevated reasoning");

    return parts.join(" | ");
  }

  private computeConfidence(
    signals: TaskSignals,
    strategy: CognitiveStrategy,
    effort: EffortLevel
  ): number {
    let confidence = 70; // Base confidence in routing

    // Routine tasks = high confidence in routing
    if (signals.novelty === "routine") confidence += 15;
    if (signals.novelty === "unprecedented") confidence -= 20;

    // Clear signal alignment = higher confidence
    if (signals.inputComplexity > 80 && effort === "max") confidence += 10;
    if (signals.inputComplexity < 20 && effort === "minimal") confidence += 10;

    // Mixed signals = lower confidence
    if (
      signals.failureCost === "catastrophic" &&
      signals.latencySensitivity === "realtime"
    ) {
      confidence -= 15; // Conflicting requirements
    }

    // Feedback-adjusted (v0: simple, v1: ML-based)
    const relevantFeedback = this.feedback.filter(
      (f) => f.outcome !== "success" && f.strategyAssessment === "wrong"
    );
    if (relevantFeedback.length > 5) confidence -= 10;

    return Math.max(20, Math.min(98, confidence));
  }

  private computeAutoCommitThreshold(signals: TaskSignals): number {
    // Higher threshold = more cautious
    const thresholds: Record<string, number> = {
      catastrophic: 99,
      critical: 95,
      costly: 85,
      annoying: 70,
      negligible: 50,
    };
    return thresholds[signals.failureCost] ?? 80;
  }

  // ── Feedback Loop ──

  async recordFeedback(feedback: CognitionFeedback): Promise<void> {
    this.feedback.push(feedback);

    // Feed training data to the learned router.
    // Find the corresponding decision by ID.
    const decision = this.decisions.find(
      (d) => d.taskId === feedback.decisionId
    );
    if (decision) {
      const entry: TrainingEntry = {
        features: extractFeatures(decision.signals),
        strategy: decision.profile.strategy,
        effort: decision.profile.effort,
        outcome: feedback.outcome,
        timestamp: decision.decidedAt.getTime(),
      };
      this.learnedRouter.addEntry(entry);
    }
  }

  // ── Stats ──

  getStats(): RouterStats {
    const byStrategy: Record<CognitiveStrategy, number> = {
      snap: 0, linear: 0, parallel: 0,
      consensus: 0, recursive: 0, adversarial: 0,
    };
    const byEffort: Record<EffortLevel, number> = {
      minimal: 0, low: 0, medium: 0, high: 0, max: 0,
    };
    const outcomeRates: Record<string, number> = {
      success: 0, partial: 0, failure: 0, timeout: 0,
    };

    let totalConfidence = 0;

    for (const d of this.decisions) {
      byStrategy[d.profile.strategy]++;
      byEffort[d.profile.effort]++;
      totalConfidence += d.confidence;
    }

    for (const f of this.feedback) {
      outcomeRates[f.outcome]++;
    }

    return {
      totalDecisions: this.decisions.length,
      byStrategy,
      byEffort,
      averageConfidence:
        this.decisions.length > 0
          ? Math.round(totalConfidence / this.decisions.length)
          : 0,
      feedbackCount: this.feedback.length,
      outcomeRates,
    };
  }
}
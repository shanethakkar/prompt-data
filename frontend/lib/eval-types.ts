// Types for the committed eval artifacts in content/ (produced by eval/run_*.py).
import type { AnswerResult, Assumptions, Cell, Clarification, Confidence } from "@/lib/types";

export interface ReliabilityBin {
  lower: number;
  upper: number;
  predicted: number;
  observed: number;
  count: number;
}

export interface EvalResults {
  metadata: {
    model: string;
    k: number;
    n_questions: number;
    n_answered: number;
    estimated_cost_usd: number;
    eval_peak_rss_mb: number;
  };
  accuracy: {
    execution_accuracy: number;
    answered_accuracy: number;
    clarification_rate: number;
    semantic_error_rate: number;
  };
  confidently_wrong: {
    threshold: number;
    with_trust: number;
    baseline: number;
    absolute_reduction: number;
    relative_reduction: number;
    sweep: Record<string, { with_trust: number; baseline: number }>;
  };
  calibration: {
    shipped_isotonic: boolean;
    test_n: number;
    brier_raw: number;
    brier_calibrated: number;
    ece_raw: number;
    ece_calibrated: number;
    reliability_shipped: ReliabilityBin[];
  };
  clarification: ClarificationScores;
  records: { latency_ms: number }[];
}

export interface ClarificationScores {
  precision: number;
  recall: number;
  over_ask_rate: number;
  true_positive: number;
  false_positive: number;
  false_negative: number;
}

export interface TrapResults {
  metadata: { model: string; k: number; n_items: number; estimated_cost_usd: number };
  confidently_answered_on_traps: {
    n_traps: number;
    n_clear: number;
    baseline_confidently_answered: number;
    trust_confidently_answered: number;
    absolute_reduction: number;
    relative_reduction: number;
    over_decline_rate: number;
    by_category: Record<string, number>;
  };
  mean_confidence_when_answered: { traps: number | null; clear: number | null };
  clarification: ClarificationScores;
}

export interface GalleryCard {
  id: string;
  category: string;
  question: string;
  takeaway: string;
  naive: {
    sql: string;
    columns: string[];
    rows: Cell[][];
    row_count: number;
    error: string | null;
  };
  verity: {
    kind: "answer" | "clarification";
    clarification?: Clarification;
    answer?: AnswerResult | null;
    assumptions?: Assumptions | null;
    confidence?: Confidence | null;
  };
}

export interface GalleryData {
  model: string;
  generated: string;
  estimated_cost_usd: number;
  cards: GalleryCard[];
}

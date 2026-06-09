// Mirrors the backend payload shapes (TrustedResponse / StageEvent) from
// backend/app/main.py and pipeline/answer.py.

export type Cell = string | number | boolean | null;

export interface AnswerResult {
  question: string;
  explanation: string;
  sql: string;
  columns: string[];
  rows: Cell[][];
  row_count: number;
  chart_type: "stat" | "bar" | "line" | "table" | "none";
  self_correction_fired: boolean;
  attempts: number;
  timed_out: boolean;
  error: string | null;
}

export interface Assumptions {
  term_mappings: string[];
  tables: string[];
  joins: string[];
  filters: string[];
  group_by: string[];
  row_limit: number | null;
}

export interface Confidence {
  score: number;
  raw: number;
  agreement: number;
  samples: number;
  self_correction_fired: boolean;
  calibrated: boolean;
  explanation: string;
}

export interface Clarification {
  question: string;
  options: string[];
  dimensions: string[];
}

export type StageEvent =
  | { type: "stage"; name: string; label: string }
  | { type: "clarification"; clarification: Clarification }
  | {
      type: "answer";
      answer: AnswerResult;
      assumptions: Assumptions | null;
      confidence: Confidence | null;
    };

export interface Stage {
  name: string;
  label: string;
  done: boolean;
}

export interface Turn {
  id: string;
  question: string;
  stages: Stage[];
  status: "streaming" | "done" | "error";
  kind?: "answer" | "clarification";
  answer?: AnswerResult;
  assumptions?: Assumptions | null;
  confidence?: Confidence | null;
  clarification?: Clarification;
  error?: string;
}

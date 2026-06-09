import type { Metadata } from "next";
import evalRaw from "@/content/eval_results.json";
import trapRaw from "@/content/trap_results.json";
import type { EvalResults, TrapResults } from "@/lib/eval-types";
import { PageHeader } from "@/components/site/page-header";
import { MetricCard, PercentBars, ReliabilityDiagram } from "@/components/evals/charts";

export const metadata: Metadata = {
  title: "Evals — Verity",
  description: "Measured trust metrics: accuracy, calibration, and the confidently-wrong reduction.",
};

const evals = evalRaw as unknown as EvalResults;
const traps = trapRaw as unknown as TrapResults;

const pct = (v: number) => `${Math.round(v * 100)}%`;

function median(xs: number[]): number {
  if (xs.length === 0) return 0;
  const s = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

function Section({
  title,
  caption,
  children,
}: {
  title: string;
  caption?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-10">
      <h2 className="text-lg font-medium text-foreground">{title}</h2>
      {caption && <p className="mt-1 text-sm text-muted-foreground">{caption}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

export default function EvalsPage() {
  const cw = traps.confidently_answered_on_traps;
  const medianLatency = median(evals.records.map((r) => r.latency_ms));
  const catBars = Object.entries(cw.by_category)
    .sort((a, b) => b[1] - a[1])
    .map(([label, value]) => ({ label, value, tone: "warn" as const }));

  return (
    <div className="mx-auto max-w-3xl px-5 py-12">
      <PageHeader
        eyebrow="Measured, not asserted"
        title="Evals"
        lede="Every number here is produced by a reproducible offline harness and committed to the repo. Results are a pinned subset, not a leaderboard run, and are labelled with their sample size."
      />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCard label="Exec accuracy" value={pct(evals.accuracy.execution_accuracy)} sub={`BIRD, n=${evals.metadata.n_questions}`} />
        <MetricCard label="Semantic-error" value={pct(evals.accuracy.semantic_error_rate)} sub="executed but wrong" />
        <MetricCard label="Calibration (ECE)" value={evals.calibration.ece_calibrated.toFixed(2)} sub={`from ${evals.calibration.ece_raw.toFixed(2)} raw`} />
        <MetricCard label="Confidently-wrong" value={pct(cw.trust_confidently_answered)} sub={`from ${pct(cw.baseline_confidently_answered)} baseline`} />
      </div>

      <Section
        title="The trust layer's signature: confidently-wrong reduction"
        caption={`On ${cw.n_traps} questions that should not be answered (ambiguous, unanswerable, prompt-injection), a no-trust baseline answers confidently every time. Verity declines or clarifies most, and over-declines none of the ${cw.n_clear} clear controls.`}
      >
        <PercentBars
          bars={[
            { label: "Baseline (no trust)", value: cw.baseline_confidently_answered, tone: "warn" },
            { label: "Verity", value: cw.trust_confidently_answered, tone: "primary" },
            { label: "Over-decline (clear)", value: cw.over_decline_rate, tone: "muted" },
          ]}
        />
      </Section>

      <Section
        title="Calibration"
        caption={`Self-consistency confidence is over-confident raw; isotonic calibration on a held-out split (n=${evals.calibration.test_n}) makes it track observed accuracy. Points should sit near the diagonal.`}
      >
        <div className="flex flex-col items-start gap-6 sm:flex-row sm:items-center">
          <ReliabilityDiagram bins={evals.calibration.reliability_shipped} />
          <div className="flex-1">
            <PercentBars
              bars={[
                { label: "ECE (raw)", value: evals.calibration.ece_raw, tone: "warn" },
                { label: "ECE (calibrated)", value: evals.calibration.ece_calibrated, tone: "primary" },
                { label: "Brier (raw)", value: evals.calibration.brier_raw, tone: "muted" },
                { label: "Brier (calibrated)", value: evals.calibration.brier_calibrated, tone: "primary" },
              ]}
            />
            <p className="mt-2 text-xs text-muted-foreground">Lower is better.</p>
          </div>
        </div>
      </Section>

      <Section
        title="Where the trust layer still slips"
        caption="Share of trap questions Verity answered anyway, by category. Honest: it is strong on metric and time ambiguity, weaker on grain and entity, and the ambiguity gate is not an injection detector (the SELECT-only validator handles that)."
      >
        <PercentBars bars={catBars} />
      </Section>

      <Section title="Clarification quality" caption="Against the hand-labelled ambiguity set: it never over-asks on clear questions.">
        <div className="grid grid-cols-3 gap-3">
          <MetricCard label="Precision" value={traps.clarification.precision.toFixed(2)} />
          <MetricCard label="Recall" value={traps.clarification.recall.toFixed(2)} />
          <MetricCard label="Over-ask" value={traps.clarification.over_ask_rate.toFixed(2)} />
        </div>
      </Section>

      <Section title="Cost and latency" caption="Single model tier in this run; routing across tiers is future work.">
        <div className="grid grid-cols-3 gap-3">
          <MetricCard label="Model" value={evals.metadata.model.replace("claude-", "")} />
          <MetricCard label="Median latency" value={`${(medianLatency / 1000).toFixed(1)}s`} sub="per question, K-sampled" />
          <MetricCard label="Eval peak RSS" value={`${evals.metadata.eval_peak_rss_mb} MB`} sub="under the 4 GB ceiling" />
        </div>
      </Section>

      <p className="mt-10 text-xs text-muted-foreground">
        Source: BIRD dev (pinned {evals.metadata.n_questions}-question subset) on {evals.metadata.model}, K={evals.metadata.k}; trap eval on {cw.n_traps + cw.n_clear} curated Olist questions. Numbers regenerate from <code className="font-mono">eval/run_bird.py</code> and <code className="font-mono">eval/run_traps.py</code>.
      </p>
    </div>
  );
}

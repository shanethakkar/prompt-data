import type { Metadata } from "next";
import Link from "next/link";
import evalRaw from "@/content/eval_results.json";
import trapRaw from "@/content/trap_results.json";
import type { EvalResults, TrapResults } from "@/lib/eval-types";
import { PageHeader } from "@/components/site/page-header";

export const metadata: Metadata = {
  title: "Methodology — Verity",
  description: "How Verity earns trust: ambiguity detection, surfaced assumptions, calibrated confidence, and measured honesty.",
};

const evals = evalRaw as unknown as EvalResults;
const traps = trapRaw as unknown as TrapResults;
const pct = (v: number) => `${Math.round(v * 100)}%`;

function Behavior({ n, title, children }: { n: string; title: string; children: React.ReactNode }) {
  return (
    <div className="border-t border-border/60 py-6">
      <div className="flex items-baseline gap-3">
        <span className="font-mono text-sm text-primary">{n}</span>
        <h2 className="text-lg font-medium text-foreground">{title}</h2>
      </div>
      <div className="mt-2 space-y-3 text-[15px] leading-relaxed text-muted-foreground">{children}</div>
    </div>
  );
}

export default function MethodologyPage() {
  const cw = traps.confidently_answered_on_traps;
  return (
    <div className="mx-auto max-w-2xl px-5 py-12">
      <PageHeader
        eyebrow="How it works"
        title="Methodology"
        lede="Generating SQL is the easy part. The hard part is knowing when to trust the answer. Verity is built around four behaviors, and every claim it makes about its own quality is measured, never asserted."
      />

      <Behavior n="01" title="It asks instead of guessing">
        <p>
          Before answering, Verity classifies a question for ambiguity: an undefined metric (&ldquo;top&rdquo;
          by what?), a vague time window (&ldquo;last quarter&rdquo;), an unclear entity or grain, or a request
          for data that simply is not in the schema. When a question is genuinely underspecified, it returns a
          short clarifying question with tappable options instead of guessing.
        </p>
        <p>
          The trade-off is real: ask too much and it is annoying; ask too little and it guesses wrong. On a
          hand-labelled set it hits <strong className="text-foreground">{traps.clarification.precision.toFixed(2)} precision</strong> and{" "}
          <strong className="text-foreground">{traps.clarification.recall.toFixed(2)} recall</strong> with{" "}
          <strong className="text-foreground">zero over-asking</strong> on clear questions.
        </p>
      </Behavior>

      <Behavior n="02" title="It shows its work">
        <p>
          When it proceeds, Verity surfaces the concrete assumptions the query embodies, extracted directly from
          the SQL it actually ran: which tables and joins, which filters, the aggregation grain, the row cap, and
          which business terms it resolved (for example, &ldquo;revenue&rdquo; to the sum of item prices, or &ldquo;a
          customer&rdquo; to the unique customer id rather than the per-order id). These cannot drift from the query
          because they are read back out of it.
        </p>
      </Behavior>

      <Behavior n="03" title="Its confidence is calibrated">
        <p>
          Verity samples several candidate queries and measures how often they agree. On its own this signal is
          over-confident, so a calibration map fit offline (isotonic regression on a held-out split) rescales it to
          match observed accuracy. That took calibration error from{" "}
          <strong className="text-foreground">{evals.calibration.ece_raw.toFixed(2)}</strong> down to{" "}
          <strong className="text-foreground">{evals.calibration.ece_calibrated.toFixed(2)}</strong> — so when Verity
          says it is 70% sure, it is roughly right 70% of the time. The map is fit offline and loaded statically;
          nothing is fit at request time.
        </p>
      </Behavior>

      <Behavior n="04" title="Its quality is measured">
        <p>
          An offline harness runs the{" "}
          <Link href="/evals" className="text-primary underline-offset-4 hover:underline">eval suite</Link>{" "}
          against BIRD (a hard public text-to-SQL benchmark) and a curated trap set. The headline result: on
          questions that should not be confidently answered, a no-trust baseline answers{" "}
          <strong className="text-foreground">{pct(cw.baseline_confidently_answered)}</strong> of them; Verity
          answers only <strong className="text-foreground">{pct(cw.trust_confidently_answered)}</strong> — clarifying
          or declining the rest — while still answering every clear control. Execution accuracy on the BIRD subset
          (n={evals.metadata.n_questions}) is <strong className="text-foreground">{pct(evals.accuracy.execution_accuracy)}</strong>.
        </p>
      </Behavior>

      <div className="border-t border-border/60 py-6">
        <h2 className="text-lg font-medium text-foreground">Under the hood</h2>
        <p className="mt-2 text-[15px] leading-relaxed text-muted-foreground">
          A read-only, SELECT-only sandbox parses every generated query and rejects anything that is not a single
          read-only statement before it reaches the database — the real backstop against prompt injection. The
          server runs LLM inference via the Anthropic API and stays well under a 4 GB memory budget. The numbers on
          this site are produced by a reproducible batch job and committed to the repository.
        </p>
      </div>
    </div>
  );
}

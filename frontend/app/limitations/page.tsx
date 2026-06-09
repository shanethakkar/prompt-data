import type { Metadata } from "next";
import evalRaw from "@/content/eval_results.json";
import trapRaw from "@/content/trap_results.json";
import type { EvalResults, TrapResults } from "@/lib/eval-types";
import { PageHeader } from "@/components/site/page-header";

export const metadata: Metadata = {
  title: "Limitations — Prompt Data",
  description: "The honest page: what Prompt Data cannot do, where it is weakest, and what is still measured but imperfect.",
};

const evals = evalRaw as unknown as EvalResults;
const traps = trapRaw as unknown as TrapResults;
const pct = (v: number) => `${Math.round(v * 100)}%`;

function Limit({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-t border-border/60 py-6">
      <h2 className="text-base font-medium text-foreground">{title}</h2>
      <p className="mt-2 text-[15px] leading-relaxed text-muted-foreground">{children}</p>
    </div>
  );
}

export default function LimitationsPage() {
  const cw = traps.confidently_answered_on_traps;
  return (
    <div className="mx-auto max-w-2xl px-5 py-12">
      <PageHeader
        eyebrow="The honest page"
        title="Limitations"
        lede="A trust product that hides its weaknesses is not trustworthy. Here is what Prompt Data does not do well, stated plainly."
      />

      <Limit title="It can still be confidently wrong">
        <p>
          Execution accuracy on the benchmark subset is about {pct(evals.accuracy.execution_accuracy)}, so a real
          fraction of answered questions return the wrong result. The trust layer reduces how often those are shown
          confidently; it does not make them correct. A query that runs cleanly and that the model agrees with
          itself on can still answer the wrong question.
        </p>
      </Limit>

      <Limit title="Confidence is well-calibrated but coarse">
        <p>
          Confidence comes from how often several sampled queries agree. On a strong model they usually agree, so
          the signal is blunt — it sorts answers into roughly &ldquo;likely right&rdquo; and &ldquo;shaky&rdquo;
          rather than finely ranking each one. Calibration makes the number trustworthy as a probability (it tracks
          accuracy), but it cannot manufacture resolution the underlying signal lacks.
        </p>
      </Limit>

      <Limit title="The numbers are a pinned subset, not a leaderboard">
        <p>
          Accuracy and calibration are measured on a fixed {evals.metadata.n_questions}-question slice of BIRD with
          one model, and calibration is evaluated on a small held-out split (n={evals.calibration.test_n}). They are
          honest and reproducible, but they carry real sampling noise and should not be read as full-benchmark or
          state-of-the-art figures.
        </p>
      </Limit>

      <Limit title="Ambiguity detection misses some cases">
        <p>
          It is strong on undefined metrics and vague time windows, but weaker on aggregation grain and entity
          ambiguity — on the trap set it still answered {pct(cw.trust_confidently_answered)} of questions it
          arguably should have clarified. Improving the depth of ambiguity detection is future work.
        </p>
      </Limit>

      <Limit title="Read-only is guaranteed; semantic appropriateness is not">
        <p>
          A SELECT-only validator parses every query and guarantees no write or schema change ever reaches the
          database, which is also the backstop against prompt injection. What it cannot judge is whether a read is
          the <em>right</em> read. The ambiguity gate is not an injection detector — the validator is — so an
          adversarial prompt that still produces a valid SELECT will execute (safely), and the trust layer rather
          than the sandbox is what flags it.
        </p>
      </Limit>

      <Limit title="One model, one database, English only">
        <p>
          The live demo runs against the Olist e-commerce database with a single model tier and English questions.
          Model routing across tiers, bring-your-own-database, and broader language coverage are out of scope for
          this version.
        </p>
      </Limit>
    </div>
  );
}

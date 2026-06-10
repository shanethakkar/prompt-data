"use client";

import { useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { Database } from "lucide-react";
import { useAsk } from "@/lib/use-ask";
import type { Dataset, UploadResponse } from "@/lib/schema-types";
import { QuestionInput } from "@/components/ask/question-input";
import { StageProgress } from "@/components/ask/stage-progress";
import { AnswerCard } from "@/components/ask/answer-card";
import { ClarificationCard } from "@/components/ask/clarification-card";
import { SchemaDrawer } from "@/components/ask/schema-drawer";

function CustomBanner({ filename }: { filename: string | null }) {
  return (
    <div className="mb-3 flex items-center gap-2 rounded-lg border border-primary/30 bg-primary/[0.06] px-3 py-2 text-xs text-muted-foreground">
      <Database className="size-3.5 shrink-0 text-primary" />
      <span>
        Querying <span className="font-medium text-foreground">{filename ?? "your upload"}</span>.
        Confidence is uncalibrated for custom data.
      </span>
    </div>
  );
}

export default function AskPage() {
  const { turns, isStreaming, submit, clarify, reset } = useAsk();
  const [dataset, setDataset] = useState<Dataset>({ kind: "olist" });
  const reduce = useReducedMotion();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "end" });
  }, [turns, reduce]);

  const empty = turns.length === 0;
  const custom = dataset.kind === "custom";
  const session = dataset.kind === "custom" ? dataset.session : undefined;
  const placeholder = custom ? "Ask your data anything…" : "Ask the Olist database anything…";

  // Switching datasets starts a fresh conversation (the thread can't mix sources).
  function handleUpload(r: UploadResponse) {
    setDataset({ kind: "custom", session: r.session, filename: r.filename, tables: r.tables });
    reset();
  }
  function handleUseOlist() {
    setDataset({ kind: "olist" });
    reset();
  }

  return (
    <div className="mx-auto flex min-h-[calc(100vh-3.5rem)] max-w-3xl flex-col px-5">
      {empty ? (
        <div className="flex flex-1 flex-col justify-center py-16">
          <motion.div
            initial={reduce ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className="mb-8"
          >
            <h1 className="text-balance text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
              Ask in plain English. <span className="text-primary">Trust the answer.</span>
            </h1>
            <p className="mt-3 max-w-xl text-pretty text-[15px] leading-relaxed text-muted-foreground">
              {custom
                ? "Querying your uploaded data. Prompt Data writes the SQL, surfaces its assumptions, and asks when a question is ambiguous. Confidence is uncalibrated for custom datasets."
                : "Prompt Data turns questions about the Olist e-commerce database into SQL, surfaces the assumptions it made, asks when a question is ambiguous instead of guessing, and attaches a calibrated confidence signal. Or upload your own CSV or database."}
            </p>
            <div className="mt-5">
              <SchemaDrawer dataset={dataset} onUpload={handleUpload} onUseOlist={handleUseOlist} />
            </div>
          </motion.div>
          {custom && <CustomBanner filename={dataset.filename} />}
          <QuestionInput
            onSubmit={(q) => submit(q, session)}
            disabled={isStreaming}
            showStarters={!custom}
            placeholder={placeholder}
          />
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-8 py-8">
            {turns.map((turn) => (
              <div key={turn.id} className="flex flex-col gap-3">
                <div className="flex justify-end">
                  <div className="max-w-[85%] rounded-2xl rounded-br-sm border border-border/60 bg-secondary/50 px-4 py-2.5 text-[15px] text-foreground">
                    {turn.question}
                  </div>
                </div>

                {turn.status === "streaming" && <StageProgress stages={turn.stages} />}

                {turn.status === "error" && (
                  <div className="rounded-2xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-foreground">
                    {turn.error ?? "Something went wrong."}
                  </div>
                )}

                {turn.kind === "answer" && turn.answer && (
                  <AnswerCard
                    answer={turn.answer}
                    assumptions={turn.assumptions}
                    confidence={turn.confidence}
                    scoring={turn.scoringConfidence}
                  />
                )}

                {turn.kind === "clarification" && turn.clarification && (
                  <ClarificationCard
                    clarification={turn.clarification}
                    disabled={isStreaming}
                    onSelect={(choice) => clarify(turn.question, choice, session)}
                  />
                )}
              </div>
            ))}
            <div ref={endRef} />
          </div>

          <div className="sticky bottom-0 mt-auto border-t border-border/60 bg-background/80 py-4 backdrop-blur-xl">
            <div className="mb-2.5 flex justify-end">
              <SchemaDrawer
                label="Data"
                dataset={dataset}
                onUpload={handleUpload}
                onUseOlist={handleUseOlist}
              />
            </div>
            {custom && <CustomBanner filename={dataset.filename} />}
            <QuestionInput
              onSubmit={(q) => submit(q, session)}
              disabled={isStreaming}
              placeholder={placeholder}
            />
          </div>
        </>
      )}
    </div>
  );
}

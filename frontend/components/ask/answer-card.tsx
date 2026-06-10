"use client";

import { motion, useReducedMotion } from "motion/react";
import { AlertTriangle, Download, Loader2 } from "lucide-react";
import type { AnswerResult, Assumptions, Confidence } from "@/lib/types";
import { downloadCsv } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Chart } from "@/components/charts/chart";
import { ResultTable } from "@/components/ask/result-table";
import { SqlBlock } from "@/components/ask/sql-block";
import { AssumptionsPanel } from "@/components/ask/assumptions-panel";
import { ConfidenceBadge } from "@/components/ask/confidence-badge";

function MetaPill({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full border border-border/60 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
      {children}
    </span>
  );
}

function ScoringPill() {
  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-card/50 px-3 py-1.5 text-xs text-muted-foreground">
      <Loader2 className="size-3.5 animate-spin" />
      Scoring confidence…
    </div>
  );
}

export function AnswerCard({
  answer,
  assumptions,
  confidence,
  scoring,
}: {
  answer: AnswerResult;
  assumptions?: Assumptions | null;
  confidence?: Confidence | null;
  scoring?: boolean;
}) {
  const reduce = useReducedMotion();
  const hasChart = answer.chart_type === "bar" || answer.chart_type === "line";
  const hasRows = answer.rows.length > 0;

  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className="halo rounded-2xl border border-border/60 bg-card/40 p-5 sm:p-6"
    >
      <div className="flex items-start justify-between gap-4">
        <p className="text-pretty text-[15px] leading-relaxed text-foreground">
          {answer.explanation}
        </p>
        <div className="shrink-0">
          {confidence ? (
            <ConfidenceBadge confidence={confidence} />
          ) : scoring ? (
            <ScoringPill />
          ) : null}
        </div>
      </div>

      {answer.error ? (
        <div className="mt-4 flex items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-foreground">
          <AlertTriangle className="size-4 text-destructive" />
          {answer.error}
        </div>
      ) : (
        <div className="mt-5 flex flex-col gap-5">
          {answer.chart_type === "stat" && hasRows ? (
            <Chart result={answer} />
          ) : hasChart && hasRows ? (
            <Tabs defaultValue="chart">
              <TabsList>
                <TabsTrigger value="chart">Chart</TabsTrigger>
                <TabsTrigger value="table">Table</TabsTrigger>
              </TabsList>
              <TabsContent value="chart" className="pt-3">
                <Chart result={answer} />
              </TabsContent>
              <TabsContent value="table" className="pt-3">
                <ResultTable columns={answer.columns} rows={answer.rows} />
              </TabsContent>
            </Tabs>
          ) : hasRows ? (
            <ResultTable columns={answer.columns} rows={answer.rows} />
          ) : (
            <p className="text-sm text-muted-foreground">The query returned no rows.</p>
          )}

          <SqlBlock sql={answer.sql} />
          {assumptions && <AssumptionsPanel assumptions={assumptions} />}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-1.5">
        <MetaPill>{answer.row_count} rows</MetaPill>
        {answer.self_correction_fired && <MetaPill>self-corrected</MetaPill>}
        {answer.attempts > 1 && <MetaPill>{answer.attempts} attempts</MetaPill>}
        {answer.timed_out && <MetaPill>timed out</MetaPill>}
        {hasRows && !answer.error && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => downloadCsv("prompt-data-result.csv", answer.columns, answer.rows)}
            className="ml-auto h-7 gap-1.5 text-muted-foreground hover:text-foreground"
          >
            <Download className="size-3.5" />
            Export CSV
          </Button>
        )}
      </div>
    </motion.div>
  );
}

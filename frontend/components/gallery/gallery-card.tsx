"use client";

import { AlertTriangle, Check, X } from "lucide-react";
import type { Cell } from "@/lib/types";
import type { GalleryCard as Card } from "@/lib/eval-types";
import { formatCell, isNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import { SqlBlock } from "@/components/ask/sql-block";
import { AssumptionsPanel } from "@/components/ask/assumptions-panel";
import { ConfidenceBadge } from "@/components/ask/confidence-badge";

function MiniTable({ columns, rows }: { columns: string[]; rows: Cell[][] }) {
  if (columns.length === 0) return null;
  return (
    <div className="overflow-hidden rounded-md border border-border/50">
      <table className="w-full text-xs">
        <thead className="bg-card/60">
          <tr>
            {columns.map((c, i) => (
              <th key={i} className="px-2.5 py-1.5 text-left font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 4).map((row, ri) => (
            <tr key={ri}>
              {row.map((cell, ci) => (
                <td key={ci} className={cn("border-t border-border/40 px-2.5 py-1.5 text-foreground/90", isNumber(cell) && "text-right font-mono tabular-nums")}>
                  {formatCell(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Pane({
  tone,
  label,
  tag,
  children,
}: {
  tone: "naive" | "verity";
  label: string;
  tag: string;
  children: React.ReactNode;
}) {
  const naive = tone === "naive";
  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-xl border p-4",
        naive ? "border-border/60 bg-card/20" : "border-primary/30 bg-primary/[0.04]",
      )}
    >
      <div className="flex items-center gap-2">
        {naive ? (
          <X className="size-3.5 text-[oklch(0.7_0.16_30)]" />
        ) : (
          <Check className="size-3.5 text-primary" />
        )}
        <span className={cn("font-mono text-[11px] uppercase tracking-[0.14em]", naive ? "text-muted-foreground" : "text-primary/90")}>
          {label}
        </span>
        <span className="text-[11px] text-muted-foreground/70">{tag}</span>
      </div>
      {children}
    </div>
  );
}

export function GalleryCard({ card }: { card: Card }) {
  const v = card.verity;
  return (
    <div className="halo flex flex-col gap-4 rounded-2xl border border-border/60 bg-card/30 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-border/60 px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          {card.category}
        </span>
      </div>
      <p className="text-[15px] font-medium text-foreground">{card.question}</p>

      <div className="grid gap-3 md:grid-cols-2">
        <Pane tone="naive" label="Naive copilot" tag="trust layer off">
          <SqlBlock sql={card.naive.sql || "(no query produced)"} />
          {card.naive.error ? (
            <div className="flex items-center gap-2 rounded-md border border-[oklch(0.7_0.16_30)]/40 bg-[oklch(0.7_0.16_30)]/10 px-2.5 py-1.5 text-xs text-foreground">
              <AlertTriangle className="size-3.5 text-[oklch(0.7_0.16_30)]" />
              {card.naive.error}
            </div>
          ) : (
            <MiniTable columns={card.naive.columns} rows={card.naive.rows} />
          )}
        </Pane>

        <Pane tone="verity" label="Verity" tag="trust layer on">
          {v.kind === "clarification" && v.clarification ? (
            <div className="flex flex-col gap-2.5">
              <p className="text-sm text-foreground">{v.clarification.question}</p>
              <div className="flex flex-wrap gap-1.5">
                {v.clarification.options.map((o, i) => (
                  <span key={i} className="rounded-full border border-border/60 bg-card/60 px-2.5 py-1 text-xs text-foreground/90">
                    {o}
                  </span>
                ))}
              </div>
            </div>
          ) : (
            v.answer && (
              <div className="flex flex-col gap-3">
                <p className="text-sm text-foreground/90">{v.answer.explanation}</p>
                {v.confidence && <ConfidenceBadge confidence={v.confidence} />}
                {v.assumptions && <AssumptionsPanel assumptions={v.assumptions} />}
              </div>
            )
          )}
        </Pane>
      </div>

      <p className="text-sm text-muted-foreground">{card.takeaway}</p>
    </div>
  );
}

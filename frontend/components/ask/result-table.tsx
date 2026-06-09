"use client";

import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import type { Cell } from "@/lib/types";
import { formatCell, isNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

const PAGE = 50;

export function ResultTable({ columns, rows }: { columns: string[]; rows: Cell[][] }) {
  const [sort, setSort] = useState<{ col: number; dir: "asc" | "desc" } | null>(null);
  const [showAll, setShowAll] = useState(false);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const { col, dir } = sort;
    const sign = dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const x = a[col];
      const y = b[col];
      if (x === null) return 1;
      if (y === null) return -1;
      if (isNumber(x) && isNumber(y)) return (x - y) * sign;
      return String(x).localeCompare(String(y)) * sign;
    });
  }, [rows, sort]);

  const visible = showAll ? sorted : sorted.slice(0, PAGE);

  function toggle(col: number) {
    setSort((prev) =>
      prev?.col === col
        ? { col, dir: prev.dir === "asc" ? "desc" : "asc" }
        : { col, dir: "desc" },
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border/60">
      <div className="max-h-[420px] overflow-auto">
        <table className="w-full border-collapse text-sm">
          <thead className="sticky top-0 z-10 bg-card/95 backdrop-blur">
            <tr>
              {columns.map((c, i) => (
                <th key={i} className="border-b border-border/60 p-0 text-left">
                  <button
                    onClick={() => toggle(i)}
                    className="flex w-full items-center gap-1.5 px-3 py-2.5 font-mono text-[11px] uppercase tracking-wider text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {c}
                    {sort?.col === i ? (
                      sort.dir === "asc" ? (
                        <ArrowUp className="size-3" />
                      ) : (
                        <ArrowDown className="size-3" />
                      )
                    ) : (
                      <ChevronsUpDown className="size-3 opacity-40" />
                    )}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((row, ri) => (
              <tr key={ri} className="transition-colors hover:bg-accent/30">
                {row.map((cell, ci) => (
                  <td
                    key={ci}
                    className={cn(
                      "border-b border-border/40 px-3 py-2 text-foreground/90",
                      isNumber(cell) && "text-right font-mono tabular-nums",
                    )}
                  >
                    {formatCell(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sorted.length > PAGE && (
        <button
          onClick={() => setShowAll((s) => !s)}
          className="w-full border-t border-border/60 bg-card/40 py-2 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          {showAll ? "Show fewer" : `Show all ${sorted.length} rows`}
        </button>
      )}
    </div>
  );
}

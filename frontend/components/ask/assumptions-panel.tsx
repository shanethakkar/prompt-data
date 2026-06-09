import type { Assumptions } from "@/lib/types";

function Row({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="flex flex-col gap-1 sm:flex-row sm:gap-3">
      <span className="shrink-0 font-mono text-[11px] uppercase tracking-wider text-muted-foreground sm:w-20 sm:pt-0.5">
        {label}
      </span>
      <div className="flex flex-wrap gap-1.5">
        {items.map((it, i) => (
          <code
            key={i}
            className="rounded-md border border-border/60 bg-card/50 px-2 py-0.5 font-mono text-xs text-foreground/90"
          >
            {it}
          </code>
        ))}
      </div>
    </div>
  );
}

export function AssumptionsPanel({ assumptions }: { assumptions: Assumptions }) {
  const limit = assumptions.row_limit === null ? [] : [`LIMIT ${assumptions.row_limit}`];
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border/60 bg-card/30 p-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-foreground">Assumptions</span>
        <span className="text-xs text-muted-foreground">extracted from the executed query</span>
      </div>
      <div className="flex flex-col gap-2.5">
        <Row label="Terms" items={assumptions.term_mappings} />
        <Row label="Tables" items={assumptions.tables} />
        <Row label="Joins" items={assumptions.joins} />
        <Row label="Filters" items={assumptions.filters} />
        <Row label="Grain" items={assumptions.group_by} />
        <Row label="Cap" items={limit} />
      </div>
    </div>
  );
}

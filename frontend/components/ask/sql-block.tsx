"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";

const KEYWORDS = new Set([
  "select", "from", "where", "group", "by", "order", "having", "limit", "offset",
  "join", "left", "right", "inner", "outer", "on", "as", "and", "or", "not", "in",
  "is", "null", "distinct", "count", "sum", "avg", "min", "max", "case", "when",
  "then", "else", "end", "with", "union", "all", "asc", "desc", "using", "cast",
  "strftime", "date", "between", "like",
]);

/** Minimal SQL highlighter: keywords in cyan, strings/numbers tinted. No editor dependency. */
function highlight(sql: string): React.ReactNode[] {
  const tokens = sql.match(/'[^']*'|"[^"]*"|\b\w+\b|\s+|[^\s\w]/g) ?? [sql];
  return tokens.map((tok, i) => {
    const lower = tok.toLowerCase();
    if (KEYWORDS.has(lower)) {
      return (
        <span key={i} className="font-medium text-primary">
          {tok}
        </span>
      );
    }
    if (/^'.*'$|^".*"$/.test(tok)) return <span key={i} className="text-emerald-300/90">{tok}</span>;
    if (/^\d+$/.test(tok)) return <span key={i} className="text-amber-200/90">{tok}</span>;
    return <span key={i}>{tok}</span>;
  });
}

export function SqlBlock({ sql }: { sql: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(sql);
    setCopied(true);
    toast.success("SQL copied to clipboard");
    setTimeout(() => setCopied(false), 1600);
  }

  return (
    <div className="group relative overflow-hidden rounded-lg border border-border/60 bg-[oklch(0.12_0.006_277)]">
      <div className="flex items-center justify-between border-b border-border/60 px-4 py-2">
        <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
          Generated SQL
        </span>
        <Button
          variant="ghost"
          size="sm"
          onClick={copy}
          className="h-7 gap-1.5 text-muted-foreground hover:text-foreground"
        >
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <pre className="max-h-80 overflow-auto px-4 py-3.5 text-[13px] leading-relaxed">
        <code className="font-mono">{highlight(sql)}</code>
      </pre>
    </div>
  );
}

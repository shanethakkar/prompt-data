"use client";

import { useState } from "react";
import { Database, KeyRound, Loader2, RotateCcw, Upload } from "lucide-react";
import olistSchemaRaw from "@/content/olist-schema.json";
import { apiUrl } from "@/lib/api";
import type { Dataset, SchemaResponse, SchemaTable, UploadResponse } from "@/lib/schema-types";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { ScrollArea } from "@/components/ui/scroll-area";

// The Olist schema ships statically (generated from the slim demo DB); custom datasets carry
// their schema from the /upload response. No backend call for the Olist case.
const olistSchema = olistSchemaRaw as unknown as SchemaResponse;

function TableBlock({ table }: { table: SchemaTable }) {
  return (
    <div className="rounded-lg border border-border/60 bg-card/30 p-3.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-sm font-medium text-foreground">{table.name}</span>
        <span className="shrink-0 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          {table.row_count.toLocaleString()} rows
        </span>
      </div>
      {table.description && (
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{table.description}</p>
      )}
      <ul className="mt-2.5 flex flex-col gap-1">
        {table.columns.map((c) => (
          <li key={c.name} className="flex items-center gap-2 text-xs">
            {c.primary_key ? (
              <KeyRound className="size-3 shrink-0 text-primary" aria-label="primary key" />
            ) : (
              <span className="size-3 shrink-0" />
            )}
            <span className="font-mono text-foreground/90">{c.name}</span>
            <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              {c.type}
            </span>
            {c.note && <span className="text-muted-foreground/70">— {c.note}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function UploadZone({ onUpload }: { onUpload: (r: UploadResponse) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handle(file: File) {
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch(apiUrl("/upload"), { method: "POST", body: form });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(body?.detail ?? `Upload failed (${res.status})`);
      }
      onUpload((await res.json()) as UploadResponse);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-1.5">
      <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-border/70 bg-card/40 px-3 py-2.5 text-sm text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground">
        <input
          type="file"
          accept=".csv,.db,.sqlite,.sqlite3"
          className="hidden"
          disabled={busy}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void handle(f);
            e.target.value = "";
          }}
        />
        {busy ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />}
        {busy ? "Uploading…" : "Upload a CSV or SQLite file"}
      </label>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

export function SchemaDrawer({
  label = "What's in the data?",
  dataset,
  onUpload,
  onUseOlist,
}: {
  label?: string;
  dataset: Dataset;
  onUpload: (r: UploadResponse) => void;
  onUseOlist: () => void;
}) {
  const custom = dataset.kind === "custom";
  const tables = custom ? dataset.tables : olistSchema.tables;

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5 text-muted-foreground">
          <Database className="size-3.5" />
          {label}
        </Button>
      </SheetTrigger>
      <SheetContent className="flex w-full flex-col gap-0 sm:max-w-md">
        <SheetHeader>
          <SheetTitle>
            {custom ? (dataset.filename ?? "Your dataset") : "The Olist dataset"}
          </SheetTitle>
          <SheetDescription>
            {custom
              ? "Your uploaded data. Confidence is uncalibrated for custom datasets."
              : "A Brazilian e-commerce database. Ask about orders, items, products, sellers, customers, payments, and reviews."}
          </SheetDescription>
        </SheetHeader>
        <ScrollArea className="flex-1 px-4">
          <div className="flex flex-col gap-2.5 pb-4">
            {tables.map((t) => (
              <TableBlock key={t.name} table={t} />
            ))}
          </div>
        </ScrollArea>
        <div className="flex flex-col gap-2 border-t border-border/60 p-4">
          <UploadZone onUpload={onUpload} />
          {custom && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onUseOlist}
              className="gap-1.5 text-muted-foreground"
            >
              <RotateCcw className="size-3.5" />
              Back to the Olist demo
            </Button>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

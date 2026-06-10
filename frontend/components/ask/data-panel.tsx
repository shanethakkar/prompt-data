"use client";

import { useState } from "react";
import { Check, Database, KeyRound, Loader2, Table2, Upload } from "lucide-react";
import olistSchemaRaw from "@/content/olist-schema.json";
import { apiUrl } from "@/lib/api";
import type { Dataset, SchemaResponse, SchemaTable, UploadResponse } from "@/lib/schema-types";
import { cn } from "@/lib/utils";

// The Olist schema ships statically (generated from the slim demo DB); custom datasets carry their
// schema from the /upload response. No backend call for the Olist case.
const olistSchema = olistSchemaRaw as unknown as SchemaResponse;

function TableBlock({ table }: { table: SchemaTable }) {
  return (
    <div className="rounded-lg border border-border/60 bg-card/30 p-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate font-mono text-[13px] font-medium text-foreground">{table.name}</span>
        <span className="shrink-0 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          {table.row_count.toLocaleString()} rows
        </span>
      </div>
      {table.description && (
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{table.description}</p>
      )}
      <ul className="mt-2 flex flex-col gap-1">
        {table.columns.map((c) => (
          <li key={c.name} className="flex items-center gap-1.5 text-xs">
            {c.primary_key ? (
              <KeyRound className="size-3 shrink-0 text-primary" aria-label="primary key" />
            ) : (
              <span className="size-3 shrink-0" />
            )}
            <span className="truncate font-mono text-foreground/90">{c.name}</span>
            <span className="shrink-0 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              {c.type}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SourceRow({
  active,
  icon: Icon,
  title,
  subtitle,
  onClick,
}: {
  active: boolean;
  icon: typeof Database;
  title: string;
  subtitle: string;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={active && !onClick}
      className={cn(
        "flex w-full items-center gap-2.5 rounded-lg border px-3 py-2 text-left transition-colors",
        active
          ? "border-primary/50 bg-primary/[0.07]"
          : "border-border/60 bg-card/30 hover:border-border hover:bg-card/50",
      )}
    >
      <Icon className={cn("size-4 shrink-0", active ? "text-primary" : "text-muted-foreground")} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm text-foreground">{title}</span>
        <span className="block truncate text-[11px] text-muted-foreground">{subtitle}</span>
      </span>
      {active && <Check className="size-4 shrink-0 text-primary" />}
    </button>
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
      <label className="flex cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-border/70 bg-card/20 px-3 py-4 text-center text-xs text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground">
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
        <span className="font-medium text-foreground">
          {busy ? "Uploading…" : "Upload your own data"}
        </span>
        <span>CSV or SQLite file</span>
      </label>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

export function DataPanel({
  dataset,
  onUpload,
  onUseOlist,
}: {
  dataset: Dataset;
  onUpload: (r: UploadResponse) => void;
  onUseOlist: () => void;
}) {
  const custom = dataset.kind === "custom";
  const tables = custom ? dataset.tables : olistSchema.tables;

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-col gap-2.5 border-b border-border/60 p-4">
        <div className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
          Data source
        </div>
        <SourceRow
          active={!custom}
          icon={Database}
          title="Olist demo"
          subtitle="Brazilian e-commerce database"
          onClick={custom ? onUseOlist : undefined}
        />
        {custom && (
          <SourceRow
            active
            icon={Table2}
            title={dataset.filename ?? "Your dataset"}
            subtitle="custom · confidence uncalibrated"
          />
        )}
        <UploadZone onUpload={onUpload} />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        <div className="mb-2 px-1 font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
          {custom ? "Your tables" : "Schema"}
        </div>
        <div className="flex flex-col gap-2">
          {tables.map((t) => (
            <TableBlock key={t.name} table={t} />
          ))}
        </div>
      </div>
    </div>
  );
}

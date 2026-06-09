"use client";

import { useEffect, useState } from "react";
import { Database, KeyRound, Loader2 } from "lucide-react";
import { apiUrl } from "@/lib/api";
import type { SchemaResponse, SchemaTable } from "@/lib/schema-types";
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

export function SchemaDrawer({ label = "What's in the data?" }: { label?: string }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<SchemaResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || data) return;
    let cancelled = false;
    fetch(apiUrl("/schema"))
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`Schema request failed (${r.status})`))))
      .then((d: SchemaResponse) => !cancelled && setData(d))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [open, data]);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5 text-muted-foreground">
          <Database className="size-3.5" />
          {label}
        </Button>
      </SheetTrigger>
      <SheetContent className="w-full gap-0 sm:max-w-md">
        <SheetHeader>
          <SheetTitle>The Olist dataset</SheetTitle>
          <SheetDescription>
            A Brazilian e-commerce database. Ask about orders, items, products, sellers, customers,
            payments, and reviews.
          </SheetDescription>
        </SheetHeader>
        <ScrollArea className="h-full px-4 pb-6">
          {error ? (
            <p className="text-sm text-muted-foreground">{error}</p>
          ) : !data ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Loading schema…
            </div>
          ) : (
            <div className="flex flex-col gap-2.5">
              {data.tables.map((t) => (
                <TableBlock key={t.name} table={t} />
              ))}
            </div>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}

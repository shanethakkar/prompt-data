"use client";

import { Database } from "lucide-react";
import type { Dataset, UploadResponse } from "@/lib/schema-types";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { DataPanel } from "@/components/ask/data-panel";

// Mobile-only: the same DataPanel inside a sheet (the persistent sidebar is hidden below `md`).
export function DataSheet({
  dataset,
  onUpload,
  onUseOlist,
}: {
  dataset: Dataset;
  onUpload: (r: UploadResponse) => void;
  onUseOlist: () => void;
}) {
  const label = dataset.kind === "custom" ? (dataset.filename ?? "Your dataset") : "Olist demo";
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5 text-muted-foreground">
          <Database className="size-3.5" />
          <span className="max-w-40 truncate">Data: {label}</span>
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-full gap-0 p-0 sm:max-w-sm">
        <SheetTitle className="sr-only">Data source and schema</SheetTitle>
        <DataPanel dataset={dataset} onUpload={onUpload} onUseOlist={onUseOlist} />
      </SheetContent>
    </Sheet>
  );
}

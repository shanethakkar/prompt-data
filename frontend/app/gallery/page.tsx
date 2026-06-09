"use client";

import { useMemo, useState } from "react";
import galleryRaw from "@/content/gallery.json";
import type { GalleryData } from "@/lib/eval-types";
import { PageHeader } from "@/components/site/page-header";
import { GalleryCard } from "@/components/gallery/gallery-card";

const gallery = galleryRaw as unknown as GalleryData;

export default function GalleryPage() {
  const categories = useMemo(
    () => ["All", ...Array.from(new Set(gallery.cards.map((c) => c.category)))],
    [],
  );
  const [active, setActive] = useState("All");
  const cards = active === "All" ? gallery.cards : gallery.cards.filter((c) => c.category === active);

  return (
    <div className="mx-auto max-w-3xl px-5 py-12">
      <PageHeader
        eyebrow="The killer demo"
        title="Gallery"
        lede="The questions that quietly break a naive copilot, shown side by side. Same model, trust layer off vs on. All outputs are real captures, not mock-ups."
      />

      <div className="mb-6 flex flex-wrap gap-2">
        {categories.map((c) => (
          <button
            key={c}
            onClick={() => setActive(c)}
            className={
              active === c
                ? "rounded-full border border-primary/60 bg-primary/10 px-3 py-1.5 text-xs text-foreground"
                : "rounded-full border border-border/60 bg-card/40 px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
            }
          >
            {c}
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-6">
        {cards.map((card) => (
          <GalleryCard key={card.id} card={card} />
        ))}
      </div>
    </div>
  );
}

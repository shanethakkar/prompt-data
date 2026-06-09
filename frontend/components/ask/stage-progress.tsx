"use client";

import { motion, useReducedMotion } from "motion/react";
import { Check, Loader2 } from "lucide-react";
import type { Stage } from "@/lib/types";

export function StageProgress({ stages }: { stages: Stage[] }) {
  const reduce = useReducedMotion();
  if (stages.length === 0) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        Starting…
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2.5 rounded-2xl border border-border/60 bg-card/30 p-5">
      {stages.map((s) => (
        <motion.div
          key={s.name}
          initial={reduce ? false : { opacity: 0, x: -6 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.25 }}
          className="flex items-center gap-2.5 text-sm"
        >
          <span className="grid size-5 place-items-center">
            {s.done ? (
              <Check className="size-4 text-primary" />
            ) : (
              <Loader2 className="size-4 animate-spin text-primary" />
            )}
          </span>
          <span className={s.done ? "text-muted-foreground" : "text-foreground"}>{s.label}</span>
        </motion.div>
      ))}
    </div>
  );
}

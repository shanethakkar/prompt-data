"use client";

import { motion, useReducedMotion } from "motion/react";
import { HelpCircle } from "lucide-react";
import type { Clarification } from "@/lib/types";

export function ClarificationCard({
  clarification,
  onSelect,
  disabled,
}: {
  clarification: Clarification;
  onSelect: (choice: string) => void;
  disabled?: boolean;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className="rounded-2xl border border-primary/30 bg-primary/[0.04] p-5 sm:p-6"
    >
      <div className="flex items-center gap-2">
        <HelpCircle className="size-4 text-primary" />
        <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-primary/90">
          Clarifying first
        </span>
        {clarification.dimensions.length > 0 && (
          <span className="text-xs text-muted-foreground">
            ({clarification.dimensions.join(", ")})
          </span>
        )}
      </div>
      <p className="mt-3 text-pretty text-[15px] leading-relaxed text-foreground">
        {clarification.question}
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        {clarification.options.map((opt, i) => (
          <button
            key={i}
            disabled={disabled}
            onClick={() => onSelect(opt)}
            className="rounded-full border border-border/70 bg-card/60 px-3.5 py-1.5 text-sm text-foreground/90 transition-all hover:border-primary/60 hover:bg-primary/10 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
          >
            {opt}
          </button>
        ))}
      </div>
    </motion.div>
  );
}

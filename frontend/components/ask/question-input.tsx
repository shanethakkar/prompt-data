"use client";

import { useState } from "react";
import { ArrowUp } from "lucide-react";
import { Button } from "@/components/ui/button";

const STARTERS = [
  "What are the top 5 product categories by revenue?",
  "How many orders were delivered?",
  "What is the average review score by product category?",
  "How many orders were placed each month in 2017?",
];

export function QuestionInput({
  onSubmit,
  disabled,
  showStarters,
  placeholder = "Ask the Olist database anything…",
}: {
  onSubmit: (question: string) => void;
  disabled?: boolean;
  showStarters?: boolean;
  placeholder?: string;
}) {
  const [value, setValue] = useState("");

  function submit() {
    const q = value.trim();
    if (!q || disabled) return;
    onSubmit(q);
    setValue("");
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="halo flex items-end gap-2 rounded-2xl border border-border/70 bg-card/50 p-2.5 focus-within:border-primary/50">
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={1}
          placeholder={placeholder}
          aria-label="Ask a question"
          className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-2 py-1.5 text-[15px] text-foreground outline-none placeholder:text-muted-foreground"
        />
        <Button
          size="icon"
          onClick={submit}
          disabled={disabled || !value.trim()}
          aria-label="Send"
          className="size-9 shrink-0 rounded-xl"
        >
          <ArrowUp className="size-4" />
        </Button>
      </div>
      {showStarters && (
        <div className="flex flex-wrap gap-2">
          {STARTERS.map((s) => (
            <button
              key={s}
              disabled={disabled}
              onClick={() => onSubmit(s)}
              className="rounded-full border border-border/60 bg-card/40 px-3 py-1.5 text-xs text-muted-foreground transition-all hover:border-primary/50 hover:text-foreground disabled:opacity-50"
            >
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

import { ShieldCheck } from "lucide-react";
import type { Confidence } from "@/lib/types";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

function band(score: number): { label: string; color: string } {
  if (score >= 0.75) return { label: "High", color: "oklch(0.79 0.135 199)" };
  if (score >= 0.5) return { label: "Moderate", color: "oklch(0.8 0.12 90)" };
  return { label: "Low", color: "oklch(0.7 0.16 30)" };
}

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  const pct = Math.round(confidence.score * 100);
  const { label, color } = band(confidence.score);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-card/50 px-3 py-1.5"
          role="status"
          aria-label={`Confidence ${pct} percent, ${label}`}
        >
          <ShieldCheck className="size-3.5" style={{ color }} />
          <span className="text-sm font-medium tabular-nums" style={{ color }}>
            {pct}%
          </span>
          <span className="text-xs text-muted-foreground">{label} confidence</span>
          {!confidence.calibrated && (
            <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/70">
              provisional
            </span>
          )}
        </div>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">
        <p>{confidence.explanation}</p>
        <p className="mt-1 text-muted-foreground">
          {confidence.calibrated
            ? "Calibrated against held-out accuracy."
            : "Not yet calibrated; shown as a provisional signal."}
        </p>
      </TooltipContent>
    </Tooltip>
  );
}

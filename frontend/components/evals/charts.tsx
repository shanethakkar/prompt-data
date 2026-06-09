import type { ReliabilityBin } from "@/lib/eval-types";

const TONE: Record<string, string> = {
  primary: "fill-primary",
  warn: "fill-[oklch(0.7_0.16_30)]",
  muted: "fill-muted-foreground/50",
};

export function MetricCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-xl border border-border/60 bg-card/40 p-5">
      <div className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
        {label}
      </div>
      <div className="mt-2 font-mono text-3xl font-semibold tracking-tight text-foreground tabular-nums">
        {value}
      </div>
      {sub && <div className="mt-1.5 text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

/** Horizontal bars for values in [0,1], rendered as percentages. */
export function PercentBars({
  bars,
}: {
  bars: { label: string; value: number; tone?: keyof typeof TONE }[];
}) {
  const rowH = 40;
  const labelW = 150;
  const barW = 460;
  const height = bars.length * rowH;
  return (
    <svg
      viewBox={`0 0 ${labelW + barW + 60} ${height}`}
      className="w-full"
      role="img"
      aria-label="Comparison bars"
    >
      {bars.map((b, i) => {
        const w = Math.max(b.value * barW, 2);
        const y = i * rowH;
        return (
          <g key={i}>
            <text
              x={labelW - 12}
              y={y + rowH / 2}
              textAnchor="end"
              dominantBaseline="middle"
              className="fill-muted-foreground"
              fontSize={12}
            >
              {b.label}
            </text>
            <rect x={labelW} y={y + 8} width={barW} height={rowH - 18} rx={5} className="fill-border/40" />
            <rect
              x={labelW}
              y={y + 8}
              width={w}
              height={rowH - 18}
              rx={5}
              className={TONE[b.tone ?? "primary"]}
            />
            <text
              x={labelW + w + 8}
              y={y + rowH / 2}
              dominantBaseline="middle"
              className="fill-foreground tabular-nums"
              fontSize={12}
            >
              {Math.round(b.value * 100)}%
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** Reliability diagram: predicted confidence (x) vs observed accuracy (y), ideal diagonal. */
export function ReliabilityDiagram({ bins }: { bins: ReliabilityBin[] }) {
  const size = 320;
  const pad = 36;
  const plot = size - pad * 2;
  const sx = (v: number) => pad + v * plot;
  const sy = (v: number) => size - pad - v * plot;
  const points = bins.filter((b) => b.count > 0);
  const maxCount = Math.max(...points.map((p) => p.count), 1);

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="w-full max-w-sm" role="img" aria-label="Reliability diagram: predicted confidence versus observed accuracy">
      {/* frame */}
      <rect x={pad} y={pad} width={plot} height={plot} className="fill-card/30 stroke-border/60" />
      {/* ideal diagonal */}
      <line x1={sx(0)} y1={sy(0)} x2={sx(1)} y2={sy(1)} className="stroke-muted-foreground/40" strokeDasharray="4 4" />
      {/* points */}
      {points.map((p, i) => (
        <circle
          key={i}
          cx={sx(p.predicted)}
          cy={sy(p.observed)}
          r={4 + (p.count / maxCount) * 7}
          className="fill-primary/70 stroke-primary"
        />
      ))}
      <text x={size / 2} y={size - 6} textAnchor="middle" className="fill-muted-foreground" fontSize={11}>
        predicted confidence
      </text>
      <text x={12} y={size / 2} textAnchor="middle" transform={`rotate(-90 12 ${size / 2})`} className="fill-muted-foreground" fontSize={11}>
        observed accuracy
      </text>
    </svg>
  );
}

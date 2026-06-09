"use client";

import type { AnswerResult, Cell } from "@/lib/types";
import { compactNumber, formatCell, isNumber } from "@/lib/format";

// Hand-built SVG charts, no chart library (per spec). Each is responsive (viewBox + width 100%)
// and ARIA-labelled. The backend picks chart_type from the result shape.

/** Evenly spaced, nicely-rounded ticks from 0 covering [0, maxValue]. */
function niceTicks(maxValue: number, count = 4): number[] {
  if (!(maxValue > 0)) return [0, 1];
  const rawStep = maxValue / count;
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const norm = rawStep / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag;
  const ticks: number[] = [];
  for (let t = 0; t <= maxValue + step * 1e-6; t += step) ticks.push(t);
  if (ticks[ticks.length - 1] < maxValue) ticks.push(ticks[ticks.length - 1] + step);
  return ticks;
}

function StatCard({ label, value }: { label: string; value: Cell }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-border/60 bg-card/40 px-6 py-10">
      <div className="font-mono text-5xl font-semibold tracking-tight text-foreground tabular-nums">
        {formatCell(value)}
      </div>
      <div className="mt-3 font-mono text-xs uppercase tracking-[0.16em] text-muted-foreground">
        {label}
      </div>
    </div>
  );
}

function BarChart({ rows, columns }: { rows: Cell[][]; columns: string[] }) {
  const data = rows
    .map((r) => ({ label: formatCell(r[0]), value: isNumber(r[1]) ? r[1] : 0 }))
    .slice(0, 12);
  const rowH = 34;
  const labelW = 168;
  const barW = 520;
  const top = 6;
  const plotH = data.length * rowH;
  const axisY = top + plotH; // bottom (value) axis
  const width = labelW + barW + 24;
  const height = axisY + 40; // room for tick labels + axis title

  const ticks = niceTicks(Math.max(...data.map((d) => d.value), 1));
  const axisMax = ticks[ticks.length - 1];
  const sx = (v: number) => labelW + (v / axisMax) * barW;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full"
      role="img"
      aria-label={`Bar chart of ${columns[1]} by ${columns[0]}, values from 0 to ${compactNumber(axisMax)}`}
    >
      {/* value gridlines + x-axis ticks */}
      {ticks.map((t, i) => (
        <g key={`t${i}`}>
          <line x1={sx(t)} y1={top} x2={sx(t)} y2={axisY} className="stroke-border/30" />
          <text x={sx(t)} y={axisY + 15} textAnchor="middle" className="fill-muted-foreground" fontSize={11}>
            {compactNumber(t)}
          </text>
        </g>
      ))}
      {/* bars + category labels */}
      {data.map((d, i) => {
        const w = Math.max((d.value / axisMax) * barW, 1);
        const y = top + i * rowH;
        return (
          <g key={i}>
            <text x={labelW - 12} y={y + rowH / 2} textAnchor="end" dominantBaseline="middle" className="fill-muted-foreground" fontSize={12}>
              {d.label.length > 22 ? `${d.label.slice(0, 21)}…` : d.label}
            </text>
            <rect x={labelW} y={y + 7} width={w} height={rowH - 14} rx={4} className="fill-primary" />
            <text x={labelW + w + 8} y={y + rowH / 2} dominantBaseline="middle" className="fill-foreground tabular-nums" fontSize={12}>
              {compactNumber(d.value)}
            </text>
          </g>
        );
      })}
      {/* axes */}
      <line x1={labelW} y1={top} x2={labelW} y2={axisY} className="stroke-border/70" />
      <line x1={labelW} y1={axisY} x2={labelW + barW} y2={axisY} className="stroke-border/70" />
      <text x={labelW + barW / 2} y={height - 4} textAnchor="middle" className="fill-muted-foreground" fontSize={11}>
        {columns[1]}
      </text>
    </svg>
  );
}

function LineChart({ rows, columns }: { rows: Cell[][]; columns: string[] }) {
  const data = rows.map((r) => ({ label: formatCell(r[0]), value: isNumber(r[1]) ? r[1] : 0 }));
  const w = 760;
  const h = 280;
  const pad = { top: 14, right: 18, bottom: 46, left: 64 };
  const plotW = w - pad.left - pad.right;
  const plotH = h - pad.top - pad.bottom;

  const dataMax = Math.max(...data.map((d) => d.value), 1);
  const ticks = niceTicks(dataMax);
  const yMax = ticks[ticks.length - 1];

  const x = (i: number) => pad.left + (i / Math.max(data.length - 1, 1)) * plotW;
  const y = (v: number) => pad.top + (1 - v / yMax) * plotH;
  const baseY = pad.top + plotH;
  const points = data.map((d, i) => `${x(i)},${y(d.value)}`).join(" ");
  const area = `${pad.left},${baseY} ${points} ${x(data.length - 1)},${baseY}`;

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      className="w-full"
      role="img"
      aria-label={`Line chart of ${columns[1]} over ${columns[0]}, values from 0 to ${compactNumber(yMax)}`}
    >
      {/* y gridlines + ticks */}
      {ticks.map((t, i) => (
        <g key={`y${i}`}>
          <line x1={pad.left} y1={y(t)} x2={pad.left + plotW} y2={y(t)} className="stroke-border/30" />
          <text x={pad.left - 8} y={y(t)} textAnchor="end" dominantBaseline="middle" className="fill-muted-foreground" fontSize={11}>
            {compactNumber(t)}
          </text>
        </g>
      ))}
      {/* axes */}
      <line x1={pad.left} y1={pad.top} x2={pad.left} y2={baseY} className="stroke-border/70" />
      <line x1={pad.left} y1={baseY} x2={pad.left + plotW} y2={baseY} className="stroke-border/70" />
      {/* series */}
      <polygon points={area} className="fill-primary/10" />
      <polyline points={points} fill="none" className="stroke-primary" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      {data.map((d, i) => (
        <g key={i}>
          <circle cx={x(i)} cy={y(d.value)} r={3} className="fill-primary" />
          {(i === 0 || i === data.length - 1 || data.length <= 12) && (
            <text x={x(i)} y={baseY + 16} textAnchor="middle" className="fill-muted-foreground" fontSize={10}>
              {d.label.length > 10 ? d.label.slice(-7) : d.label}
            </text>
          )}
        </g>
      ))}
      {/* axis titles */}
      <text x={pad.left + plotW / 2} y={h - 4} textAnchor="middle" className="fill-muted-foreground" fontSize={11}>
        {columns[0]}
      </text>
      <text x={14} y={pad.top + plotH / 2} textAnchor="middle" transform={`rotate(-90 14 ${pad.top + plotH / 2})`} className="fill-muted-foreground" fontSize={11}>
        {columns[1]}
      </text>
    </svg>
  );
}

export function Chart({ result }: { result: AnswerResult }) {
  const { chart_type, columns, rows } = result;
  if (chart_type === "none" || rows.length === 0) return null;
  if (chart_type === "stat") return <StatCard label={columns[0] ?? "Result"} value={rows[0]?.[0] ?? null} />;
  if (chart_type === "bar") return <BarChart rows={rows} columns={columns} />;
  if (chart_type === "line") return <LineChart rows={rows} columns={columns} />;
  return null; // "table" -> the ResultTable carries it
}

"use client";

import type { AnswerResult, Cell } from "@/lib/types";
import { compactNumber, formatCell, isNumber } from "@/lib/format";

// Hand-built SVG charts, no chart library (per spec). Each is responsive (viewBox + width 100%)
// and ARIA-labelled. The backend picks chart_type from the result shape.

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
  const max = Math.max(...data.map((d) => d.value), 1);
  const rowH = 34;
  const height = data.length * rowH;
  const labelW = 168;
  const barW = 520;

  return (
    <svg
      viewBox={`0 0 ${labelW + barW + 70} ${height}`}
      className="w-full"
      role="img"
      aria-label={`Bar chart of ${columns[1]} by ${columns[0]}`}
    >
      {data.map((d, i) => {
        const w = Math.max((d.value / max) * barW, 2);
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
              {d.label.length > 22 ? `${d.label.slice(0, 21)}…` : d.label}
            </text>
            <rect x={labelW} y={y + 7} width={barW} height={rowH - 14} rx={4} className="fill-border/40" />
            <rect x={labelW} y={y + 7} width={w} height={rowH - 14} rx={4} className="fill-primary" />
            <text
              x={labelW + w + 8}
              y={y + rowH / 2}
              dominantBaseline="middle"
              className="fill-foreground tabular-nums"
              fontSize={12}
            >
              {compactNumber(d.value)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function LineChart({ rows, columns }: { rows: Cell[][]; columns: string[] }) {
  const data = rows.map((r) => ({ label: formatCell(r[0]), value: isNumber(r[1]) ? r[1] : 0 }));
  const w = 760;
  const h = 240;
  const pad = { top: 16, right: 20, bottom: 28, left: 44 };
  const max = Math.max(...data.map((d) => d.value), 1);
  const min = Math.min(...data.map((d) => d.value), 0);
  const span = max - min || 1;
  const x = (i: number) =>
    pad.left + (i / Math.max(data.length - 1, 1)) * (w - pad.left - pad.right);
  const y = (v: number) => pad.top + (1 - (v - min) / span) * (h - pad.top - pad.bottom);
  const points = data.map((d, i) => `${x(i)},${y(d.value)}`).join(" ");
  const area = `${pad.left},${h - pad.bottom} ${points} ${x(data.length - 1)},${h - pad.bottom}`;

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      className="w-full"
      role="img"
      aria-label={`Line chart of ${columns[1]} over ${columns[0]}`}
    >
      <polygon points={area} className="fill-primary/10" />
      <polyline
        points={points}
        fill="none"
        className="stroke-primary"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {data.map((d, i) => (
        <g key={i}>
          <circle cx={x(i)} cy={y(d.value)} r={3} className="fill-primary" />
          {(i === 0 || i === data.length - 1 || data.length <= 12) && (
            <text
              x={x(i)}
              y={h - 10}
              textAnchor="middle"
              className="fill-muted-foreground"
              fontSize={10}
            >
              {d.label.length > 8 ? d.label.slice(-5) : d.label}
            </text>
          )}
        </g>
      ))}
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

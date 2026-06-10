import type { Cell } from "@/lib/types";

export function isNumber(v: Cell): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

export function formatCell(v: Cell): string {
  if (v === null) return "—";
  if (isNumber(v)) {
    return Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(v);
}

export function compactNumber(v: number): string {
  return Math.abs(v) >= 1000
    ? v.toLocaleString(undefined, { notation: "compact", maximumFractionDigits: 1 })
    : v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function csvCell(v: Cell): string {
  const s = v === null ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** Serialize a result set to CSV and trigger a client-side download. */
export function downloadCsv(filename: string, columns: string[], rows: Cell[][]): void {
  const lines = [columns.map(csvCell).join(","), ...rows.map((r) => r.map(csvCell).join(","))];
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

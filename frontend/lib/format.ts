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

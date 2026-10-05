import { relativeTime } from "@/lib/utils";

// Display-format guards. Every function returns "—" for null/undefined/NaN/
// Infinity so no component ever renders "NaN%" or "undefined" text.

const DASH = "—";

/** Locale-grouped number, fixed fraction digits. Bad input → "—". */
export function fmtNum(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return DASH;
  return v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** Percent display. Accepts a ratio (|v| ≤ 1 → ×100) or an already-scaled percent. */
export function fmtPct(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return DASH;
  const pct = Math.abs(v) <= 1 ? v * 100 : v;
  return `${fmtNum(pct, digits)}%`;
}

/** Compact magnitude, e.g. 12400 → "12.4K". Bad input → "—". */
export function fmtCompact(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return DASH;
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(v);
}

/** Relative time, e.g. "3h ago". Delegates to utils.relativeTime; bad ISO → "—". */
export function fmtRelTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  return relativeTime(iso) || DASH;
}

"use client";

import type { TooltipContentProps } from "recharts";

// Custom recharts tooltip content — Paper-token surface, so it theme-switches
// with the palette. recharts v3: pass as `content={<ChartTooltip />}` (props
// are injected by cloning) or `content={ChartTooltip}`.

/** Themed tooltip panel: label row + one dot-coded row per series. */
export function ChartTooltip({
  active,
  payload,
  label,
  valueFormat,
}: Partial<TooltipContentProps<number | string, string>> & {
  /** Formats numeric row values (e.g. fmtNum, fmtPct). */
  valueFormat?: (v: number) => string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 shadow-sm">
      {label !== undefined && label !== "" && <p className="text-label font-semibold text-muted">{String(label)}</p>}
      <div className="mt-1 space-y-0.5">
        {payload.map((entry, i) => (
          <p key={`${String(entry.dataKey ?? entry.name)}-${i}`} className="tabular flex items-center gap-1.5 text-caption text-ink">
            <span className="size-2 shrink-0 rounded-full" style={{ background: entry.color ?? "var(--accent)" }} aria-hidden="true" />
            <span className="min-w-0 truncate text-muted">{String(entry.name ?? "")}</span>
            <span className="ml-auto pl-3 font-semibold">
              {typeof entry.value === "number" && valueFormat ? valueFormat(entry.value) : String(entry.value ?? "—")}
            </span>
          </p>
        ))}
      </div>
    </div>
  );
}

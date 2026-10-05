"use client";

import { Skeleton } from "@/components/skeleton";

// Template stat-pill strip (deliberately NOT MetricCard) — compact counts for
// list-page headers. Promoted from quarantine's queue-pills for the wave-3
// list pages; StatPills/QueuePills name both exported for call-site clarity.

export interface StatPillDef {
  key: string;
  label: string;
  value: number;
  /** Danger tints the value when it is non-zero (e.g. overdue count). */
  tone?: "danger";
}

export function StatPills({ pills, loading = false }: { pills: StatPillDef[]; loading?: boolean }) {
  if (loading) {
    return (
      <div className="flex flex-wrap gap-2" aria-hidden="true">
        {pills.map((p) => (
          <div key={p.key} className="w-28 rounded-md border border-line bg-canvas px-3 py-2">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="mt-2 h-5 w-10" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-wrap gap-2">
      {pills.map((p) => (
        <div key={p.key} className="min-w-28 rounded-md border border-line bg-canvas px-3 py-2">
          <p className="text-xs text-muted">{p.label}</p>
          <p className={`text-lg font-mono font-semibold ${p.tone === "danger" && p.value > 0 ? "text-danger" : "text-ink"}`}>
            {p.value}
          </p>
        </div>
      ))}
    </div>
  );
}

export { StatPills as QueuePills };
export type { StatPillDef as QueuePillDef };

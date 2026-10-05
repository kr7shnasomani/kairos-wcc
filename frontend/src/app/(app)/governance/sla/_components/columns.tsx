"use client";

import Link from "next/link";
import { StatusBadge, type TableColumn } from "@/components/ui";
import { fmtNum, fmtRelTime } from "@/lib/format";
import type { SlaReport } from "@/lib/types";
import { triggerLabel } from "@/lib/utils";

/** Merged overdue item. Type alias (not interface) so it satisfies
 *  DataTable's `Record<string, unknown>` constraint. */
export type SlaRow = {
  id: string;
  kind: "conflict" | "quarantine";
  category: string;
  asset: string | null;
  deadline: string;
  days_overdue: number;
  escalated_at: string | null;
  status: string;
  href: string;
};

const DAY_MS = 86_400_000;

/** Merge both overdue queues and compute days overdue against the supplied
 *  clock (callers pass `nowMs()` — never read the clock at module scope).
 *  Pre-sorted worst-first, so the table's unsorted view = days_overdue desc. */
export function buildRows(report: SlaReport, now: number): SlaRow[] {
  const days = (iso: string) => {
    const t = Date.parse(iso);
    return Number.isFinite(t) ? Math.max(0, (now - t) / DAY_MS) : 0;
  };
  const rows: SlaRow[] = [
    ...(report.overdue_conflicts ?? []).map((c) => ({
      id: c.conflict_id,
      kind: "conflict" as const,
      category: c.track,
      asset: c.asset_id,
      deadline: c.sla_deadline,
      days_overdue: days(c.sla_deadline),
      escalated_at: c.escalated_at,
      status: c.status,
      href: "/governance/conflicts",
    })),
    ...(report.overdue_quarantine_items ?? []).map((q) => ({
      id: q.item_id,
      kind: "quarantine" as const,
      category: triggerLabel(q.input_type),
      asset: q.asset_id,
      deadline: q.sla_due_at,
      days_overdue: days(q.sla_due_at),
      escalated_at: q.escalated_at,
      status: "pending review",
      href: "/governance/quarantine",
    })),
  ];
  return rows.sort((a, b) => b.days_overdue - a.days_overdue);
}

export const COLUMNS: TableColumn<SlaRow>[] = [
  {
    key: "id",
    label: "Item",
    render: (r) => (
      <Link
        href={r.href}
        onClick={(e) => e.stopPropagation()}
        className="tabular text-caption font-semibold text-accent hover:underline"
      >
        {r.id}
      </Link>
    ),
  },
  {
    key: "kind",
    label: "Kind",
    sortable: true,
    render: (r) => (
      <StatusBadge tone={r.kind === "conflict" ? "danger" : "caution"} dot={false}>
        {r.kind}
      </StatusBadge>
    ),
  },
  { key: "category", label: "Category", sortable: true },
  {
    key: "asset",
    label: "Asset",
    sortable: true,
    render: (r) => (r.asset ? <span className="tabular">{r.asset}</span> : <span className="text-muted">—</span>),
  },
  { key: "deadline", label: "Deadline", sortValue: (r) => r.deadline, render: (r) => fmtRelTime(r.deadline) },
  {
    key: "days_overdue",
    label: "Overdue",
    sortValue: (r) => r.days_overdue,
    render: (r) => (
      <span className={`tabular font-semibold ${r.days_overdue >= 1 ? "text-danger" : "text-caution"}`}>
        {fmtNum(r.days_overdue, 1)}d
      </span>
    ),
  },
  {
    key: "escalated_at",
    label: "Escalated",
    render: (r) =>
      r.escalated_at ? (
        <StatusBadge tone="danger" dot={false}>escalated</StatusBadge>
      ) : (
        <span className="text-muted">—</span>
      ),
  },
];

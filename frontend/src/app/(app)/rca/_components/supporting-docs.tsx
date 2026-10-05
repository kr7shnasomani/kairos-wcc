"use client";

import { AuthorityBadge, SourceChip } from "@/components/ui";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui-card";
import { fmtPct } from "@/lib/format";
import type { RcaSupportingDoc } from "@/lib/types";

/** Authority-ranked evidence rows: title, source chip, authority badge, confidence. */
export function SupportingDocs({ docs }: { docs: RcaSupportingDoc[] }) {
  if ((docs ?? []).length === 0) return null;

  return (
    <Card className="overflow-hidden shadow-sm">
      <CardHeader className="border-b border-line p-4 sm:px-5">
        <CardTitle className="text-sm">Supporting documents</CardTitle>
        <CardDescription>Authority-ranked evidence referenced by this analysis.</CardDescription>
      </CardHeader>
      <div className="divide-y divide-line">
        {docs.map((d) => (
          <div
            key={d.document_id}
            className="grid gap-3 px-4 py-3.5 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-center sm:px-5"
          >
            <div className="min-w-0">
              <p className="truncate text-body font-semibold text-ink">{d.title}</p>
              <div className="mt-1.5 flex flex-wrap gap-2">
                <SourceChip>{d.document_id}</SourceChip>
                <AuthorityBadge level={d.authority_level} />
              </div>
            </div>
            <span className="tabular text-label text-muted">Confidence</span>
            <span className="tabular text-caption font-semibold text-ink">{fmtPct(d.confidence)}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

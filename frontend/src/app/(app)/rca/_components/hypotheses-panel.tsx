"use client";

import { useMemo } from "react";
import { BarList } from "@/components/charts/bar-list";
import { EmptyState, RefusalCard, SourceChip } from "@/components/ui";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui-card";
import { fmtNum } from "@/lib/format";
import type { RcaHypothesis } from "@/lib/types";

const MAX_BARS = 8;

/** Ranked hypotheses: BarList of evidence weights + per-hypothesis detail rows. */
export function HypothesesPanel({ hypotheses }: { hypotheses: RcaHypothesis[] }) {
  const ranked = useMemo(
    () => [...(hypotheses ?? [])].sort((a, b) => (b.evidence_weight ?? 0) - (a.evidence_weight ?? 0)),
    [hypotheses],
  );
  const bars = useMemo(
    () =>
      ranked
        .filter((h) => !h.refused)
        .slice(0, MAX_BARS)
        .map((h) => ({
          label: h.hypothesis.length > 60 ? `${h.hypothesis.slice(0, 59)}…` : h.hypothesis,
          value: h.evidence_weight ?? 0,
        })),
    [ranked],
  );

  return (
    <Card className="overflow-hidden shadow-sm">
      <CardHeader className="border-b border-line p-4 sm:px-5">
        <CardTitle className="text-sm">Ranked hypotheses</CardTitle>
        <CardDescription>Evidence weight indicates support, not certainty.</CardDescription>
      </CardHeader>
      {ranked.length === 0 ? (
        <div className="p-4 sm:p-5">
          <EmptyState message="No hypotheses generated" />
        </div>
      ) : (
        <>
          {bars.length > 0 && (
            <div className="border-b border-line p-4 sm:p-5">
              <BarList data={bars} height={Math.max(96, bars.length * 36)} valueFormat={(v) => fmtNum(v, 2)} />
            </div>
          )}
          <div className="divide-y divide-line">
            {ranked.map((h, i) => (
              <HypothesisRow key={h.hypothesis.slice(0, 60)} h={h} rank={i + 1} />
            ))}
          </div>
        </>
      )}
    </Card>
  );
}

function HypothesisRow({ h, rank }: { h: RcaHypothesis; rank: number }) {
  if (h.refused) {
    return <RefusalCard reason={`Hypothesis #${rank}: ${h.hypothesis}`} escalateTo="Reliability Engineer" />;
  }
  return (
    <article className="p-4 sm:px-5" title={h.hypothesis}>
      <div className="flex items-baseline gap-3">
        <span className="tabular text-label font-bold text-muted">#{rank}</span>
        <p className="min-w-0 flex-1 text-body leading-relaxed text-ink">{h.hypothesis}</p>
        <span className="tabular shrink-0 text-caption font-semibold text-ink">{fmtNum(h.evidence_weight, 2)}</span>
      </div>
      {(h.sources ?? []).length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2 pl-7">
          {(h.sources ?? []).map((s) => (
            <SourceChip key={s}>{s}</SourceChip>
          ))}
        </div>
      )}
    </article>
  );
}

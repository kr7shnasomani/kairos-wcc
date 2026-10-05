"use client";

// Client-only lazy wrappers. `ssr: false` is disallowed with next/dynamic inside
// Server Components (Next 16), so these live in a "use client" module and are
// imported statically by the server pages. React Flow / browser-only UI must not SSR.
import dynamic from "next/dynamic";

export const KnowledgeGraph = dynamic(
  () => import("@/components/knowledge-graph").then((m) => m.KnowledgeGraph),
  { ssr: false, loading: () => <div className="h-[340px] animate-pulse rounded-xl bg-surface-2" /> },
);

export const BlastRadiusPanel = dynamic(
  () => import("@/components/blast-radius-panel").then((m) => m.BlastRadiusPanel),
  { ssr: false, loading: () => null },
);

export const SupersedeAction = dynamic(
  () => import("@/components/supersede-action").then((m) => m.SupersedeAction),
  { ssr: false, loading: () => null },
);

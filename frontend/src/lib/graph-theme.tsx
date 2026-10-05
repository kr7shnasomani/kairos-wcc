"use client";

// Shared color/marker helpers for the three ReactFlow canvases (knowledge-graph,
// blast-radius-panel, documents/[id]/topology). Canvas nodes/edges take concrete
// color strings, not CSS custom properties — ReactFlow's SVG/canvas layer doesn't
// live-track `var(--x)` the way DOM elements do. This resolves the Paper theme's
// tokens once per provider (not once per node) and re-resolves on theme/contrast
// toggle via a single shared MutationObserver.
import { createContext, useContext, useLayoutEffect, useState, type ReactNode } from "react";
import { MarkerType } from "@xyflow/react";

const TOKEN_NAMES = ["--accent", "--danger", "--caution", "--verified", "--info", "--muted", "--line"] as const;
export type CanvasTokenName = (typeof TOKEN_NAMES)[number];
export type CanvasTokens = Record<CanvasTokenName, string>;

// Mirror the shipped light-theme tokens in globals.css (SSR-only fallback; the
// provider reads the live computed values before first client paint).
const FALLBACK_TOKENS: CanvasTokens = {
  "--accent": "#d93400",
  "--danger": "#b42318",
  "--caution": "#9a5b00",
  "--verified": "#216d3b",
  "--info": "#1d4ed8",
  "--muted": "#3f3f3f",
  "--line": "#e5e3df",
};

function readTokens(): CanvasTokens {
  const style = getComputedStyle(document.documentElement);
  const out = { ...FALLBACK_TOKENS };
  for (const name of TOKEN_NAMES) {
    const v = style.getPropertyValue(name).trim();
    if (v) out[name] = v;
  }
  return out;
}

const CanvasTokensContext = createContext<CanvasTokens | null>(null);

export function CanvasTokensProvider({ children }: { children: ReactNode }) {
  // Initialize from the real computed tokens so the first frame is already in the
  // active palette (no light-mode flash in dark theme). Canvas consumers are
  // ssr:false, so the SSR fallback value never reaches painted DOM.
  const [tokens, setTokens] = useState<CanvasTokens>(() =>
    typeof document === "undefined" ? FALLBACK_TOKENS : readTokens(),
  );
  useLayoutEffect(() => {
    const observer = new MutationObserver(() => setTokens(readTokens()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "data-contrast"] });
    return () => observer.disconnect();
  }, []);
  return (
    <CanvasTokensContext.Provider value={tokens}>{children}</CanvasTokensContext.Provider>
  );
}

/** Concrete color strings for the current theme, for canvas (ReactFlow/SVG) consumers. */
export function useCanvasTokens(): CanvasTokens {
  return useContext(CanvasTokensContext) ?? FALLBACK_TOKENS;
}

export function arrowMarker(color: string, size = 14) {
  return { type: MarkerType.ArrowClosed, width: size, height: size, color } as const;
}

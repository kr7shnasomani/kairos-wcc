"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui";

// Shared error boundary for all (app) routes. Next bubbles a render/fetch error here.
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // Surface for debugging; no PII in these errors.
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto max-w-3xl">
      <div
        role="alert"
        className="rounded-xl border border-[color-mix(in_srgb,var(--danger)_35%,var(--line))] bg-[color-mix(in_srgb,var(--danger)_8%,var(--surface))] p-6"
      >
        <h1 className="text-title font-semibold text-danger">Something went wrong</h1>
        <p className="mt-1.5 text-body leading-relaxed text-muted">
          This screen failed to load. Your data and the evidence vault are unaffected — retry, or move to
          another screen.
        </p>
        <div className="mt-4">
          <Button variant="primary" onClick={reset}>Try again</Button>
        </div>
      </div>
    </div>
  );
}

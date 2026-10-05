"use client";

// Route-level error surface for the server-fetched assets pages (spec §8:
// error+retry). Next.js error boundaries must be client components.
import { Button } from "@/components/ui";

export default function AssetsError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="mx-auto flex max-w-[1400px] flex-col items-center gap-3 rounded-xl border border-line bg-surface px-4 py-10 text-center">
      <p className="text-body text-muted">Could not load the asset registry.</p>
      <Button variant="primary" onClick={reset}>Retry</Button>
    </div>
  );
}

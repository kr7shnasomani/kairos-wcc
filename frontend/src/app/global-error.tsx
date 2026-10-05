"use client";

// Custom global-error boundary. Next 16.2.10's *default* `_global-error` page fails
// to prerender (`TypeError: Cannot read properties of null (reading 'useContext')`),
// breaking `next build`. Providing our own overrides that default. global-error
// replaces the root layout, so it renders its own <html>/<body> and uses inline
// styles — no providers, tokens, or context-dependent components exist at this level.
export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "system-ui, -apple-system, sans-serif", background: "#f5f3f0", color: "#1a1a1a" }}>
        <main style={{ minHeight: "100dvh", display: "grid", placeItems: "center", padding: "1.25rem" }}>
          <div style={{ maxWidth: "24rem", textAlign: "center" }}>
            <div style={{ width: 48, height: 48, margin: "0 auto", borderRadius: 12, background: "#c2410c", display: "grid", placeItems: "center" }}>
              <span style={{ color: "#fff", fontSize: 26, fontWeight: 700, lineHeight: 1 }}>K</span>
            </div>
            <h1 style={{ marginTop: "1.25rem", fontSize: "1.5rem", fontWeight: 600 }}>Something went wrong</h1>
            <p style={{ marginTop: "0.5rem", color: "#6b6b6b", lineHeight: 1.5 }}>
              An unexpected error occurred. Try again, or reload the app.
            </p>
            <button
              type="button"
              onClick={reset}
              style={{ marginTop: "1.5rem", height: 40, padding: "0 1rem", borderRadius: 8, border: "none", background: "#1a1a1a", color: "#f5f3f0", fontWeight: 600, cursor: "pointer" }}
            >
              Try again
            </button>
          </div>
        </main>
      </body>
    </html>
  );
}

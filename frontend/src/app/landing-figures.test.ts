import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * The landing's eval bars carry a code comment saying they come from
 * benchmark/RESULTS.md. This proves it, so the constants cannot drift
 * from the benchmark of record unnoticed. DESIGN.md §4a.
 */
describe("landing eval figures match the benchmark of record", () => {
  const results = readFileSync(join(process.cwd(), "..", "benchmark", "RESULTS.md"), "utf8");
  const page = readFileSync(join(process.cwd(), "src", "app", "page.tsx"), "utf8");

  const badgeFor = (label: string) => {
    const m = page.match(new RegExp(`label: "${label}"[^}]*badge: "(\\d+)/(\\d+)"`));
    expect(m, `could not find the ${label} bar in page.tsx`).not.toBeNull();
    return `${m![1]}/${m![2]}`;
  };

  it("retrieval badge appears in RESULTS.md", () => {
    expect(results).toContain(badgeFor("Retrieval"));
  });

  it("provenance badge appears in RESULTS.md", () => {
    expect(results).toContain(badgeFor("Provenance"));
  });

  // Drift resolved 2026-08-22. This carried an it.fails() marker while the
  // landing showed 34/37 against RESULTS.md's 33/37. The marker was built to
  // start failing the moment the two agreed, and it did: main's landing now
  // reads 33/37 at 89%, matching the benchmark of record. Marker removed.
  it("answer-quality badge appears in RESULTS.md", () => {
    expect(results).toContain(badgeFor("Answer quality"));
  });
});

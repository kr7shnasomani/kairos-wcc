import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CompliancePage from "./page";

// Test data inlined from the deleted `lib/compliance.ts`. That module was an *application*
// fallback — api.ts served it whenever a fetch failed — which is why it was removed. Test data
// is a different thing: it never ships, and mocking the fetch is the point of the test.
//
// Declared INSIDE the vi.mock factory on purpose: `vi.mock` is hoisted above module-level
// consts, so referencing an outer variable here throws "Cannot access before initialization".
vi.mock("@/lib/api", () => {
  const gaps = [
    { concept_id: "REG-OISD-6.4", framework: "OISD_117", clause_id: "6.4", requirement_text: "Relief-device set pressure documented and current", authority_level: 1, asset_id: "P-101", equipment_class: "Centrifugal pump", severity: "critical" },
    { concept_id: "REG-OISD-7.2", framework: "OISD_117", clause_id: "7.2", requirement_text: "Seal replacement records for rotating equipment", authority_level: 2, asset_id: "EQ-101", equipment_class: "Rotating equipment", severity: "major" },
    { concept_id: "REG-ISO-7.5", framework: "ISO_45001", clause_id: "7.5", requirement_text: "Documented information controlled and versioned", authority_level: 3, asset_id: "EQ-101", equipment_class: "Rotating equipment", severity: "minor" },
  ];
  const complianceFixture = {
    items: gaps, total: gaps.length, limit: 100, offset: 0, framework: null, last_scan: "test",
  };
  return {
  getComplianceGaps: vi.fn().mockResolvedValue({ data: complianceFixture, source: "live" }),
  getComplianceDashboard: vi.fn().mockResolvedValue({
    data: {
      total_gaps: { critical: 3, major: 3, minor: 2 },
      by_framework: { OISD_117: { critical: 2, major: 2 }, ISO_45001: { critical: 1, major: 1, minor: 2 } },
      by_asset_class: {},
      last_updated: "2026-07-14T00:00:00Z",
    },
    source: "live",
  }),
  };
});

// jsdom has no matchMedia; useReducedMotion (charts) needs it.
window.matchMedia = ((query: string) => ({
  matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {},
})) as unknown as typeof window.matchMedia;

describe("CompliancePage", () => {
  afterEach(cleanup);

  it("renders KPIs, charts, gap table, and workflow link cards", async () => {
    render(<CompliancePage />);

    // Table row lands after fetch resolves.
    await screen.findByText("Relief-device set pressure documented and current");

    expect(screen.getByTestId("compliance-kpis")).toBeInTheDocument();
    expect(screen.getByText("Gaps by framework")).toBeInTheDocument();
    expect(screen.getByText("Severity mix")).toBeInTheDocument();

    // Nullable remediation cells render an em dash, never "undefined".
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);

    expect(screen.getByRole("link", { name: /Assemble audit pack/ })).toHaveAttribute("href", "/compliance/audit-pack");
    expect(screen.getByRole("link", { name: /Non-conformance register/ })).toHaveAttribute("href", "/compliance/nonconformance");
  });

  it("filters the gap register by severity", async () => {
    render(<CompliancePage />);
    await screen.findByText("Relief-device set pressure documented and current");

    fireEvent.click(screen.getByRole("button", { name: /Minor/ }));
    await waitFor(() =>
      expect(screen.queryByText("Relief-device set pressure documented and current")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("Documented information controlled and versioned")).toBeInTheDocument();
  });
});

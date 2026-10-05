import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import NonConformancePage from "./page";

const mocks = vi.hoisted(() => ({
  getConflicts: vi.fn(),
  getQuarantine: vi.fn(),
  getEvents: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getConflicts: mocks.getConflicts,
  getQuarantine: mocks.getQuarantine,
  getEvents: mocks.getEvents,
}));

function conflict(i: number) {
  return { conflict_id: `CON-${i}`, status: "open", asset_id: "P-101", parameter: "seal pressure", track: "engineering", severity: "safety_critical", is_overdue: true, created_at: "2026-07-14T00:00:00Z" };
}

function respond(conflicts: unknown[], quarantine: unknown[] = [], events: unknown[] = []) {
  mocks.getConflicts.mockResolvedValue({ data: { items: conflicts }, source: "live" });
  mocks.getQuarantine.mockResolvedValue({ data: { items: quarantine }, source: "live" });
  mocks.getEvents.mockResolvedValue({ data: { items: events }, source: "live" });
}

describe("NonConformancePage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("paginates a 10k queue to at most 25 rendered rows", async () => {
    respond(Array.from({ length: 10_000 }, (_, i) => conflict(i)));

    render(<NonConformancePage />);

    await waitFor(() => expect(screen.getAllByText("Conflict on seal pressure").length).toBeGreaterThan(0));
    expect(document.querySelectorAll("tbody tr").length).toBeLessThanOrEqual(25);
    expect(screen.getByText(/Showing 1–25 of 10000/)).toBeInTheDocument();
  });

  it("composes sources into pills, filters by source, and links to RCA", async () => {
    respond(
      [conflict(1)],
      [{ item_id: "Q-1", review_status: "disputed", asset_id: "V-247", content: "Field reading conflicts with the verified procedure", submitted_at: "2026-07-13T00:00:00Z" }],
      [{ event_id: "EV-1", event_type: "inspection_complete", asset_id: "HX-301", occurred_at: "2026-07-12T00:00:00Z", payload: { result: "failed", findings: "Tube wall loss above threshold" } }],
    );

    render(<NonConformancePage />);

    await waitFor(() => expect(screen.getByText("Conflict on seal pressure")).toBeInTheDocument());
    expect(screen.getByTestId("nonconformance-summary")).toHaveTextContent("Urgent");
    expect(screen.getAllByRole("link", { name: "Root-cause analysis" })[0]).toHaveAttribute("href", "/rca");

    fireEvent.click(screen.getByRole("button", { name: /Inspections/ }));
    await waitFor(() => expect(screen.queryByText("Conflict on seal pressure")).not.toBeInTheDocument());
    expect(screen.getByText("Inspection failed")).toBeInTheDocument();
  });

  it("shows the tailored empty state when all sources are clear", async () => {
    respond([]);

    render(<NonConformancePage />);

    await waitFor(() => expect(screen.getByText("No nonconformances open ✓")).toBeInTheDocument());
  });
});

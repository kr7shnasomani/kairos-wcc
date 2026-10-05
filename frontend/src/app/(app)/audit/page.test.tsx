import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AuditLogEntry } from "@/lib/types";
import AuditPage from "./page";

const mocks = vi.hoisted(() => ({ getAuditLog: vi.fn() }));

vi.mock("@/lib/api", () => ({ getAuditLog: mocks.getAuditLog }));

function entry(i: number, over: Partial<AuditLogEntry> = {}): AuditLogEntry {
  return {
    log_id: `AL-${i}`, entity_type: "document", entity_id: `DOC-${i}`, action: "quarantine_promoted",
    performed_by: "engineer_kiran", timestamp: "2026-07-14T10:00:00.000Z", ...over,
  };
}

function respond(items: AuditLogEntry[]) {
  mocks.getAuditLog.mockResolvedValue({ data: { items, total: items.length }, source: "live" });
}

describe("AuditPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("paginates a 10k trail to at most 25 rendered rows", async () => {
    respond(Array.from({ length: 10_000 }, (_, i) => entry(i)));

    render(<AuditPage />);

    await waitFor(() => expect(screen.getByText("AL-0")).toBeInTheDocument());
    expect(document.querySelectorAll("tbody tr").length).toBeLessThanOrEqual(25);
    expect(screen.getByText(/Showing 1–25 of 10000/)).toBeInTheDocument();
  });

  it("filters by entity type, exposes metadata via native disclosure, and exports JSON", async () => {
    respond([
      entry(1, { metadata: { authority_level: 2 } }),
      entry(2, { entity_type: "brief", entity_id: "BRIEF-1", action: "brief_acknowledged" }),
      entry(3, { entity_type: "asset", entity_id: "P-101", action: "sla_escalated", performed_by: "system" }),
    ]);

    render(<AuditPage />);

    await waitFor(() => expect(screen.getByText("AL-1")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "Export JSON" })).toHaveAttribute("download", "kairos-audit-log.json");
    expect(screen.getByText(/authority_level/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Document/ }));
    await waitFor(() => expect(screen.queryByText("AL-2")).not.toBeInTheDocument());
    expect(screen.getByText("AL-1")).toBeInTheDocument();
  });

  it("shows the empty state when there is no audit activity (live-only — no fixture)", async () => {
    respond([]);

    render(<AuditPage />);

    await waitFor(() => expect(screen.getByText("No audit activity")).toBeInTheDocument());
  });

  it("shows exact timestamps, not only relative", async () => {
    respond([entry(1)]);

    render(<AuditPage />);

    await waitFor(() => expect(screen.getByText(/2026-07-14 10:00:00/)).toBeInTheDocument());
  });

  it("does not duplicate the tab counts in cards above them", async () => {
    respond([entry(1)]);

    render(<AuditPage />);

    await waitFor(() => expect(screen.getByText("AL-1")).toBeInTheDocument());
    expect(screen.queryByTestId("audit-summary")).not.toBeInTheDocument();
  });

  it("keeps entity ids out of the alarm colour", async () => {
    respond([entry(1)]);

    render(<AuditPage />);

    const entityId = await screen.findByText("DOC-1");
    expect(entityId).toHaveClass("text-ink");
    expect(entityId).not.toHaveClass("text-danger", "text-accent");
  });
});

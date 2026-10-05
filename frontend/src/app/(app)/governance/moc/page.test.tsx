import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MocItem } from "@/lib/types";
import MocListPage from "./page";

const mocks = vi.hoisted(() => ({ getMocList: vi.fn(), push: vi.fn() }));

vi.mock("@/lib/api", () => ({ getMocList: mocks.getMocList }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));

function item(i: number, over: Partial<MocItem> = {}): MocItem {
  return {
    moc_id: `MOC-${i}`, asset_id: `P-${i}`, parameter: "operating_pressure",
    source_a: { value: "1" }, source_b: { value: "2" }, blast_radius_count: 0,
    status: "pending", created_at: "2026-07-01T00:00:00Z", draft_content: null, ...over,
  };
}

describe("MocListPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("paginates a 10k register to at most 25 rendered rows", async () => {
    mocks.getMocList.mockResolvedValue({ data: { items: Array.from({ length: 10_000 }, (_, i) => item(i)), total: 10_000 }, source: "live" });

    render(<MocListPage />);

    await waitFor(() => expect(screen.getByText("MOC-0")).toBeInTheDocument());
    expect(document.querySelectorAll("tbody tr").length).toBeLessThanOrEqual(25);
    expect(screen.getByText(/Showing 1–25 of 10000/)).toBeInTheDocument();
  });

  it("renders an honest empty state for an empty live list — never fabricated rows", async () => {
    // Inverted deliberately. This used to assert the opposite: an empty *successful* response
    // rendered buildFixture() — MOC-2024-001 and friends, invented ids and document refs —
    // behind a "Demo data" chip. Fabricating records on a successful request is precisely what
    // the live-only policy forbids, so the page now shows its empty state.
    mocks.getMocList.mockResolvedValue({ data: { items: [], total: 0 }, source: "live" });

    render(<MocListPage />);

    await waitFor(() => expect(screen.getByText("No changes under review")).toBeInTheDocument());
    expect(screen.queryByText("MOC-2024-001")).not.toBeInTheDocument();
    expect(screen.queryByText("Demo data")).not.toBeInTheDocument();
  });

  it("routes a row click to the case file", async () => {
    mocks.getMocList.mockResolvedValue({ data: { items: [item(1)], total: 1 }, source: "live" });

    render(<MocListPage />);

    const row = await screen.findByText("MOC-1");
    fireEvent.click(row.closest("tr")!);
    expect(mocks.push).toHaveBeenCalledWith("/governance/moc/MOC-1");
  });

  it("shows an error surface with retry when the fetch rejects", async () => {
    mocks.getMocList.mockRejectedValueOnce(new Error("offline"));
    mocks.getMocList.mockResolvedValue({ data: { items: [item(1)], total: 1 }, source: "live" });

    render(<MocListPage />);

    const retry = await screen.findByRole("button", { name: "Retry" });
    fireEvent.click(retry);
    await waitFor(() => expect(screen.getByText("MOC-1")).toBeInTheDocument());
  });
});

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CircuitBreakerPage from "./page";

const mocks = vi.hoisted(() => ({ getCircuitBreaker: vi.fn() }));

vi.mock("@/lib/api", () => ({ getCircuitBreaker: mocks.getCircuitBreaker }));

const LIVE_STATE = {
  halted_count: 1,
  states: [
    { asset_class: "Pump", halted: false, z_score: 1.2, override_count_7d: 0, reason: "within_normal_range" },
    { asset_class: "Valve", halted: true, z_score: 3.8, override_count_7d: 4, reason: "z_score_exceeded" },
  ],
};

describe("CircuitBreakerPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("presents asset-class safeguards as metric strip, ranked chart, and table", async () => {
    mocks.getCircuitBreaker.mockResolvedValue({ data: LIVE_STATE, source: "live" });

    render(<CircuitBreakerPage />);

    await waitFor(() => expect(screen.getByText("Valve")).toBeInTheDocument());
    expect(screen.getByTestId("circuit-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByTestId("circuit-summary")).toHaveClass("lg:grid-cols-4");
    expect(screen.getByTestId("circuit-layout")).toHaveClass("lg:grid-cols-[minmax(0,1fr)_300px]");
    expect(screen.getByTestId("circuit-monitor")).toHaveTextContent("Valve");
    expect(screen.getByTestId("circuit-context")).toHaveTextContent("What triggers a halt?");
    // Halted classes are visually distinct and z-scores never render NaN.
    expect(screen.getAllByText("halted").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByTestId("circuit-workspace")).not.toHaveTextContent("NaN");
    expect(screen.getAllByText("3.8σ").length).toBeGreaterThanOrEqual(1);
  });

  // Inverted from the original assertion, which expected the page to render "Separator" — a row
  // that existed only in a hardcoded FIXTURE served whenever the live response was null. That is
  // fabricated governance state on the page whose entire job is reporting whether extraction has
  // actually been halted. The guarantee is now pinned the other way.
  it("renders no fabricated breakers when the live response is empty", async () => {
    mocks.getCircuitBreaker.mockResolvedValue({ data: null, source: "live" });

    render(<CircuitBreakerPage />);

    await waitFor(() => expect(screen.getByTestId("circuit-workspace")).toBeInTheDocument());
    const workspace = screen.getByTestId("circuit-workspace");
    for (const invented of ["Separator", "Instrument", "Vessel", "Pump", "Valve"]) {
      expect(workspace).not.toHaveTextContent(invented);
    }
    expect(screen.queryAllByText("halted")).toHaveLength(0);
    expect(workspace).not.toHaveTextContent("NaN");
  });

  it("shows an error banner with retry when the fetcher rejects", async () => {
    mocks.getCircuitBreaker.mockRejectedValue(new Error("backend down"));

    render(<CircuitBreakerPage />);

    await waitFor(() => expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument());
    expect(screen.getByTestId("circuit-workspace")).toHaveTextContent("Couldn’t load circuit-breaker state.");
  });
});

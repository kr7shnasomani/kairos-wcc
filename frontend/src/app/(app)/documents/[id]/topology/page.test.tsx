import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import TopologyPage from "./page";

vi.mock("next/navigation", () => ({ useParams: () => ({ id: "DOC-1" }) }));
vi.mock("@/lib/api", () => ({
  getDocumentTopology: vi.fn().mockResolvedValue({
    data: {
      document_id: "DOC-1", generated_at: "2026-07-15T08:00:00Z",
      nodes: [{ node_id: "P-101", node_type: "Pump", label: "P-101", verification_status: "verified", properties: {} }],
      edges: [],
      verification_status: "partially_verified",
      elements_total: 2, elements_verified: 1, elements_disputed: 0,
      safety_critical_total: 1, safety_critical_verified: 0,
      canonical_ready: false,
    },
    source: "api",
  }),
  verifyTopologyElements: vi.fn(),
  // Pulled in transitively via useRole -> getMe; the whole-module mock would otherwise
  // leave it undefined and the effect throws.
  getToken: vi.fn(() => null),
}));
vi.mock("@/lib/graph-theme", () => ({
  useCanvasTokens: () => ({ "--info": "blue", "--accent": "purple", "--verified": "green", "--caution": "orange", "--danger": "red", "--muted": "gray", "--line": "gray" }),
  arrowMarker: () => undefined,
}));
vi.mock("@xyflow/react", () => ({
  ReactFlow: ({ children }: { children: React.ReactNode }) => <div data-testid="flow-canvas">{children}</div>,
  Background: () => null,
  Controls: () => <div>Controls</div>,
  Handle: () => null,
  Position: { Top: "top", Bottom: "bottom" },
  useNodesState: () => [[], vi.fn(), vi.fn()],
  useEdgesState: () => [[], vi.fn(), vi.fn()],
}));

describe("TopologyPage", () => {
  afterEach(cleanup);

  it("uses a responsive topology investigation workspace", async () => {
    render(<TopologyPage />);
    await waitFor(() => expect(screen.getByText("Elements (1)")).toBeInTheDocument());

    expect(screen.getByTestId("topology-workspace")).toHaveClass("max-w-[1400px]");
    expect(screen.getByTestId("topology-layout")).toHaveClass("lg:grid-cols-[minmax(0,1fr)_280px]");
    expect(screen.getByTestId("topology-canvas")).toHaveClass("min-h-[420px]");
    expect(screen.getByTestId("topology-context")).toHaveTextContent("Verification key");
    expect(screen.getByTestId("topology-register")).toHaveTextContent("P-101");
  });
});

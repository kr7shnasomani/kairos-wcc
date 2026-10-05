import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AuditPackClause } from "@/lib/types";
import AuditPackPage from "./page";

const mocks = vi.hoisted(() => ({ getAuditPack: vi.fn() }));

vi.mock("@/lib/api", () => ({ getAuditPack: mocks.getAuditPack }));

function clause(i: number, over: Partial<AuditPackClause> = {}): AuditPackClause {
  return {
    clause_id: `6.${i}`, requirement_text: `Requirement ${i}`, applies_to: "Rotating equipment",
    authority_level: 1, severity: "critical",
    evidence: [{ document_id: `DOC-${i}`, document_type: "procedure", confidence: 0.96, verification_status: "verified" }],
    verified_evidence_count: 1, clearance_blocked: false, ...over,
  };
}

function respond(clauses: AuditPackClause[]) {
  mocks.getAuditPack.mockResolvedValue({
    data: {
      framework: "OISD-117", clauses, total_clauses: clauses.length,
      total_evidence_docs: clauses.length, human_review_required: [],
    },
    source: "live",
  });
}

describe("AuditPackPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("paginates a 10k clause register to at most 25 rendered rows", async () => {
    respond(Array.from({ length: 10_000 }, (_, i) => clause(i)));

    render(<AuditPackPage />);

    await waitFor(() => expect(screen.getByText("OISD-117 §6.0")).toBeInTheDocument());
    expect(document.querySelectorAll("tbody tr").length).toBeLessThanOrEqual(25);
    expect(screen.getByText(/Showing 1–25 of 10000/)).toBeInTheDocument();
  });

  it("keeps evidence links, confidence, and clearance status per clause", async () => {
    respond([clause(4), clause(5, { clearance_blocked: true, evidence: [], verified_evidence_count: 0 })]);

    render(<AuditPackPage />);

    await waitFor(() => expect(screen.getByTestId("audit-pack-summary")).toHaveTextContent("Human review"));
    expect(screen.getByRole("link", { name: "DOC-4" })).toHaveAttribute("href", "/documents/DOC-4");
    expect(screen.getByText("96%")).toBeInTheDocument();
    expect(screen.getByText("Requires human review")).toBeInTheDocument();
    expect(screen.getByText("No supporting evidence")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Print / export PDF" })).toBeInTheDocument();
  });

  it("shows the tailored empty state with an ingest CTA", async () => {
    respond([]);

    render(<AuditPackPage />);

    await waitFor(() => expect(screen.getByText("No audit packs generated")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "Ingest a document" })).toHaveAttribute("href", "/documents/ingest");
  });
});

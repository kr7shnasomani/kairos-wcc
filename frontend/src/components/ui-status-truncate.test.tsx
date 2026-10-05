import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { statusTone, Truncate } from "./ui";

describe("statusTone — colour tracks severity (DESIGN.md 2.3)", () => {
  it("maps faults and overdue to danger", () => {
    for (const s of ["open", "overdue", "critical", "disputed", "rejected", "safety_critical"]) {
      expect(statusTone(s), s).toBe("danger");
    }
  });

  it("maps awaiting-action states to caution", () => {
    for (const s of ["pending", "pending_approval", "pending_moc", "quarantined", "high"]) {
      expect(statusTone(s), s).toBe("caution");
    }
  });

  it("maps monitoring states to info", () => {
    for (const s of ["monitor", "in_progress", "scheduled", "normal"]) {
      expect(statusTone(s), s).toBe("info");
    }
  });

  it("maps review states to validation", () => {
    for (const s of ["validation", "under_review", "questions_ready"]) {
      expect(statusTone(s), s).toBe("validation");
    }
  });

  it("maps settled states to verified", () => {
    for (const s of ["verified", "approved", "promoted", "active", "completed", "resolved"]) {
      expect(statusTone(s), s).toBe("verified");
    }
  });

  it("gives low severity the least weight, never danger", () => {
    for (const s of ["low", "non_critical", "archived", "superseded", "cancelled"]) {
      expect(statusTone(s), s).toBe("neutral");
    }
  });

  it("falls back to neutral for anything unrecognised", () => {
    expect(statusTone("something_new")).toBe("neutral");
  });
});

describe("Truncate", () => {
  it("exposes the full text via title", () => {
    render(<Truncate text="seal_series_MS44_service_bulletin_r3.pdf" />);
    expect(screen.getByTitle("seal_series_MS44_service_bulletin_r3.pdf")).toBeInTheDocument();
  });

  it("supports two-line clamping", () => {
    render(<Truncate text="A very long node label that wraps" lines={2} />);
    expect(screen.getByTitle("A very long node label that wraps").className).toMatch(/line-clamp-2/);
  });

  it("renders an em dash for absent text", () => {
    const { container } = render(<Truncate text={null} />);
    expect(container.textContent).toBe("—");
  });
});

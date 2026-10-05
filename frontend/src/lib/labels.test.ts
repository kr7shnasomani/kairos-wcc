import { describe, expect, it } from "vitest";
import { label, labelOf, plural } from "./labels";

describe("label", () => {
  it("humanises snake_case", () => {
    expect(label("deviation_flag")).toBe("Deviation flag");
    expect(label("work_order_created")).toBe("Work order created");
  });

  it("applies overrides where the naive humanisation would be wrong", () => {
    expect(label("he-3xx_series")).toBe("HE-3xx series");
    expect(label("non_critical")).toBe("Non-critical");
    expect(label("safety_critical")).toBe("Safety-critical");
    expect(label("pid_drawing")).toBe("P&ID drawing");
    expect(label("oem_manual")).toBe("OEM manual");
    expect(label("ptw")).toBe("PTW");
    expect(label("pending_moc")).toBe("Pending MoC");
  });

  it("returns an em dash for absent values", () => {
    expect(label(null)).toBe("—");
    expect(label(undefined)).toBe("—");
    expect(label("")).toBe("—");
  });

  it("never leaks raw snake_case to the screen", () => {
    const raw = [
      "valve_isolation",
      "instrument_bypass",
      "rotating_centrifugal_pump",
      "elicitation_response",
      "offboarding_response",
      "questions_ready",
      "pending_approval",
      "manual_correction",
      "human_promotion",
    ];
    for (const v of raw) {
      expect(label(v), `${v} still contains an underscore`).not.toContain("_");
    }
  });
});

describe("labelOf", () => {
  it("delegates to label for known values", () => {
    expect(labelOf("criticality", "non_critical")).toBe("Non-critical");
    expect(labelOf("document_status", "superseded")).toBe("Superseded");
  });

  it("falls back to the generic humaniser for unknown values", () => {
    expect(labelOf("equipment_class", "brand_new_class")).toBe("Brand new class");
  });
});

describe("plural", () => {
  it("does not pluralise a count of one", () => {
    expect(plural(1, "signal")).toBe("1 signal");
    expect(plural(1, "active programme")).toBe("1 active programme");
  });

  it("pluralises everything else", () => {
    expect(plural(0, "signal")).toBe("0 signals");
    expect(plural(3, "signal")).toBe("3 signals");
  });

  it("accepts an explicit plural form", () => {
    expect(plural(2, "entry", "entries")).toBe("2 entries");
    expect(plural(1, "entry", "entries")).toBe("1 entry");
  });
});

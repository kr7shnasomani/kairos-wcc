import { describe, expect, it } from "vitest";
import { fmtCompact, fmtNum, fmtPct, fmtRelTime } from "./format";

describe("format guards", () => {
  it("fmtNum formats and guards bad input", () => {
    expect(fmtNum(12400)).toBe("12,400");
    expect(fmtNum(3.14159, 2)).toBe("3.14");
    expect(fmtNum(null)).toBe("—");
    expect(fmtNum(undefined)).toBe("—");
    expect(fmtNum(NaN)).toBe("—");
    expect(fmtNum(Infinity)).toBe("—");
  });

  it("fmtPct scales ratios, passes percents, guards bad input", () => {
    expect(fmtPct(0.82)).toBe("82%");
    expect(fmtPct(82)).toBe("82%");
    expect(fmtPct(-0.5)).toBe("-50%");
    expect(fmtPct(0.825, 1)).toBe("82.5%");
    expect(fmtPct(null)).toBe("—");
    expect(fmtPct(NaN)).toBe("—");
    expect(fmtPct(-Infinity)).toBe("—");
  });

  it("fmtCompact abbreviates and guards", () => {
    expect(fmtCompact(12400)).toBe("12.4K");
    expect(fmtCompact(999)).toBe("999");
    expect(fmtCompact(null)).toBe("—");
    expect(fmtCompact(NaN)).toBe("—");
  });

  it("fmtRelTime delegates and guards bad ISO", () => {
    expect(fmtRelTime(new Date(Date.now() - 3600_000).toISOString())).toMatch(/ago|just now/);
    expect(fmtRelTime(null)).toBe("—");
    expect(fmtRelTime(undefined)).toBe("—");
    expect(fmtRelTime("not-a-date")).toBe("—");
  });
});

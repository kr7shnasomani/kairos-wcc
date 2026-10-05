import { describe, expect, it } from "vitest";
import { downsample } from "./charts";

describe("downsample", () => {
  it("passes small data through untouched", () => {
    const data = [1, 2, 3];
    expect(downsample(data, 500)).toBe(data);
  });

  it("caps at max and keeps first and last points", () => {
    const data = Array.from({ length: 5000 }, (_, i) => i);
    const out = downsample(data, 500);
    expect(out.length).toBeLessThanOrEqual(501);
    expect(out[0]).toBe(0);
    expect(out[out.length - 1]).toBe(4999);
  });
});

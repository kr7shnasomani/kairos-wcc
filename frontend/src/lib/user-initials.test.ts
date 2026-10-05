import { describe, expect, it } from "vitest";
import { getUserInitials } from "./user-initials";

describe("getUserInitials", () => {
  it("uses initials from a separated email local-part", () => {
    expect(getUserInitials("jane.doe@kairos.example")).toBe("JD");
  });

  it("uses the first two characters when no separator is available", () => {
    expect(getUserInitials("engineer@kairos.example")).toBe("EN");
  });

  it("uses both words from the visible account name", () => {
    expect(getUserInitials("Kairos user")).toBe("KU");
  });
});

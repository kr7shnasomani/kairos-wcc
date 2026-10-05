import { describe, expect, it } from "vitest";
import { getSearchShortcut } from "./search-shortcut";

describe("getSearchShortcut", () => {
  it("uses Command on Apple platforms", () => {
    expect(getSearchShortcut("MacIntel")).toBe("⌘ K");
  });

  it("uses Ctrl on non-Apple platforms", () => {
    expect(getSearchShortcut("Win32")).toBe("Ctrl K");
  });
});

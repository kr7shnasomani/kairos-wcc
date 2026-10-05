import { describe, expect, it } from "vitest";
import { META_MODEL, metaAnswer } from "./copilot";

describe("metaAnswer", () => {
  it("answers 'what can you do?' locally, with no sources and a meta marker", () => {
    const a = metaAnswer("what can you do?");
    expect(a).not.toBeNull();
    expect(a!.model).toBe(META_MODEL);
    expect(a!.sources).toEqual([]);
    expect(a!.refused).toBe(false);
    expect(a!.answer).toMatch(/governed/i);
  });

  it("answers a bare greeting", () => {
    for (const greeting of ["hi", "Hello", "hey there", "good morning"]) {
      expect(metaAnswer(greeting), greeting).not.toBeNull();
    }
  });

  // The important one. If the meta matcher ever swallowed a plant question, the copilot would
  // answer it from a hardcoded string instead of governed sources — and for a safety-critical
  // parameter it would bypass the refusal gate entirely. Everything here must reach retrieval.
  it("never intercepts a plant question", () => {
    const plantQuestions = [
      "What's the failure history of P-101?",
      "Maximum allowable pressure for the HE-3xx series?",
      "Isolation points for work on V-247",
      "Open compliance gaps on P-101",
      "What seal part number was used for EQ-101 before the revision?",
      "Which OEM manufactures the feed pumps at the site?",
      "when was isolation valve XV-203 last inspected?",
      // contains "help" as a substring of a real word — must not match the help pattern
      "Which document helped identify the seal failure?",
      // asks what a *pump* does, not what the assistant does
      "what does the standby pump do during a trip?",
    ];
    for (const q of plantQuestions) {
      expect(metaAnswer(q), q).toBeNull();
    }
  });

  it("describes refusal behaviour, so the capability answer does not oversell", () => {
    const a = metaAnswer("what can you do");
    expect(a!.answer).toMatch(/refuse/i);
    expect(a!.answer).toMatch(/safety-critical/i);
  });
});

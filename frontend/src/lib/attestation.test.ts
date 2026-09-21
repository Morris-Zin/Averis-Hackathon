import { describe, expect, it } from "vitest";
import { shouldResetVerification } from "./attestation";

describe("OCR attestation", () => {
  it("resets verification when transcription text changes", () => {
    expect(shouldResetVerification("hello", "hello!", ["b1"], ["b1"])).toBe(
      true,
    );
    expect(shouldResetVerification("hello", "hello", ["b1"], ["b1"])).toBe(
      false,
    );
  });

  it("resets verification when selected evidence changes", () => {
    expect(
      shouldResetVerification("hello", "hello", ["b1"], ["b1", "b2"]),
    ).toBe(true);
    expect(shouldResetVerification("hello", "hello", ["b1"], ["b2"])).toBe(
      true,
    );
  });
});

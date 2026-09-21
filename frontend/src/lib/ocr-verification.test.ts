import { describe, expect, it } from "vitest";
import { shouldResetOcrVerification } from "./ocr-verification";

describe("OCR verification", () => {
  it("resets verification when transcription text changes", () => {
    expect(shouldResetOcrVerification("hello", "hello!", ["b1"], ["b1"])).toBe(
      true,
    );
    expect(shouldResetOcrVerification("hello", "hello", ["b1"], ["b1"])).toBe(
      false,
    );
  });

  it("resets verification when selected evidence changes", () => {
    expect(
      shouldResetOcrVerification("hello", "hello", ["b1"], ["b1", "b2"]),
    ).toBe(true);
    expect(shouldResetOcrVerification("hello", "hello", ["b1"], ["b2"])).toBe(
      true,
    );
  });
});

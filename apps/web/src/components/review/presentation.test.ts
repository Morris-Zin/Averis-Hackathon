import { describe, expect, it } from "vitest";
import { confidenceDisplay } from "./presentation";

function classification(source: "model" | "human" | "fixture") {
  return {
    suggested: "BL_COMPARISON" as const,
    accepted: null,
    confidence: 0.82,
    probabilities: { BL_COMPARISON: 0.82 },
    source,
    model: "jev-test",
    policy_version: "classification-v1",
  };
}

describe("confidenceDisplay", () => {
  it("returns null without a classification", () => {
    expect(confidenceDisplay(null)).toBeNull();
    expect(confidenceDisplay(undefined)).toBeNull();
  });
  it("labels model output as AI certainty, not accuracy", () => {
    const display = confidenceDisplay(classification("model"));
    expect(display?.kind).toBe("ai");
    expect(display?.percent).toBe(82);
    expect(display?.headline).toContain("82%");
    expect(display?.detail).toContain("not measured accuracy");
  });
  it("labels human decisions as reviewer classified with the original suggestion", () => {
    const display = confidenceDisplay(classification("human"));
    expect(display?.kind).toBe("reviewer");
    expect(display?.headline).toBe("Reviewer classified");
    expect(display?.detail).toContain("Shipping instruction check");
    expect(display?.detail).toContain("82%");
  });
  it("marks fixtures as illustrative demo values", () => {
    const display = confidenceDisplay(classification("fixture"));
    expect(display?.kind).toBe("demo");
    expect(display?.detail).toContain("Illustrative demo value");
  });
});

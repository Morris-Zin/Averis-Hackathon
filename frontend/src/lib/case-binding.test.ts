import { describe, expect, it } from "vitest";
import {
  isActionAllowed,
  shouldIgnoreLateResponse,
  shouldInvalidateOnNavigate,
} from "./case-binding";

describe("case binding", () => {
  it("failed A->B navigation never exposes actions against the previous case", () => {
    // Navigating invalidates; a failed load leaves no visible case.
    expect(shouldInvalidateOnNavigate("case-a", "case-b")).toBe(true);
    expect(shouldInvalidateOnNavigate("case-a", "case-a")).toBe(false);
    // Previous case must not remain actionable under the new request.
    expect(isActionAllowed("case-b", "case-a")).toBe(false);
    expect(isActionAllowed("case-b", null)).toBe(false);
    expect(isActionAllowed("case-b", "case-b")).toBe(true);
  });

  it("late responses for another case or version are ignored", () => {
    expect(shouldIgnoreLateResponse("case-b", "case-a", 1, 2)).toBe(true);
    expect(shouldIgnoreLateResponse("case-b", "case-b", 1, 2)).toBe(true);
    expect(shouldIgnoreLateResponse("case-b", "case-b", 2, 2)).toBe(false);
  });

  it("mutations bind to the requested case id", () => {
    const requested = "case-b";
    const staleItemId = "case-a";
    expect(isActionAllowed(requested, staleItemId)).toBe(false);
    expect(isActionAllowed(requested, requested)).toBe(true);
  });
});

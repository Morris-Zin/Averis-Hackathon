import { describe, expect, it } from "vitest";
import {
  isRequestedCaseLoaded,
  shouldIgnoreLateResponse,
  shouldInvalidateOnNavigate,
} from "./case-request-guards";

describe("case request guards", () => {
  it("failed A->B navigation never exposes actions against the previous case", () => {
    // Navigating invalidates; a failed load leaves no visible case.
    expect(shouldInvalidateOnNavigate("case-a", "case-b")).toBe(true);
    expect(shouldInvalidateOnNavigate("case-a", "case-a")).toBe(false);
    // Previous case must not remain actionable under the new request.
    expect(isRequestedCaseLoaded("case-b", "case-a")).toBe(false);
    expect(isRequestedCaseLoaded("case-b", null)).toBe(false);
    expect(isRequestedCaseLoaded("case-b", "case-b")).toBe(true);
  });

  it("late responses for another case or sequence are ignored", () => {
    expect(shouldIgnoreLateResponse("case-b", "case-a", 1, 2)).toBe(true);
    expect(shouldIgnoreLateResponse("case-b", "case-b", 1, 2)).toBe(true);
    expect(shouldIgnoreLateResponse("case-b", "case-b", 2, 2)).toBe(false);
  });

  it("mutations bind to the requested case id", () => {
    const requested = "case-b";
    const staleItemId = "case-a";
    expect(isRequestedCaseLoaded(requested, staleItemId)).toBe(false);
    expect(isRequestedCaseLoaded(requested, requested)).toBe(true);
  });
});

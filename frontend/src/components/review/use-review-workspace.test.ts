import { act, renderHook, waitFor, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CaseView } from "@/lib/contracts";
import { useReviewWorkspace } from "./use-review-workspace";

const mocks = vi.hoisted(() => ({
  api: { case: vi.fn() },
  poll: undefined as undefined | ((signal: AbortSignal) => Promise<boolean>),
}));
vi.mock("../session-provider", () => ({
  useSession: () => ({
    status: "ready",
    session: null,
    api: mocks.api,
    sessionActionPending: false,
  }),
}));
vi.mock("@/lib/use-active-polling", () => ({
  useActivePolling: (
    _enabled: boolean,
    poll: (signal: AbortSignal) => Promise<boolean>,
  ) => {
    mocks.poll = poll;
  },
}));
const queued: CaseView = {
  id: "test-case",
  subject: "Test",
  sender: "test@example.com",
  body: "Test",
  received_at: "2026-09-20T00:00:00Z",
  revision: 1,
  input_revision: 1,
  processing: "queued",
  stage: "queued",
  processing_attempts: 0,
  workflow: "open",
  assignee: "John",
  review_reasons: [],
  attachments: [],
  history: [],
  summary: { kind: "queued", mismatches: 0 },
};
const classified: CaseView = {
  ...queued,
  summary: { kind: "running", mismatches: 0 },
  processing: "running",
  stage: "classified",
  revision: 2,
  classification: {
    suggested: "BL_COMPARISON",
    accepted: null,
    confidence: 0.82,
    probabilities: { BL_COMPARISON: 0.82, GENERAL: 0.18 },
    source: "model",
    model: "jev-test",
    policy_version: "classification-v1",
  },
  attachments: [],
};
const completed: CaseView = {
  ...queued,
  summary: { kind: "categorized", mismatches: 0 },
  processing: "completed",
  revision: 2,
  classification: {
    suggested: "INVOICE_QUERY",
    accepted: "INVOICE_QUERY",
    confidence: 1,
    probabilities: { INVOICE_QUERY: 1 },
    source: "model",
    model: "test",
    policy_version: "test",
  },
  attachments: [
    { id: "si-new", filename: "SI.txt", role: "SI", superseded: false },
    { id: "bl-new", filename: "BL.txt", role: "BL", superseded: false },
  ],
};
afterEach(cleanup);
beforeEach(() => {
  mocks.api.case.mockReset();
  mocks.api.case.mockResolvedValue(queued);
});
async function deliverWorkerResult() {
  mocks.api.case.mockResolvedValue(completed);
  await act(async () => {
    await mocks.poll?.(new AbortController().signal);
  });
}
async function deliverIntermediateClassification() {
  mocks.api.case.mockResolvedValue(classified);
  await act(async () => {
    await mocks.poll?.(new AbortController().signal);
  });
}
describe("review controls during worker updates", () => {
  it("updates untouched category and pair controls when processing completes", async () => {
    const { result } = renderHook(() => useReviewWorkspace("test-case"));
    await waitFor(() => expect(result.current.item?.processing).toBe("queued"));
    await deliverWorkerResult();
    expect(result.current.category.categoryDraft).toBe("INVOICE_QUERY");
    expect(result.current.documents.pairSi).toBe("si-new");
    expect(result.current.documents.pairBl).toBe("bl-new");
    expect(result.current.documents.pairChanged).toBe(false);
  });
  it("shows classifying until a real classification exists", async () => {
    const { result } = renderHook(() => useReviewWorkspace("test-case"));
    await waitFor(() => expect(result.current.item?.processing).toBe("queued"));
    expect(result.current.category.classifying).toBe(true);
    await deliverWorkerResult();
    expect(result.current.category.classifying).toBe(false);
  });
  it("follows an intermediate classification while extraction still runs", async () => {
    const { result } = renderHook(() => useReviewWorkspace("test-case"));
    await waitFor(() => expect(result.current.item?.processing).toBe("queued"));
    await deliverIntermediateClassification();
    expect(result.current.item?.processing).toBe("running");
    expect(result.current.item?.report).toBeUndefined();
    expect(result.current.category.classifying).toBe(false);
    expect(result.current.category.categoryDraft).toBe("BL_COMPARISON");
    expect(result.current.category.classificationConfidence).toBe(82);
  });
  it("preserves explicit reviewer choices across an intermediate update", async () => {
    const { result } = renderHook(() => useReviewWorkspace("test-case"));
    await waitFor(() => expect(result.current.item?.processing).toBe("queued"));
    act(() => {
      result.current.category.setCategoryDraft("SI_REQUEST");
    });
    await deliverIntermediateClassification();
    expect(result.current.category.categoryDraft).toBe("SI_REQUEST");
  });
  it("preserves explicit reviewer choices while the server result changes", async () => {
    const { result } = renderHook(() => useReviewWorkspace("test-case"));
    await waitFor(() => expect(result.current.item?.processing).toBe("queued"));
    act(() => {
      result.current.category.setCategoryDraft("SI_REQUEST");
      result.current.documents.setPairSi("reviewer-si");
      result.current.documents.setPairBl("");
    });
    await deliverWorkerResult();
    expect(result.current.category.categoryDraft).toBe("SI_REQUEST");
    expect(result.current.documents.pairSi).toBe("reviewer-si");
    expect(result.current.documents.pairBl).toBe("");
    expect(result.current.documents.pairChanged).toBe(true);
  });
});

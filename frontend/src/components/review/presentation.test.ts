import { describe, expect, it } from "vitest";
import type { CaseView } from "@/lib/contracts";
import {
  confidenceDisplay,
  readingProvenanceLabel,
  readingIssueLabel,
  issueLabel,
  resultSummary,
} from "./presentation";

const unreadableCase: CaseView = {
  id: "broken",
  subject: "Unreadable source",
  sender: "test@example.test",
  body: "Compare documents",
  received_at: "2026-09-22T00:00:00Z",
  revision: 1,
  input_revision: 1,
  processing: "completed",
  stage: "complete",
  processing_attempts: 1,
  workflow: "open",
  assignee: "John Tan",
  attachments: [],
  history: [],
  summary: { kind: "needs_review", mismatches: 0 },
  review_reasons: [
    "A comparison document could not be read. Replace it with a readable SI or draft BL.",
    "Document cannot be reliably extracted",
    "document_unreadable:PdfminerException",
  ],
};

it("explains stored parser failures without exposing diagnostics or changing data", () => {
  const original = structuredClone(unreadableCase);
  const detail = resultSummary(unreadableCase).detail;
  expect(detail).toContain("Ask the document operator");
  expect(detail).toContain("case reference");
  expect(detail).not.toContain("PdfminerException");
  expect(detail).not.toContain("document_unreadable");
  expect(detail.match(/could not be read/g)).toHaveLength(1);
  expect(unreadableCase).toEqual(original);
  expect(
    issueLabel({
      code: "document_unreadable",
      detail: "PdfminerException",
      scope: "unused_attachment",
      blocking: false,
    }),
  ).toContain("Unused attachment:");
  expect(
    issueLabel({
      code: "document_unreadable",
      detail: "PdfminerException",
      scope: "document",
      blocking: true,
    }),
  ).not.toContain("PdfminerException");
});

it("gives missing-document recovery guidance while preserving other review reasons", () => {
  const detail = resultSummary({
    ...unreadableCase,
    review_reasons: [
      "Waiting for documents: attach a Shipping Instruction and draft BL. Not checked yet.",
      "Another unresolved source issue",
    ],
  }).detail;
  expect(detail).toContain("Shipping documents are missing");
  expect(detail).toContain("Ask the document operator");
  expect(detail).toContain("Another unresolved source issue");
  expect(
    resultSummary({
      ...unreadableCase,
      summary: { kind: "mismatch_review", mismatches: 1 },
    }).label,
  ).toBe("1 mismatch; review also required");
});

it("keeps high AI certainty separate from failed source validation", () => {
  const reading = {
    field: "shipper" as const,
    document_id: "si",
    confidence: 1,
    provenance: "machine" as const,
    acceptance_basis: "probability" as const,
    issue: "ambiguous_source_fields",
  };
  expect(readingProvenanceLabel(reading)).toContain(
    "100% AI selection confidence",
  );
  expect(readingProvenanceLabel(reading)).toContain("requires review");
  expect(readingIssueLabel(reading.issue)).toContain("Several fields");
  expect(
    readingProvenanceLabel({
      ...reading,
      confidence: null,
      acceptance_basis: "explicit_source",
    }),
  ).not.toContain("passed");
  expect(readingIssueLabel("future_reason")).toContain("Check the source");
});

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
    const display = confidenceDisplay({
      ...classification("human"),
      accepted: "BL_COMPARISON",
    });
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
  it("does not call a human spam rejection an accepted classification", () => {
    const display = confidenceDisplay({
      ...classification("human"),
      suggested: "SPAM",
    });
    expect(display?.headline).toContain("category required");
    expect(display?.detail).toContain("Spam");
  });
});

it("does not turn absent DeepSeek confidence into a percentage", () => {
  const reading = {
    field: "shipper" as const,
    document_id: "source",
    confidence: null,
    provenance: "machine" as const,
    acceptance_basis: "explicit_source" as const,
  };
  expect(readingProvenanceLabel(reading)).toBe(
    "Selected by DeepSeek · source checks passed",
  );
  expect(
    readingProvenanceLabel({ ...reading, assistance_error: "unavailable" }),
  ).toContain("unavailable");
});

describe("numeric source readings", () => {
  it("shows the chosen number while retaining the original block in evidence", async () => {
    const { readingDisplayValue } = await import("./presentation");
    const reading = {
      field: "gross_weight_kg" as const,
      acceptance_basis: "probability" as const,
      confidence: 0.9,
      provenance: "machine" as const,
      document_id: "pdf",
      text: "Containers: 4\nGross Weightnn: 117770 kg",
      normalized: "117770",
      numeric_selection: { block_id: "b1", start: 30, end: 36 },
    };
    expect(readingDisplayValue(reading)).toBe("117770 kg");
    expect(
      readingDisplayValue({
        ...reading,
        field: "container_count",
        normalized: "4",
      }),
    ).toBe("4");
    expect(readingDisplayValue({ ...reading, numeric_selection: null })).toBe(
      reading.text,
    );
    expect(readingDisplayValue()).toBe("Not found");
  });
});

it("discloses the kilogram default without changing the source text", async () => {
  const { readingDisplayValue } = await import("./presentation");
  expect(
    readingDisplayValue({
      field: "gross_weight_kg",
      document_id: "si",
      normalized: "10000",
      text: "Gross Weight: 10000",
      unit_source: "default_kg",
      confidence: 1,
      provenance: "machine",
      acceptance_basis: "probability",
    }),
  ).toBe("10000 kg (assumed—unit not supplied)");
});

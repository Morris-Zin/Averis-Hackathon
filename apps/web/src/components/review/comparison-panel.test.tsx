import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { ComparisonPanel } from "./comparison-panel";

afterEach(cleanup);

it("shows extracted Chinese values while withholding unconfirmed comparisons", () => {
  render(
    <ComparisonPanel
      summaryKind="needs_review"
      activeField="shipper"
      setActiveField={() => {}}
      openCorrection={() => {}}
      report={{
        input_revision: 1,
        policy_version: "test",
        pair_valid: false,
        findings: [
          {
            field: "shipper",
            outcome: "unresolved",
            si: {
              field: "shipper",
              document_id: "si",
              text: "上海华远贸易有限公司",
              confidence: 1,
              provenance: "machine",
              acceptance_basis: "probability",
            },
            bl: {
              field: "shipper",
              document_id: "bl",
              text: "广州华盛物流有限公司",
              confidence: 1,
              provenance: "machine",
              acceptance_basis: "probability",
            },
          },
        ],
      }}
    />,
  );
  expect(screen.getByText("上海华远贸易有限公司")).toBeTruthy();
  expect(screen.getByText("广州华盛物流有限公司")).toBeTruthy();
  expect(screen.getAllByText("PAIR UNCONFIRMED")).toHaveLength(7);
  expect(
    screen.getByText("Comparison paused: confirm document pair"),
  ).toBeTruthy();
  expect(screen.getByRole("status").textContent).toContain(
    "could not verify a shared shipment reference",
  );
  expect(screen.queryByText("MISMATCH")).toBeNull();
  expect(screen.queryByText("MATCH")).toBeNull();
});

it("shows source-bound pairing separately from the field comparison", () => {
  render(
    <ComparisonPanel
      summaryKind="needs_review"
      report={{
        input_revision: 1,
        policy_version: "test",
        pair_valid: true,
        findings: [],
        issues: [],
        pairing_evidence: {
          si_document_id: "si",
          bl_document_id: "bl",
          reference: "ORD-123456",
          si_evidence_ids: ["si-reference"],
          bl_evidence_ids: ["bl-reference"],
          confidence: 0.97,
          model: "test",
          policy_version: "test",
        },
      }}
      activeField="shipper"
      setActiveField={() => {}}
      openCorrection={() => {}}
      siAttachment={{
        id: "si",
        filename: "instruction.txt",
        role: "SI",
        superseded: false,
        evidence: {
          document_id: "si",
          parser_version: "test",
          language: "eng",
          reader_version: "test",
          ocr_profile: "test",
          blocks: [
            {
              id: "si-reference",
              method: "native",
              text: "BL INSTRUCTION: ORD-123456",
              locations: [{ kind: "text", line_start: 2 }],
            },
          ],
        },
      }}
      blAttachment={{
        id: "bl",
        filename: "draft.txt",
        role: "BL",
        superseded: false,
        evidence: {
          document_id: "bl",
          parser_version: "test",
          language: "eng",
          reader_version: "test",
          ocr_profile: "test",
          blocks: [
            {
              id: "bl-reference",
              method: "native",
              text: "Order No: ORD-123456",
              locations: [{ kind: "text", line_start: 8 }],
            },
          ],
        },
      }}
    />,
  );
  expect(
    screen.getByText("Documents linked by reference ORD-123456"),
  ).toBeTruthy();
  expect(screen.getByText(/Pairing confidence 97%/)).toBeTruthy();
  expect(screen.getByText("0 of 7 fields checked")).toBeTruthy();
  const disclosure = screen
    .getByText("Documents linked by reference ORD-123456")
    .closest("details");
  expect(disclosure?.textContent).toContain("BL INSTRUCTION: ORD-123456");
  expect(disclosure?.textContent).toContain("Order No: ORD-123456");
  expect(screen.queryByText("No mismatch detected")).toBeNull();
});

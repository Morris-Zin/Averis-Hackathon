import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { EvidencePane } from "./evidence-pane";

afterEach(cleanup);
it("shows a recoverable preview error and retries without losing evidence", async () => {
  render(
    <EvidencePane
      title="SI"
      selectedIds={["b"]}
      onCorrect={() => {}}
      attachment={{
        id: "document",
        filename: "source.pdf",
        role: "SI",
        superseded: false,
        evidence: {
          document_id: "document",
          parser_version: "evidence-v2",
          language: "eng",
          reader_version: "fixture",
          ocr_profile: "eng-psm6",
          blocks: [
            {
              id: "b",
              text: "Shipper: ACME",
              method: "native",
              locations: [{ kind: "pdf", page: 1 }],
            },
          ],
          issues: [],
        },
      }}
    />,
  );
  fireEvent.error(screen.getByRole("img"));
  expect(screen.getByText(/could not load/)).toBeTruthy();
  expect(screen.getByText("Shipper: ACME")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Retry preview" }));
  const image = screen.getByRole("img");
  expect(image.getAttribute("src")).toContain("attempt=1");
  fireEvent.load(image);
  await waitFor(() =>
    expect(screen.queryByText(/Loading source preview/)).toBeNull(),
  );
});

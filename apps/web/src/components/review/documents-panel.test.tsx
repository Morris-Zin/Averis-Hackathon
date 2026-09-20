import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { DocumentsPanel } from "./documents-panel";

afterEach(cleanup);

it("lets a reviewer confirm the unchanged proposed pair when pairing was unresolved", async () => {
  const act = vi.fn().mockResolvedValue(true);
  render(
    <DocumentsPanel
      attachments={[]}
      email={{
        subject: "Check draft",
        sender: "ops@example.test",
        body: "Please compare",
      }}
      selection={{
        pairSi: "si",
        pairBl: "bl",
        pairChanged: false,
        setPairSi: vi.fn(),
        setPairBl: vi.fn(),
        currentAttachments: [],
      }}
      controlled={false}
      pairNeedsConfirmation
      pending={false}
      act={act}
    />,
  );
  const button = screen.getByRole("button", {
    name: "Confirm pair and compare",
  });
  expect((button as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(button);
  await waitFor(() =>
    expect(act).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "pair", si_id: "si", bl_id: "bl" }),
      expect.any(String),
    ),
  );
});

it("does not offer a redundant recompute for an unchanged valid pair", () => {
  render(
    <DocumentsPanel
      attachments={[]}
      email={{
        subject: "Check draft",
        sender: "ops@example.test",
        body: "Please compare",
      }}
      selection={{
        pairSi: "si",
        pairBl: "bl",
        pairChanged: false,
        setPairSi: vi.fn(),
        setPairBl: vi.fn(),
        currentAttachments: [],
      }}
      controlled={false}
      pairNeedsConfirmation={false}
      pending={false}
      act={vi.fn()}
    />,
  );
  expect(
    (
      screen.getByRole("button", {
        name: "Recompute comparison",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
});

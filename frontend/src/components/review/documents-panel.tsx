import { Download, FileText, RefreshCw } from "lucide-react";
import { useState } from "react";
import { DOCUMENT_RECOVERY_GUIDANCE, PAIR_REVIEW_REASON } from "./presentation";
import type { ActionDraft, AttachmentView } from "@/lib/contracts";
import { Button, Select, SelectItem } from "../ui";

type Props = {
  attachments: AttachmentView[];
  email: { subject: string; sender: string; body: string };
  selection: {
    pairSi: string;
    pairBl: string;
    pairChanged: boolean;
    setPairSi: (id: string) => void;
    setPairBl: (id: string) => void;
    currentAttachments: AttachmentView[];
  };
  controlled: boolean;
  pairNeedsConfirmation: boolean;
  pending: boolean;
  act: (action: ActionDraft, message: string) => Promise<boolean>;
};

export function DocumentsPanel({
  attachments,
  email,
  selection,
  controlled,
  pairNeedsConfirmation,
  pending,
  act,
}: Props) {
  const [pairReason, setPairReason] = useState("");
  const {
    pairSi,
    pairBl,
    pairChanged,
    setPairSi,
    setPairBl,
    currentAttachments,
  } = selection;
  return (
    <section className="documents-section">
      <div className="section-heading">
        <div>
          <h2>Source documents</h2>
          <p>
            Choose the current SI and draft BL used for comparison. Previous
            versions remain available as history.
          </p>
        </div>
      </div>
      <section className="original-email" aria-label="Original email">
        <h3>Original email</h3>
        <dl>
          <div>
            <dt>Subject</dt>
            <dd>{email.subject}</dd>
          </div>
          <div>
            <dt>From</dt>
            <dd>{email.sender || "Unknown sender"}</dd>
          </div>
        </dl>
        <p className="original-email-body">
          {email.body || "No message body."}
        </p>
      </section>
      {pairNeedsConfirmation ? (
        <p role="status">
          {PAIR_REVIEW_REASON} Check the originals, then confirm the SI and
          draft BL below. Conflicting shipment references cannot be overridden.
        </p>
      ) : null}
      <div className="pair-controls">
        <label>
          <span>Shipping instruction</span>
          <Select
            value={pairSi}
            label="Shipping instruction document"
            onValueChange={setPairSi}
            disabled={pending}
          >
            {currentAttachments.map((attachment) => (
              <SelectItem key={attachment.id} value={attachment.id}>
                {attachment.filename}
              </SelectItem>
            ))}
          </Select>
        </label>
        <label>
          <span>Draft bill of lading</span>
          <Select
            value={pairBl}
            label="Draft bill of lading document"
            onValueChange={setPairBl}
            disabled={pending}
          >
            {currentAttachments.map((attachment) => (
              <SelectItem key={attachment.id} value={attachment.id}>
                {attachment.filename}
              </SelectItem>
            ))}
          </Select>
        </label>
        <label>
          <span>Why do these documents belong together?</span>
          <input
            value={pairReason}
            onChange={(event) => setPairReason(event.target.value)}
            maxLength={1000}
            disabled={pending}
            placeholder="For example, same booking and customer"
          />
        </label>
        <Button
          variant="primary"
          disabled={
            (!pairChanged && !pairNeedsConfirmation) ||
            !pairSi ||
            !pairBl ||
            pairSi === pairBl ||
            !pairReason.trim() ||
            pending
          }
          onClick={() =>
            void act(
              {
                kind: "pair",
                si_id: pairSi,
                bl_id: pairBl,
                reason: pairReason.trim(),
              },
              "Document pair updated.",
            )
          }
        >
          {pairNeedsConfirmation
            ? "Confirm pair and compare"
            : "Recompute comparison"}
        </Button>
      </div>
      <div className="attachment-list">
        {attachments.map((attachment) => (
          <a
            key={attachment.id}
            className={attachment.superseded ? "previous-version" : ""}
            href={`/api/documents/${encodeURIComponent(attachment.id)}/content`}
            target="_blank"
            rel="noreferrer"
          >
            <FileText size={20} />
            <span>
              <strong>{attachment.filename}</strong>
              <small>
                {attachment.superseded ? "Previous version" : attachment.role} ·{" "}
                {attachment.evidence?.blocks?.length ?? 0} evidence blocks
              </small>
            </span>
            <Download size={16} />
          </a>
        ))}
      </div>
      {controlled ? (
        <Button
          onClick={() =>
            void act(
              {
                kind: "revision",
                reason: "Reviewer requested the controlled revised draft",
              },
              "Controlled revised draft attached and comparison recomputed.",
            )
          }
          disabled={pending}
        >
          <RefreshCw size={15} />
          Attach controlled revised draft
        </Button>
      ) : (
        <p className="readonly-note">{DOCUMENT_RECOVERY_GUIDANCE}</p>
      )}
    </section>
  );
}

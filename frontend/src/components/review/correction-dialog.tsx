"use client";
import { useState } from "react";
import { LoaderCircle } from "lucide-react";
import type {
  ActionDraft,
  AttachmentView,
  Field,
  Finding,
} from "@/lib/contracts";
import { FIELD_LABELS } from "@/lib/contracts";
import { shouldResetOcrVerification } from "@/lib/ocr-verification";
import { Button, Dialog, Input, Textarea } from "../ui";
import { locationLabel } from "./evidence-pane";

type Props = {
  activeField: Field;
  correctionReading: Finding["si"];
  correctionAttachment: AttachmentView;
  pending: boolean;
  act: (action: ActionDraft, success: string) => Promise<boolean>;
  onClose: () => void;
};

export function CorrectionDialog({
  activeField,
  correctionReading,
  correctionAttachment,
  pending,
  act,
  onClose,
}: Props) {
  const [transcription, setTranscription] = useState(
    correctionReading.text ?? "",
  );
  const [reason, setReason] = useState("");
  const [evidenceIds, setEvidenceIds] = useState<string[]>(
    correctionReading.evidence_ids ?? [],
  );
  const [verified, setVerified] = useState(false);
  const selectedCorrectionBlocks =
    correctionAttachment.evidence?.blocks?.filter((block) =>
      evidenceIds.includes(block.id),
    ) ?? [];
  const selectedAreOcr =
    selectedCorrectionBlocks.length > 0 &&
    selectedCorrectionBlocks.every((block) => block.method === "ocr");
  const selectedIncludeOcr = selectedCorrectionBlocks.some(
    (block) => block.method === "ocr",
  );
  async function saveCorrection() {
    if (
      !correctionReading ||
      !correctionAttachment ||
      !evidenceIds.length ||
      !reason.trim()
    )
      return;
    if (
      (selectedAreOcr && !transcription.trim()) ||
      (selectedIncludeOcr && !verified)
    )
      return;
    const saved = await act(
      {
        kind: "correct",
        field: activeField,
        document_id: correctionAttachment.id,
        transcription: selectedAreOcr ? transcription.trim() : undefined,
        evidence_ids: evidenceIds,
        verified: selectedIncludeOcr ? verified : true,
        reason: reason.trim(),
      },
      "Reading corrected and comparison recomputed.",
    );
    if (saved) onClose();
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !pending) onClose();
      }}
      title={`Correct ${FIELD_LABELS[activeField].toLocaleLowerCase()} reading`}
      description="This changes Averis's reading of the source. It does not alter the original document or hide a real discrepancy."
    >
      <div className="correction-form">
        {selectedAreOcr ? (
          <label>
            <span>Verified OCR transcription</span>
            <Textarea
              value={transcription}
              onChange={(event) => {
                // Any transcription edit revokes the confirmation against the original image.
                if (
                  shouldResetOcrVerification(
                    transcription,
                    event.target.value,
                    evidenceIds,
                    evidenceIds,
                  )
                )
                  setVerified(false);
                setTranscription(event.target.value);
              }}
              rows={3}
              disabled={pending}
            />
          </label>
        ) : (
          <div className="correction-note">
            <p>
              Select the exact native source block below. Averis will recompute
              from that unchanged source text.
            </p>
            <blockquote>
              {selectedCorrectionBlocks.length
                ? selectedCorrectionBlocks.map((block) => block.text).join("\n")
                : "No evidence selected"}
            </blockquote>
          </div>
        )}
        <fieldset>
          <legend>
            Evidence from{" "}
            {correctionAttachment?.filename ?? "selected document"}
          </legend>
          {correctionAttachment?.evidence?.blocks?.map((block) => (
            <label className="evidence-option" key={block.id}>
              <input
                type="checkbox"
                checked={evidenceIds.includes(block.id)}
                disabled={pending}
                onChange={(event) => {
                  const next = event.target.checked
                    ? [...evidenceIds, block.id]
                    : evidenceIds.filter((idValue) => idValue !== block.id);
                  if (
                    shouldResetOcrVerification(
                      transcription,
                      transcription,
                      evidenceIds,
                      next,
                    )
                  )
                    setVerified(false);
                  setEvidenceIds(next);
                }}
              />
              <span>
                <strong>{locationLabel(block)}</strong>
                {block.text}
              </span>
            </label>
          ))}
        </fieldset>
        {selectedIncludeOcr ? (
          <label className="verify-check">
            <input
              type="checkbox"
              checked={verified}
              disabled={pending}
              onChange={(event) => setVerified(event.target.checked)}
            />
            <span>
              I checked this transcription against the rendered original.
            </span>
          </label>
        ) : null}
        <label>
          <span>Reason for correction</span>
          <Input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="What evidence selection or reading was wrong?"
            disabled={pending}
          />
        </label>
        <div className="dialog-actions">
          <Button onClick={() => onClose()} disabled={pending}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() => void saveCorrection()}
            disabled={
              !evidenceIds.length ||
              !reason.trim() ||
              pending ||
              (selectedAreOcr && !transcription.trim()) ||
              (selectedIncludeOcr && !verified)
            }
          >
            {pending ? (
              <>
                <LoaderCircle className="spin" size={15} />
                Saving…
              </>
            ) : (
              "Save and recompute"
            )}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

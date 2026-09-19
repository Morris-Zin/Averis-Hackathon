"use client";
import Image from "next/image";
import { Download, FileText } from "lucide-react";
import type { AttachmentView, EvidenceBlock } from "@/lib/contracts";
import { Button } from "../ui";

export function locationLabel(block: EvidenceBlock) {
  const location = block.locations[0];
  if (!location) return "Location unavailable";
  if (location.page) return `Page ${location.page}`;
  if (location.sheet)
    return `${location.sheet}${location.cell ? ` · ${location.cell}` : ""}`;
  if (location.paragraph) return `Paragraph ${location.paragraph}`;
  if (location.line_start)
    return location.line_end && location.line_end !== location.line_start
      ? `Lines ${location.line_start}–${location.line_end}`
      : `Line ${location.line_start}`;
  return location.kind;
}

export function EvidencePane({
  attachment,
  selectedIds,
  title,
  onCorrect,
}: {
  attachment?: AttachmentView;
  selectedIds: string[];
  title: string;
  onCorrect: () => void;
}) {
  const blocks = attachment?.evidence?.blocks ?? [];
  const previewBlock =
    blocks.find((block) => selectedIds.includes(block.id)) ?? blocks[0];
  const previewLocation = previewBlock?.locations.find(
    (location) => location.kind === "pdf" || location.kind === "image",
  );
  const previewPage = previewLocation?.page ?? 1;
  const roleConfidence =
    attachment?.role_confidence == null
      ? null
      : Math.round(attachment.role_confidence * 100);
  return (
    <section className="evidence-pane">
      <header>
        <div>
          <span>
            {title}
            {attachment?.superseded ? " · Previous version" : ""}
          </span>
          <strong>{attachment?.filename ?? "No document selected"}</strong>
          {roleConfidence !== null ? (
            <small
              className="role-confidence"
              title="Confidence that this document has the assigned SI or draft BL role"
            >
              Role confidence {roleConfidence}%
            </small>
          ) : null}
        </div>
        {attachment ? (
          <a
            className="icon-link"
            href={`/api/documents/${encodeURIComponent(attachment.id)}/content`}
            target="_blank"
            rel="noreferrer"
            aria-label={`Open ${attachment.filename}`}
          >
            <Download size={16} />
          </a>
        ) : null}
      </header>
      <div className="document-paper">
        {attachment && previewLocation ? (
          <div className="document-render">
            <span>
              Rendered{" "}
              {previewLocation.kind === "pdf" ? `page ${previewPage}` : "image"}
            </span>
            <Image
              unoptimized
              src={`/api/documents/${encodeURIComponent(attachment.id)}/preview?page=${previewPage}`}
              alt={`Rendered source preview for ${attachment.filename}`}
              width={900}
              height={1200}
            />
          </div>
        ) : null}
        {blocks.length ? (
          blocks.map((block) => (
            <div
              key={block.id}
              className={
                selectedIds.includes(block.id)
                  ? "evidence-block selected"
                  : "evidence-block"
              }
            >
              <small>{locationLabel(block)}</small>
              <p>{block.text}</p>
              {block.method === "ocr" ? (
                <span className="ocr-tag">OCR</span>
              ) : null}
            </div>
          ))
        ) : (
          <div className="empty-evidence">
            <FileText size={24} />
            <span>No source evidence is available for this document.</span>
          </div>
        )}
      </div>
      <footer>
        <Button
          size="sm"
          onClick={onCorrect}
          disabled={!attachment || attachment.superseded}
        >
          Correct our reading
        </Button>
        <span>
          {attachment?.superseded
            ? "Previous versions are read-only"
            : "Original file stays unchanged"}
        </span>
      </footer>
    </section>
  );
}

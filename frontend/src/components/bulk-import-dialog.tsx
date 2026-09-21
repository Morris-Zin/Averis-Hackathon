"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { FilePlus2, X } from "lucide-react";
import type { BulkImportResponse, BulkPreviewResponse } from "@/lib/contracts";
import { displayCaseKey } from "@/lib/contracts";
import { useSession } from "./session-provider";
import { Button, Dialog, Spinner } from "./ui";

type Mode = "archive" | "json";

const MB = 1024 * 1024;

function selectionError(
  mode: Mode,
  archive: File | null,
  emails: File[],
  files: File[],
): string {
  if (mode === "archive") {
    if (!archive) return "";
    if (!archive.name.toLowerCase().endsWith(".zip"))
      return "Choose a .zip archive.";
    if (archive.size > 21 * MB) return "The archive must be 21 MB or smaller.";
    if (archive.size === 0) return "The archive is empty.";
    return "";
  }
  if (emails.length > 600) return "Choose at most 600 email JSON files.";
  if (files.length > 1200) return "Choose at most 1200 attachment files.";
  if (emails.some((file) => !file.name.toLowerCase().endsWith(".json")))
    return "Email files must be .json.";
  if (emails.some((file) => file.size > 2 * MB || file.size === 0))
    return "Each email JSON must be 1 byte to 2 MB.";
  if (files.some((file) => file.size > 10 * MB || file.size === 0))
    return "Each attachment must be 1 byte to 10 MB.";
  return "";
}

function resultTone(status: string) {
  if (status === "accepted") return "success";
  if (status === "duplicate") return "neutral";
  return "danger";
}

export function BulkImportDialog({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported?: () => void;
}) {
  const { api, session, sessionActionPending } = useSession();
  const [mode, setMode] = useState<Mode>("archive");
  const [archive, setArchive] = useState<File | null>(null);
  const [emails, setEmails] = useState<File[]>([]);
  const [attachments, setAttachments] = useState<File[]>([]);
  const [preview, setPreview] = useState<BulkPreviewResponse | null>(null);
  const [previewPending, setPreviewPending] = useState(false);
  const [result, setResult] = useState<BulkImportResponse | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const previewVersion = useRef(0);

  const invalid = selectionError(mode, archive, emails, attachments);
  const hasSelection =
    mode === "archive" ? archive !== null : emails.length > 0;

  useEffect(() => {
    setPreview(null);
    setResult(null);
    setError("");
    if (invalid || !hasSelection || !session) return;
    const version = ++previewVersion.current;
    const controller = new AbortController();
    setPreviewPending(true);
    void api
      .bulkPreview(
        {
          archive: mode === "archive" ? (archive ?? undefined) : undefined,
          emails: mode === "json" ? emails : undefined,
          files: mode === "json" ? attachments : undefined,
        },
        session.csrf_token,
      )
      .then((value) => {
        if (version === previewVersion.current && !controller.signal.aborted)
          setPreview(value);
      })
      .catch((reason: unknown) => {
        if (version === previewVersion.current && !controller.signal.aborted)
          setError(
            reason instanceof Error
              ? reason.message
              : "The selection could not be previewed.",
          );
      })
      .finally(() => {
        if (version === previewVersion.current) setPreviewPending(false);
      });
    return () => controller.abort();
  }, [api, archive, attachments, emails, hasSelection, invalid, mode, session]);

  async function submit() {
    if (!session || sessionActionPending || pending || invalid || !hasSelection)
      return;
    setPending(true);
    setError("");
    try {
      const value = await api.bulkImport(
        {
          archive: mode === "archive" ? (archive ?? undefined) : undefined,
          emails: mode === "json" ? emails : undefined,
          files: mode === "json" ? attachments : undefined,
        },
        session.csrf_token,
      );
      setResult(value);
      onImported?.();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The emails could not be imported. Try again.",
      );
    } finally {
      setPending(false);
    }
  }

  function removeEmail(index: number) {
    setEmails((current) => current.filter((_, position) => position !== index));
  }

  function removeAttachment(index: number) {
    setAttachments((current) =>
      current.filter((_, position) => position !== index),
    );
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !pending) onClose();
      }}
      title="Bulk import"
      description="Import many emails at once. Each email is checked with the same rules as single-email intake."
    >
      <div className="bulk-mode-tabs" role="tablist" aria-label="Bulk source">
        <button
          type="button"
          role="tab"
          disabled={pending}
          aria-selected={mode === "archive"}
          onClick={() => setMode("archive")}
        >
          ZIP archive
        </button>
        <button
          type="button"
          role="tab"
          disabled={pending}
          aria-selected={mode === "json"}
          onClick={() => setMode("json")}
        >
          Email JSON files
        </button>
      </div>
      {mode === "archive" ? (
        <div className="import-attachments">
          <label className="attachment-picker">
            <FilePlus2 size={20} />
            <span>{archive ? "Replace archive" : "Choose ZIP archive"}</span>
            <input
              aria-label="Choose ZIP archive"
              type="file"
              accept=".zip"
              disabled={pending}
              onChange={(event) => {
                setArchive(event.target.files?.[0] ?? null);
                event.target.value = "";
              }}
            />
          </label>
          <p>
            Organizer-style ZIP: email JSON files plus the attachments they
            reference.
          </p>
          <small>ZIP · 21 MB · 2000 files · 600 emails · 32 MB unpacked</small>
          {archive ? (
            <ul>
              <li>
                <span>
                  {archive.name}
                  <small>{(archive.size / 1024).toFixed(1)} KB</small>
                </span>
                <Button
                  type="button"
                  size="sm"
                  disabled={pending}
                  aria-label={`Remove ${archive.name}`}
                  onClick={() => setArchive(null)}
                >
                  <X size={14} />
                </Button>
              </li>
            </ul>
          ) : null}
        </div>
      ) : (
        <div className="import-attachments">
          <label className="attachment-picker">
            <FilePlus2 size={20} />
            <span>Add email JSON files</span>
            <input
              aria-label="Add email JSON files"
              type="file"
              multiple
              accept=".json"
              disabled={pending}
              onChange={(event) => {
                const selected = Array.from(event.target.files ?? []);
                setEmails((current) => [...current, ...selected]);
                event.target.value = "";
              }}
            />
          </label>
          <label className="attachment-picker">
            <FilePlus2 size={20} />
            <span>Add attachments (optional)</span>
            <input
              aria-label="Add attachments"
              type="file"
              multiple
              accept=".txt,.pdf,.docx,.xlsx,.png,.jpg,.jpeg"
              disabled={pending}
              onChange={(event) => {
                const selected = Array.from(event.target.files ?? []);
                setAttachments((current) => [...current, ...selected]);
                event.target.value = "";
              }}
            />
          </label>
          <p>
            References resolve by exact filename. Missing files stay honest
            missing attachments.
          </p>
          <small>JSON · 2 MB each · 600 emails · attachments 10 MB each</small>
          {emails.length || attachments.length ? (
            <ul>
              {emails.map((file, index) => (
                <li key={`email-${file.name}-${index}`}>
                  <span>
                    {file.name}
                    <small>{(file.size / 1024).toFixed(1)} KB</small>
                  </span>
                  <Button
                    type="button"
                    size="sm"
                    disabled={pending}
                    aria-label={`Remove ${file.name}`}
                    onClick={() => removeEmail(index)}
                  >
                    <X size={14} />
                  </Button>
                </li>
              ))}
              {attachments.map((file, index) => (
                <li key={`file-${file.name}-${index}`}>
                  <span>
                    {file.name}
                    <small>{(file.size / 1024).toFixed(1)} KB</small>
                  </span>
                  <Button
                    type="button"
                    size="sm"
                    disabled={pending}
                    aria-label={`Remove ${file.name}`}
                    onClick={() => removeAttachment(index)}
                  >
                    <X size={14} />
                  </Button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      )}
      {invalid ? (
        <p className="import-error" role="alert">
          {invalid}
        </p>
      ) : null}
      {previewPending ? (
        <p role="status">
          <Spinner label="Reading selection" />
        </p>
      ) : null}
      {preview && !result ? (
        <div className="bulk-preview" aria-live="polite">
          <p>
            <strong>
              {preview.valid} ready · {preview.invalid} invalid
            </strong>
          </p>
          <ul>
            {preview.emails.map((email, index) => (
              <li key={`${email.ref}-${index}`}>
                <span
                  className={`status-lozenge ${email.error ? "danger" : "neutral"}`}
                >
                  {email.error ? "INVALID" : "READY"}
                </span>
                <span>
                  <strong>{email.error ? email.ref : email.subject}</strong>
                  <small>
                    {email.error ??
                      `${email.sender} · ${(email.attachments ?? []).length} file(s)`}
                    {!email.error && (email.missing_attachments ?? []).length
                      ? ` · missing: ${(email.missing_attachments ?? []).join(", ")}`
                      : ""}
                  </small>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {result ? (
        <div className="bulk-results" aria-live="polite">
          <p>
            <strong>
              {result.accepted} accepted · {result.duplicates} duplicates ·{" "}
              {result.failed} failed
            </strong>
          </p>
          <ul>
            {result.items.map((item, index) => (
              <li key={`${item.ref}-${index}`}>
                <span className={`status-lozenge ${resultTone(item.status)}`}>
                  {item.status.toUpperCase()}
                </span>
                <span>
                  {item.case_id ? (
                    <Link
                      className="case-key"
                      href={`/review/?case=${encodeURIComponent(item.case_id)}`}
                    >
                      {displayCaseKey(item.case_id)}
                    </Link>
                  ) : (
                    <strong>{item.ref}</strong>
                  )}
                  <small>
                    {item.status === "failed"
                      ? (item.error ?? "Import failed")
                      : `${item.subject} · ${item.attachments} file(s)`}
                    {item.status !== "failed" &&
                    (item.missing_attachments ?? []).length
                      ? ` · missing: ${(item.missing_attachments ?? []).join(", ")}`
                      : ""}
                  </small>
                </span>
              </li>
            ))}
          </ul>
          <p className="import-hint">
            Re-importing the same selection reports duplicates — no new cases
            are created.
          </p>
        </div>
      ) : null}
      {!session?.live_enabled ? (
        <p role="status">Live processing is currently unavailable.</p>
      ) : null}
      {error ? (
        <p className="import-error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="import-actions">
        <Button type="button" onClick={onClose} disabled={pending}>
          Close
        </Button>
        <Button
          type="button"
          variant="primary"
          disabled={
            pending ||
            sessionActionPending ||
            !hasSelection ||
            Boolean(invalid) ||
            !preview ||
            preview.valid === 0 ||
            !session?.live_enabled
          }
          onClick={() => void submit()}
        >
          {pending
            ? "Importing…"
            : result
              ? "Import again"
              : `Import ${preview?.valid ?? 0} emails`}
        </Button>
      </div>
    </Dialog>
  );
}

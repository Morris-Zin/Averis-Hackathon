"use client";

import { useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { FilePlus2, X } from "lucide-react";
import { Button, Dialog, Input } from "./ui";
import { useSession } from "./session-provider";

const ACCEPTED = ".txt,.pdf,.docx,.xlsx,.png,.jpg,.jpeg";
const MB = 1024 * 1024;

export function ImportEmailDialog({ onClose }: { onClose: () => void }) {
  const { api, session } = useSession();
  const router = useRouter();
  const [subject, setSubject] = useState("");
  const [sender, setSender] = useState("");
  const [body, setBody] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const submitting = useRef(false);

  function addFiles(selected: File[]) {
    const next = [...files, ...selected];
    if (next.length > 8) return setError("Choose at most eight attachments.");
    if (
      next.some(
        (file) =>
          !ACCEPTED.split(",").some((extension) =>
            file.name.toLowerCase().endsWith(extension),
          ),
      )
    )
      return setError("Use TXT, PDF, DOCX, XLSX, PNG or JPEG files.");
    if (next.some((file) => file.size > 10 * MB))
      return setError("Each attachment must be 10 MB or smaller.");
    if (next.reduce((total, file) => total + file.size, 0) > 20 * MB)
      return setError("Attachments must total 20 MB or less.");
    setError("");
    setFiles(next);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session || submitting.current) return;
    submitting.current = true;
    setPending(true);
    setError("");
    try {
      const result = await api.importEmail(
        { subject: subject.trim(), sender: sender.trim(), body },
        files,
        session.csrf_token,
      );
      router.push(`/review/?case=${encodeURIComponent(result.id)}`);
      onClose();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The email could not be added. Try again.",
      );
    } finally {
      submitting.current = false;
      setPending(false);
    }
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !pending) onClose();
      }}
      title="Add email"
      description="Paste an email and attach its shipping documents. No mailbox connection needed."
    >
      <form
        className="manual-import-form"
        onSubmit={(event) => void submit(event)}
      >
        <label>
          Subject
          <Input
            autoFocus
            required
            maxLength={1000}
            value={subject}
            onChange={(event) => setSubject(event.target.value)}
            disabled={pending}
          />
        </label>
        <label>
          From
          <Input
            type="email"
            maxLength={320}
            placeholder="sender@example.com"
            value={sender}
            onChange={(event) => setSender(event.target.value)}
            disabled={pending}
          />
        </label>
        <label>
          Email message
          <textarea
            rows={5}
            maxLength={100000}
            value={body}
            onChange={(event) => setBody(event.target.value)}
            disabled={pending}
          />
        </label>
        <div className="import-attachments">
          <label className="attachment-picker">
            <FilePlus2 size={20} />
            <span>Add attachments</span>
            <input
              aria-label="Add attachments"
              type="file"
              multiple
              accept={ACCEPTED}
              disabled={pending}
              onChange={(event) => {
                addFiles(Array.from(event.target.files ?? []));
                event.target.value = "";
              }}
            />
          </label>
          <p>
            Attach the SI and draft BL for a document check. Other emails can be
            added without files.
          </p>
          <small>
            TXT, PDF, DOCX, XLSX, PNG, JPEG · 8 files · 10 MB each · 20 MB total
          </small>
          {files.length ? (
            <ul>
              {files.map((file, index) => (
                <li key={`${file.name}-${index}`}>
                  <span>
                    {file.name}
                    <small>{(file.size / 1024).toFixed(1)} KB</small>
                  </span>
                  <Button
                    type="button"
                    size="sm"
                    disabled={pending}
                    aria-label={`Remove ${file.name}`}
                    onClick={() =>
                      setFiles((current) =>
                        current.filter((_, position) => position !== index),
                      )
                    }
                  >
                    <X size={14} />
                  </Button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <p className="import-hint">
          Submitting sends the email and extracted document text for AI
          processing. Use test data you’re allowed to share. Each session allows
          three live runs, shared with retries.
        </p>
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
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            disabled={pending || !subject.trim() || !session?.live_enabled}
          >
            {pending ? "Adding email…" : "Add and process"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

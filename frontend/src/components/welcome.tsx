"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowRight,
  FileCheck2,
  FileSearch,
  History,
  Inbox,
  ShieldCheck,
} from "lucide-react";
import { useSession } from "./session-provider";
import { Button } from "./ui";

const STEPS = [
  {
    icon: Inbox,
    title: "Bring the emails",
    detail:
      "Paste one email or bulk-import a ZIP of email JSON with attachments. Re-imports reuse their case instead of duplicating it.",
  },
  {
    icon: FileSearch,
    title: "Let the check run",
    detail:
      "Every email is classified into five categories. Shipping checks compare seven instruction fields against the draft bill of lading.",
  },
  {
    icon: History,
    title: "Review the evidence",
    detail:
      "Mismatches route to human review with source text, locations and history. Corrections change our reading, never the original document.",
  },
];

const QUEUE_PREVIEW = [
  {
    key: "AV-7F3A2C91",
    subject: "Draft BL review · Port Klang to Singapore",
    category: "Shipping instruction check",
    result: "MISMATCH",
    tone: "danger",
  },
  {
    key: "AV-41BD88E0",
    subject: "Shipping documents · Penang export",
    category: "Shipping instruction check",
    result: "NO MISMATCH",
    tone: "success",
  },
  {
    key: "AV-90C1D452",
    subject: "Invoice INV-2094 · freight charge query",
    category: "Invoice query",
    result: "CATEGORIZED",
    tone: "neutral",
  },
  {
    key: "AV-2E77B309",
    subject: "Draft BL · gross weight missing",
    category: "Shipping instruction check",
    result: "NEEDS REVIEW",
    tone: "warning",
  },
];

export function Welcome() {
  const router = useRouter();
  const { enterDemo, sessionMessage, unavailableMessage } = useSession();
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function enter() {
    setPending(true);
    setError("");
    try {
      await enterDemo();
      router.replace("/");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Could not open the demo workspace.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="welcome-shell">
      <section className="welcome-entry" aria-labelledby="welcome-title">
        <div className="brand-lockup">
          <span className="brand-mark">
            <FileCheck2 size={21} />
          </span>
          <span>Averis</span>
        </div>
        <div className="welcome-copy">
          <h1 id="welcome-title">
            Check every draft bill of lading against its shipping instruction.
          </h1>
          <p>
            Averis classifies incoming email, compares the seven shipment
            fields, and traces each finding back to its source document for
            human review.
          </p>
        </div>
        <ol className="welcome-steps">
          {STEPS.map((step) => (
            <li key={step.title}>
              <span className="welcome-step-icon" aria-hidden="true">
                <step.icon size={18} />
              </span>
              <div>
                <strong>{step.title}</strong>
                <p>{step.detail}</p>
              </div>
            </li>
          ))}
        </ol>
        <div className="welcome-actions">
          <Button
            variant="primary"
            onClick={() => void enter()}
            disabled={pending}
          >
            {pending
              ? "Opening workspace…"
              : sessionMessage
                ? "Enter a new demo workspace"
                : "Enter demo workspace"}
            <ArrowRight size={16} />
          </Button>
          {sessionMessage ? (
            <p className="connection-note session-expired" role="alert">
              <AlertCircle size={15} />
              {sessionMessage}
            </p>
          ) : null}
          {unavailableMessage ? (
            <p className="connection-note server-error" role="alert">
              <AlertCircle size={15} />
              The server could not be reached: {unavailableMessage}
            </p>
          ) : null}
          {error ? (
            <p className="form-error" role="alert">
              {error}
            </p>
          ) : null}
        </div>
        <div className="welcome-proof">
          <ShieldCheck size={16} />
          <span>
            Private demo session with saved scenarios. No mailbox is connected,
            and workspaces expire after 24 hours.
          </span>
        </div>
      </section>
      <aside className="welcome-queue" aria-label="Illustrative review queue">
        <div className="welcome-queue-head">
          <div>
            <strong>Shipping review</strong>
            <span>Illustrative queue</span>
          </div>
          <span className="status-lozenge neutral">4 open</span>
        </div>
        <ul>
          {QUEUE_PREVIEW.map((row) => (
            <li key={row.key}>
              <span className="welcome-queue-key">{row.key}</span>
              <span className="welcome-queue-subject">{row.subject}</span>
              <span className="welcome-queue-meta">
                {row.category}
                <span className={`status-lozenge ${row.tone}`}>
                  {row.result}
                </span>
              </span>
            </li>
          ))}
        </ul>
        <p className="welcome-queue-foot">
          Demo workspaces start with eight saved scenarios like these. Live AI
          checks run only after the shared budget is verified.
        </p>
      </aside>
    </main>
  );
}

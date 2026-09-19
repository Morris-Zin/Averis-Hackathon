"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowRight, FileCheck2, ShieldCheck } from "lucide-react";
import { useSession } from "./session-provider";
import { Button } from "./ui";

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
      <section className="welcome-panel">
        <div className="brand-lockup">
          <span className="brand-mark">
            <FileCheck2 size={21} />
          </span>
          <span>Averis</span>
        </div>
        <div className="welcome-copy">
          <p className="welcome-kicker">Document operations</p>
          <h1>
            Every discrepancy,
            <br />
            traced to its source.
          </h1>
          <p>
            A focused review desk for checking draft bills of lading against
            shipping instructions. See the source, correct the reading, and keep
            work moving.
          </p>
        </div>
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
            The server creates a private controlled-demo session. No email
            account is connected.
          </span>
        </div>
      </section>
      <aside
        className="welcome-ledger"
        aria-label="Illustrative comparison example"
      >
        <div className="ledger-heading">
          <span>Illustrative comparison</span>
          <span className="badge badge-danger">2 mismatches</span>
        </div>
        <div className="ledger-docs">
          <span>Shipping instruction</span>
          <span>Draft bill of lading</span>
        </div>
        <div className="ledger-row">
          <span>Port of discharge</span>
          <strong>Rotterdam</strong>
          <strong className="mismatch-value">Antwerp</strong>
        </div>
        <div className="ledger-row">
          <span>Gross weight</span>
          <strong>48,620 kg</strong>
          <strong className="mismatch-value">46,820 kg</strong>
        </div>
        <div className="ledger-row">
          <span>Container count</span>
          <strong>2 × 40HC</strong>
          <strong>2 × 40HC</strong>
        </div>
        <div className="source-slip">
          <span>Source evidence</span>
          <p>PORT OF DISCHARGE: ANTWERP, BELGIUM</p>
          <small>Draft_BL.txt · line 8</small>
        </div>
      </aside>
    </main>
  );
}

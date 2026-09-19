"use client";
import Link from "next/link";
import {
  AlertCircle,
  ArrowLeft,
  Check,
  CheckCircle2,
  ChevronDown,
  RotateCcw,
  UserRound,
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import type { CaseView, Category } from "@/lib/contracts";
import { CATEGORY_LABELS, displayCaseKey } from "@/lib/contracts";
import { AppShell } from "./app-shell";
import { Button, Select, SelectItem, Spinner } from "./ui";
import { Welcome } from "./welcome";
import { ComparisonPanel } from "./review/comparison-panel";
import { DocumentsPanel } from "./review/documents-panel";
import { ActivityPanel } from "./review/activity-panel";
import { CorrectionDialog } from "./review/correction-dialog";
import { useReviewWorkspace } from "./review/use-review-workspace";

export function ReviewWorkspace() {
  const params = useSearchParams();
  const {
    status,
    session,
    item,
    loading,
    error,
    notice,
    pending,
    act,
    controlled,
    processingActive,
    navigation: { tab, setTab, activeField, setActiveField },
    category: { categoryDraft, setCategoryDraft, classificationConfidence },
    documents: {
      pairSi,
      setPairSi,
      pairBl,
      setPairBl,
      pairChanged,
      currentAttachments,
    },
    comparison: { activeFinding, siAttachment, blAttachment, summary },
    correction: {
      correctSide,
      setCorrectSide,
      correctionReading,
      correctionAttachment,
      openCorrection,
    },
  } = useReviewWorkspace(params.get("case") ?? "");
  if (status === "loading")
    return (
      <main className="initial-loading">
        <Spinner label="Opening case" />
      </main>
    );
  if (status !== "ready") return <Welcome />;

  return (
    <AppShell>
      <div className="review-page">
        <div className="review-breadcrumbs">
          <Link href="/">
            <ArrowLeft size={15} />
            Queues
          </Link>
          <span>/</span>
          <span>{item ? displayCaseKey(item.id) : "Case"}</span>
        </div>
        {loading ? (
          <div className="review-loading">
            <Spinner label="Loading case" />
          </div>
        ) : error && !item ? (
          <div className="table-state error-state">
            <strong>Case could not be loaded</strong>
            <span>{error || "Choose a case from the queue."}</span>
            <Link className="button button-secondary button-md" href="/">
              Back to queues
            </Link>
          </div>
        ) : item ? (
          <>
            <header className="issue-header">
              <div>
                <p className="issue-key" title={item.id}>
                  {displayCaseKey(item.id)}
                </p>
                <h1>{item.subject}</h1>
                <p>
                  From {item.sender} ·{" "}
                  {new Date(item.received_at).toLocaleString()}
                </p>
              </div>
              <div className="issue-header-actions">
                <Button
                  onClick={() =>
                    void act(
                      {
                        kind: "retry",
                        reason: controlled
                          ? "Reviewer requested live processing for the saved illustrative sample"
                          : "Reviewer requested a processing retry",
                      },
                      controlled
                        ? "Live check requested."
                        : "Processing retry requested.",
                    )
                  }
                  disabled={
                    pending || processingActive || !session?.live_enabled
                  }
                  title={
                    !session?.live_enabled
                      ? "Live AI processing is disabled"
                      : processingActive
                        ? "A processing run is already active"
                        : controlled
                          ? "Run live AI processing on this saved illustrative sample"
                          : undefined
                  }
                >
                  <RotateCcw size={15} />
                  {processingActive
                    ? "Live check running..."
                    : controlled
                      ? "Run live check"
                      : "Retry"}
                </Button>
                <Select
                  value={item.workflow}
                  label="Workflow status"
                  onValueChange={(workflow) =>
                    void act(
                      {
                        kind: "workflow",
                        workflow: workflow as CaseView["workflow"],
                        reason: "Workflow status changed",
                      },
                      "Moved to " + workflow + ".",
                    )
                  }
                  disabled={pending}
                >
                  <SelectItem value="open">Open</SelectItem>
                  <SelectItem value="waiting">Waiting</SelectItem>
                  <SelectItem value="completed">Completed</SelectItem>
                </Select>
              </div>
            </header>
            {controlled ? (
              <div className="demo-banner compact">
                <strong>Saved illustrative scenario</strong>
                <span>
                  {session?.live_enabled
                    ? "The email and source documents are synthetic. Live AI can check this saved sample."
                    : "Classification is illustrative; comparison and corrections are deterministic and persisted in this server session. Live AI and email are off."}
                </span>
              </div>
            ) : !session?.live_enabled ? (
              <div className="demo-banner compact">
                <strong>Controlled server demo</strong>
                <span>Live AI and email are off.</span>
              </div>
            ) : null}
            {error ? (
              <div className="inline-message error" role="alert">
                <AlertCircle size={16} />
                {error}
              </div>
            ) : null}
            {notice ? (
              <div className="inline-message success" role="status">
                <CheckCircle2 size={16} />
                {notice}
              </div>
            ) : null}
            <div className="issue-actions-row">
              <Button variant="primary" onClick={() => setTab("comparison")}>
                Review comparison
              </Button>
              <Button onClick={() => setTab("documents")}>
                View source documents
              </Button>
              <Button onClick={() => setTab("activity")}>View history</Button>
            </div>
            <div className="issue-layout">
              <div className="issue-main">
                <section className={`result-banner ${summary?.tone}`}>
                  <span className="result-icon">
                    {summary?.tone === "success" ? (
                      <Check size={20} />
                    ) : (
                      <AlertCircle size={20} />
                    )}
                  </span>
                  <div>
                    <strong>{summary?.label}</strong>
                    <p>{summary?.detail}</p>
                  </div>
                </section>
                <section className="classification-panel">
                  <div>
                    <h2>Classification</h2>
                    <p>
                      Confidence shows certainty in the category prediction. It
                      is not measured accuracy.
                    </p>
                  </div>
                  <div className="classification-controls">
                    <Select
                      value={categoryDraft}
                      label="Email category"
                      onValueChange={(value) =>
                        setCategoryDraft(value as Category)
                      }
                      disabled={pending}
                    >
                      {(
                        Object.entries(CATEGORY_LABELS) as [Category, string][]
                      ).map(([value, label]) => (
                        <SelectItem key={value} value={value}>
                          {label}
                        </SelectItem>
                      ))}
                    </Select>
                    <span className="confidence-pill">
                      {classificationConfidence ?? "—"}% confidence
                    </span>
                    <Button
                      size="sm"
                      onClick={() =>
                        void act(
                          {
                            kind: "category",
                            category: categoryDraft,
                            reason: "Reviewer accepted the email category",
                          },
                          "Category accepted.",
                        )
                      }
                      disabled={
                        pending ||
                        categoryDraft === item.classification?.accepted
                      }
                    >
                      Accept category
                    </Button>
                  </div>
                </section>
                <div className="content-tabs" role="tablist">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={tab === "comparison"}
                    onClick={() => setTab("comparison")}
                  >
                    Comparison
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={tab === "documents"}
                    onClick={() => setTab("documents")}
                  >
                    Source documents
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={tab === "activity"}
                    onClick={() => setTab("activity")}
                  >
                    Activity
                  </button>
                </div>
                {tab === "comparison" ? (
                  <ComparisonPanel
                    report={item.report}
                    activeField={activeField}
                    setActiveField={setActiveField}
                    activeFinding={activeFinding}
                    siAttachment={siAttachment}
                    blAttachment={blAttachment}
                    openCorrection={openCorrection}
                  />
                ) : null}
                {tab === "documents" ? (
                  <DocumentsPanel
                    attachments={item.attachments}
                    selection={{
                      pairSi,
                      pairBl,
                      pairChanged,
                      setPairSi,
                      setPairBl,
                      currentAttachments,
                    }}
                    controlled={controlled}
                    pending={pending}
                    act={act}
                  />
                ) : null}
                {tab === "activity" ? (
                  <ActivityPanel history={item.history} />
                ) : null}
              </div>
              <aside className="issue-details">
                <div className="details-heading">
                  <h2>Details</h2>
                  <ChevronDown size={17} />
                </div>
                <dl>
                  <div>
                    <dt>Status</dt>
                    <dd>
                      <span
                        className={`status-lozenge ${item.workflow === "completed" ? "success" : item.workflow === "waiting" ? "warning" : "neutral"}`}
                      >
                        {item.workflow.toUpperCase()}
                      </span>
                    </dd>
                  </div>
                  <div>
                    <dt>Assignee</dt>
                    <dd>
                      <Select
                        value={item.assignee}
                        label="Assignee"
                        onValueChange={(assignee) =>
                          void act(
                            {
                              kind: "assign",
                              assignee,
                              reason: "Case assigned",
                            },
                            `Assigned to ${assignee}.`,
                          )
                        }
                        disabled={pending}
                      >
                        {(session?.reviewers ?? []).map((reviewer) => (
                          <SelectItem key={reviewer} value={reviewer}>
                            {reviewer}
                          </SelectItem>
                        ))}
                      </Select>
                    </dd>
                  </div>
                  <div>
                    <dt>Processing</dt>
                    <dd>
                      {item.processing}
                      <small>{item.stage}</small>
                      <small>{item.processing_attempts} of 3 attempts</small>
                      {item.processing_error ? (
                        <small className="processing-error">
                          {item.processing_error}
                        </small>
                      ) : null}
                    </dd>
                  </div>
                  <div>
                    <dt>Input revision</dt>
                    <dd>{item.input_revision}</dd>
                  </div>
                  <div>
                    <dt>Case revision</dt>
                    <dd>{item.revision}</dd>
                  </div>
                  <div>
                    <dt>Reporter</dt>
                    <dd>
                      <UserRound size={15} />
                      {item.sender}
                    </dd>
                  </div>
                </dl>
                <div className="email-description">
                  <h3>Email message</h3>
                  <p>{item.body}</p>
                </div>
              </aside>
            </div>
          </>
        ) : null}
      </div>
      {correctSide && correctionReading && correctionAttachment ? (
        <CorrectionDialog
          key={`${correctionAttachment.id}:${activeField}`}
          activeField={activeField}
          correctionReading={correctionReading}
          correctionAttachment={correctionAttachment}
          pending={pending}
          act={act}
          onClose={() => setCorrectSide(null)}
        />
      ) : null}
    </AppShell>
  );
}

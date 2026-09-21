"use client";
import Link from "next/link";
import {
  AlertCircle,
  ArrowLeft,
  Check,
  CheckCircle2,
  ChevronDown,
  Gauge,
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
import { confidenceDisplay } from "./review/presentation";
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
    category: { categoryDraft, setCategoryDraft, classifying },
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
  const confidence = item ? confidenceDisplay(item.classification) : null;

  return (
    <AppShell contentBusy={pending}>
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
            {!controlled && !session?.live_enabled ? (
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
                <section
                  className="classification-panel"
                  aria-label="Classification"
                >
                  <div className="classification-summary">
                    <h2>Classification</h2>
                    {classifying ? (
                      <p role="status">
                        Classifying… the AI category is not ready yet.
                      </p>
                    ) : !item.classification ? (
                      <p>
                        No AI classification is available. Retry processing to
                        continue.
                      </p>
                    ) : null}
                    {confidence && !classifying ? (
                      <div className="confidence-meter">
                        <p className="confidence-meter-head">
                          {confidence.kind === "reviewer" ? (
                            <UserRound size={16} aria-hidden="true" />
                          ) : (
                            <Gauge size={16} aria-hidden="true" />
                          )}
                          <strong>{confidence.headline}</strong>
                          <span>{confidence.detail}</span>
                        </p>
                        {confidence.kind === "reviewer" ? null : (
                          <div
                            className="confidence-bar"
                            role="img"
                            aria-label={`${confidence.headline}. ${confidence.detail}`}
                          >
                            <span style={{ width: `${confidence.percent}%` }} />
                          </div>
                        )}
                      </div>
                    ) : null}
                  </div>
                  <div className="classification-controls">
                    {item.summary.kind === "spam" ||
                    item.summary.kind === "suspected_spam" ? (
                      <Button
                        disabled={pending}
                        onClick={() =>
                          void act(
                            {
                              kind: "not_spam",
                              reason: "Reviewer marked not spam",
                            },
                            "Returned to Needs review. Choose the appropriate email category.",
                          )
                        }
                      >
                        Not spam
                      </Button>
                    ) : null}
                    {classifying ? (
                      <span className="classifying-pill" role="status">
                        Classifying…
                      </span>
                    ) : (
                      <>
                        <Select
                          value={categoryDraft}
                          label="Email category"
                          placeholder="Choose category"
                          onValueChange={(value) =>
                            setCategoryDraft(value as Category)
                          }
                          disabled={pending}
                        >
                          {(
                            Object.entries(CATEGORY_LABELS) as [
                              Category,
                              string,
                            ][]
                          ).map(([value, label]) => (
                            <SelectItem key={value} value={value}>
                              {label}
                            </SelectItem>
                          ))}
                        </Select>
                        <Button
                          size="sm"
                          onClick={() =>
                            categoryDraft &&
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
                            !categoryDraft ||
                            !item.classification ||
                            categoryDraft === item.classification?.accepted
                          }
                        >
                          Accept category
                        </Button>
                      </>
                    )}
                  </div>
                </section>
                <div className="content-tabs" role="tablist">
                  <button
                    id="comparison-tab"
                    type="button"
                    role="tab"
                    aria-selected={tab === "comparison"}
                    aria-controls="comparison-panel"
                    onClick={() => setTab("comparison")}
                  >
                    Comparison
                  </button>
                  <button
                    id="documents-tab"
                    type="button"
                    role="tab"
                    aria-selected={tab === "documents"}
                    aria-controls="documents-panel"
                    onClick={() => setTab("documents")}
                  >
                    Source documents
                  </button>
                  <button
                    id="activity-tab"
                    type="button"
                    role="tab"
                    aria-selected={tab === "activity"}
                    aria-controls="activity-panel"
                    onClick={() => setTab("activity")}
                  >
                    Activity
                  </button>
                </div>
                {tab === "comparison" ? (
                  <div
                    id="comparison-panel"
                    role="tabpanel"
                    aria-labelledby="comparison-tab"
                  >
                    <ComparisonPanel
                      summaryKind={item.summary.kind}
                      report={item.report}
                      activeField={activeField}
                      setActiveField={setActiveField}
                      activeFinding={activeFinding}
                      siAttachment={siAttachment}
                      blAttachment={blAttachment}
                      openCorrection={openCorrection}
                    />
                  </div>
                ) : null}
                {tab === "documents" ? (
                  <div
                    id="documents-panel"
                    role="tabpanel"
                    aria-labelledby="documents-tab"
                  >
                    <DocumentsPanel
                      attachments={item.attachments}
                      email={{
                        subject: item.subject,
                        sender: item.sender,
                        body: item.body,
                      }}
                      selection={{
                        pairSi,
                        pairBl,
                        pairChanged,
                        setPairSi,
                        setPairBl,
                        currentAttachments,
                      }}
                      controlled={controlled}
                      pairNeedsConfirmation={
                        item.processing === "completed" &&
                        item.report?.pair_valid === false
                      }
                      pending={pending}
                      act={act}
                    />
                  </div>
                ) : null}
                {tab === "activity" ? (
                  <div
                    id="activity-panel"
                    role="tabpanel"
                    aria-labelledby="activity-tab"
                  >
                    <ActivityPanel history={item.history} />
                  </div>
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

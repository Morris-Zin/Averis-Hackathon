"use client";

import Image from "next/image";
import Link from "next/link";
import { AlertCircle, ArrowLeft, Check, CheckCircle2, ChevronDown, Download, FileText, History, LoaderCircle, RefreshCw, RotateCcw, UserRound } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ActionDraft, AttachmentView, CaseView, Category, Field, Finding } from "@/lib/contracts";
import { CATEGORY_LABELS, displayCaseKey, FIELD_LABELS, FIELDS } from "@/lib/contracts";
import { ApiError } from "@/lib/api";
import { useActivePolling } from "@/lib/use-active-polling";
import { AppShell } from "./app-shell";
import { useSession } from "./session-provider";
import { Button, Dialog, Input, Select, SelectItem, Spinner, Textarea } from "./ui";
import { Welcome } from "./welcome";

type Side = "si" | "bl";
type Tab = "comparison" | "documents" | "activity";

function outcomeLabel(outcome: Finding["outcome"]) {
  if (outcome === "match") return "MATCH";
  if (outcome === "mismatch") return "MISMATCH";
  return "NEEDS REVIEW";
}

function readingProvenanceLabel(reading?: Finding["si"]) {
  if (!reading) return "Not read";
  if (reading.provenance === "human_verified") return "Human verified";
  if (reading.provenance === "human_transcribed") return "Human transcription";
  return Math.round(reading.confidence * 100) + "% field confidence";
}

function locationLabel(block: NonNullable<AttachmentView["evidence"]>["blocks"] extends (infer T)[] | undefined ? T : never) {
  const location = block.locations[0];
  if (!location) return "Location unavailable";
  if (location.page) return `Page ${location.page}`;
  if (location.sheet) return `${location.sheet}${location.cell ? ` · ${location.cell}` : ""}`;
  if (location.paragraph) return `Paragraph ${location.paragraph}`;
  if (location.line_start) return location.line_end && location.line_end !== location.line_start ? `Lines ${location.line_start}–${location.line_end}` : `Line ${location.line_start}`;
  return location.kind;
}

function resultSummary(item: CaseView) {
  if (item.processing === "failed") return { label: "Processing failed", tone: "danger", detail: processingFailureDetail(item) };
  if (item.processing !== "completed") return { label: `Processing ${item.processing}`, tone: "neutral", detail: item.stage || "The comparison is not ready yet." };
  const category = item.classification?.accepted ?? item.classification?.suggested;
  if (!category) return { label: "Classification unavailable", tone: "warning", detail: "Review the email before continuing." };
  if (item.review_reasons.length && category !== "BL_COMPARISON") return { label: "Category needs review", tone: "warning", detail: item.review_reasons.join(" · ") };
  if (category !== "BL_COMPARISON") return { label: "Comparison not applicable", tone: "neutral", detail: `This email is categorized as ${CATEGORY_LABELS[category]}.` };
  if (!item.report) return { label: "Comparison unavailable", tone: "warning", detail: "A completed comparison report is required before a result can be stated." };

  const findings = item.report.findings ?? [];
  const mismatches = findings.filter((finding) => finding.outcome === "mismatch").length;
  const unresolved = findings.filter((finding) => finding.outcome === "unresolved").length;
  const allFieldsPresent = findings.length === FIELDS.length && new Set(findings.map((finding) => finding.field)).size === FIELDS.length;
  const blocking = !item.report.pair_valid || Boolean(item.report.issues?.length) || Boolean(item.review_reasons.length) || unresolved > 0 || !allFieldsPresent;
  if (mismatches && blocking) return { label: `${mismatches} ${mismatches === 1 ? "mismatch" : "mismatches"}; review also required`, tone: "danger", detail: "Known mismatches are retained while incomplete or uncertain evidence is reviewed." };
  if (mismatches) return { label: `${mismatches} ${mismatches === 1 ? "mismatch" : "mismatches"} found`, tone: "danger", detail: "This case is routed to human review." };
  if (!blocking && findings.every((finding) => finding.outcome === "match")) return { label: "No mismatch detected", tone: "success", detail: "The pair is valid and all seven shipment fields agree with no blocking report issues." };
  return { label: "Comparison needs review", tone: "warning", detail: item.report.issues?.join(" · ") || item.review_reasons.join(" · ") || "The report is incomplete or contains uncertain evidence." };
}

function processingFailureDetail(item: CaseView) {
  const attempts = item.processing_attempts
    ? " after " + item.processing_attempts + (item.processing_attempts === 1 ? " attempt" : " attempts")
    : "";
  const reason = item.processing_error ? " " + item.processing_error : "";
  return "Document processing could not finish" + attempts + "." + reason
    + " Review the source documents, then run the check again when live AI processing is available.";
}

function EvidencePane({ attachment, selectedIds, title, onCorrect }: { attachment?: AttachmentView; selectedIds: string[]; title: string; onCorrect: () => void }) {
  const blocks = attachment?.evidence?.blocks ?? [];
  const previewBlock = blocks.find((block) => selectedIds.includes(block.id)) ?? blocks[0];
  const previewLocation = previewBlock?.locations.find((location) => location.kind === "pdf" || location.kind === "image");
  const previewPage = previewLocation?.page ?? 1;
  const roleConfidence = attachment?.role_confidence == null ? null : Math.round(attachment.role_confidence * 100);
  return (
    <section className="evidence-pane">
      <header><div><span>{title}{attachment?.superseded ? " · Previous version" : ""}</span><strong>{attachment?.filename ?? "No document selected"}</strong>{roleConfidence !== null ? <small className="role-confidence" title="Confidence that this document has the assigned SI or draft BL role">Role confidence {roleConfidence}%</small> : null}</div>{attachment ? <a className="icon-link" href={`/api/documents/${encodeURIComponent(attachment.id)}/content`} target="_blank" rel="noreferrer" aria-label={`Open ${attachment.filename}`}><Download size={16} /></a> : null}</header>
      <div className="document-paper">
        {attachment && previewLocation ? <div className="document-render"><span>Rendered {previewLocation.kind === "pdf" ? `page ${previewPage}` : "image"}</span><Image unoptimized src={`/api/documents/${encodeURIComponent(attachment.id)}/preview?page=${previewPage}`} alt={`Rendered source preview for ${attachment.filename}`} width={900} height={1200} /></div> : null}
        {blocks.length ? blocks.map((block) => <div key={block.id} className={selectedIds.includes(block.id) ? "evidence-block selected" : "evidence-block"}><small>{locationLabel(block)}</small><p>{block.text}</p>{block.method === "ocr" ? <span className="ocr-tag">OCR</span> : null}</div>) : <div className="empty-evidence"><FileText size={24} /><span>No source evidence is available for this document.</span></div>}
      </div>
      <footer><Button size="sm" onClick={onCorrect} disabled={!attachment || attachment.superseded}>Correct our reading</Button><span>{attachment?.superseded ? "Previous versions are read-only" : "Original file stays unchanged"}</span></footer>
    </section>
  );
}

export function ReviewWorkspace() {
  const params = useSearchParams();
  const id = params.get("case") ?? "";
  const { status, session, api } = useSession();
  const [item, setItem] = useState<CaseView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState(false);
  const [tab, setTab] = useState<Tab>("comparison");
  const [activeField, setActiveField] = useState<Field>("shipper");
  const [correctSide, setCorrectSide] = useState<Side | null>(null);
  const [transcription, setTranscription] = useState("");
  const [reason, setReason] = useState("");
  const [evidenceIds, setEvidenceIds] = useState<string[]>([]);
  const [verified, setVerified] = useState(false);
  const [categoryDraft, setCategoryDraft] = useState<Category>("BL_COMPARISON");
  const [pairSi, setPairSi] = useState("");
  const [pairBl, setPairBl] = useState("");
  const requestVersion = useRef(0);
  const requestController = useRef<AbortController | null>(null);

  useEffect(() => {
    if (status === "ready") return;
    requestVersion.current += 1;
    requestController.current?.abort();
    requestController.current = null;
    setItem(null);
    setError("");
    setNotice("");
    setPending(false);
    setCorrectSide(null);
    setTranscription("");
    setReason("");
    setEvidenceIds([]);
    setVerified(false);
    setCategoryDraft("GENERAL");
    setPairSi("");
    setPairBl("");
  }, [status]);

  const load = useCallback(async (
    background = false,
    resetDrafts = !background,
    pollingSignal?: AbortSignal,
  ): Promise<boolean> => {
    if (status !== "ready") return false;
    if (!id) {
      setItem(null);
      setError("No case was selected.");
      setLoading(false);
      return false;
    }
    if (background && requestController.current) return false;
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    const version = ++requestVersion.current;
    const abortForPolling = () => controller.abort();
    pollingSignal?.addEventListener("abort", abortForPolling, { once: true });
    if (!background) {
      setLoading(true);
      setError("");
    }
    try {
      const value = await api.case(id, controller.signal);
      if (controller.signal.aborted || version !== requestVersion.current) return false;
      setItem(value);
      if (resetDrafts) {
        setCategoryDraft(value.classification?.accepted ?? value.classification?.suggested ?? "GENERAL");
        setPairSi(value.attachments.find((attachment) => attachment.role === "SI" && !attachment.superseded)?.id ?? "");
        setPairBl(value.attachments.find((attachment) => attachment.role === "BL" && !attachment.superseded)?.id ?? "");
        const important = value.report?.findings?.find((finding) => finding.outcome !== "match")?.field;
        if (important) setActiveField(important);
      }
      return true;
    } catch (reasonValue) {
      if (controller.signal.aborted || version !== requestVersion.current) return false;
      if (!background) setError(reasonValue instanceof Error ? reasonValue.message : "Case could not be loaded.");
      return false;
    } finally {
      pollingSignal?.removeEventListener("abort", abortForPolling);
      if (version === requestVersion.current) {
        requestController.current = null;
        if (!background) setLoading(false);
      }
    }
  }, [api, id, status]);

  useEffect(() => { void load(false, true); }, [load]);

  useEffect(() => () => {
    requestVersion.current += 1;
    requestController.current?.abort();
  }, []);

  const act = useCallback(async (action: ActionDraft, success: string) => {
    if (!item || !session) return false;
    requestVersion.current += 1;
    requestController.current?.abort();
    requestController.current = null;
    setPending(true);
    setError("");
    setNotice("");
    try {
      const updated = await api.action(item.id, { verified: false, reason: "", ...action, expected_revision: item.revision }, session.csrf_token);
      setItem(updated);
      if (action.kind === "revision" || action.kind === "pair") {
        setPairSi(updated.attachments.find((attachment) => attachment.role === "SI" && !attachment.superseded)?.id ?? "");
        setPairBl(updated.attachments.find((attachment) => attachment.role === "BL" && !attachment.superseded)?.id ?? "");
        setCorrectSide(null);
        setEvidenceIds([]);
        setTranscription("");
        setVerified(false);
      }
      if (action.kind === "category") {
        setCategoryDraft(updated.classification?.accepted ?? updated.classification?.suggested ?? "GENERAL");
      }
      setNotice(success);
      return true;
    } catch (reasonValue) {
      if (reasonValue instanceof ApiError && reasonValue.status === 409) {
        const refreshed = await load(false, false);
        if (refreshed) setError("This case changed while you were reviewing it. Your change was not saved. The latest version has been loaded.");
      } else setError(reasonValue instanceof Error ? reasonValue.message : "The action could not be saved.");
      return false;
    } finally { setPending(false); }
  }, [api, item, load, session]);

  const processingActive = item?.processing === "queued" || item?.processing === "running";
  const poll = useCallback((signal: AbortSignal) => load(true, false, signal), [load]);
  useActivePolling(status === "ready" && Boolean(item) && processingActive && !pending && !loading, poll);

  const activeFinding = item?.report?.findings?.find((finding) => finding.field === activeField);
  const siAttachment = activeFinding ? item?.attachments.find((attachment) => attachment.id === activeFinding.si.document_id) : item?.attachments.find((attachment) => attachment.role === "SI" && !attachment.superseded);
  const blAttachment = activeFinding ? item?.attachments.find((attachment) => attachment.id === activeFinding.bl.document_id) : item?.attachments.find((attachment) => attachment.role === "BL" && !attachment.superseded);
  const correctionReading = correctSide === "si" ? activeFinding?.si : activeFinding?.bl;
  const correctionAttachment = item?.attachments.find((attachment) => attachment.id === correctionReading?.document_id && !attachment.superseded);
  const selectedCorrectionBlocks = correctionAttachment?.evidence?.blocks?.filter((block) => evidenceIds.includes(block.id)) ?? [];
  const selectedAreOcr = selectedCorrectionBlocks.length > 0 && selectedCorrectionBlocks.every((block) => block.method === "ocr");
  const currentAttachments = item?.attachments.filter((attachment) => !attachment.superseded) ?? [];
  const controlled = item?.history.some((entry) => entry.actor === "Demo setup") ?? false;
  const summary = item ? resultSummary(item) : null;
  const classificationConfidence = item?.classification ? Math.round(item.classification.confidence * 100) : null;
  const pairChanged = item ? pairSi !== (item.attachments.find((attachment) => attachment.role === "SI" && !attachment.superseded)?.id ?? "") || pairBl !== (item.attachments.find((attachment) => attachment.role === "BL" && !attachment.superseded)?.id ?? "") : false;
function openCorrection(side: Side) {
    const reading = side === "si" ? activeFinding?.si : activeFinding?.bl;
    const source = item?.attachments.find((attachment) => attachment.id === reading?.document_id && !attachment.superseded);
    if (!reading || !source) return;
    setCorrectSide(side);
    setTranscription(reading.text ?? "");
    setEvidenceIds(reading.evidence_ids ?? []);
    setReason("");
    setVerified(false);
  }

  async function saveCorrection() {
    if (!correctSide || !correctionReading || !correctionAttachment || !evidenceIds.length || !reason.trim()) return;
    if (selectedAreOcr && (!transcription.trim() || !verified)) return;
    const saved = await act({ kind: "correct", field: activeField, document_id: correctionAttachment.id, transcription: selectedAreOcr ? transcription.trim() : undefined, evidence_ids: evidenceIds, verified: selectedAreOcr ? verified : true, reason: reason.trim() }, "Reading corrected and comparison recomputed.");
    if (saved) setCorrectSide(null);
  }
  if (status === "loading") return <main className="initial-loading"><Spinner label="Opening case" /></main>;
  if (status !== "ready") return <Welcome />;

  return (
    <AppShell>
      <div className="review-page">
        <div className="review-breadcrumbs"><Link href="/"><ArrowLeft size={15} />Queues</Link><span>/</span><span>{item ? displayCaseKey(item.id) : "Case"}</span></div>
        {loading ? <div className="review-loading"><Spinner label="Loading case" /></div> : error && !item ? <div className="table-state error-state"><strong>Case could not be loaded</strong><span>{error || "Choose a case from the queue."}</span><Link className="button button-secondary button-md" href="/">Back to queues</Link></div> : item ? <>
          <header className="issue-header">
            <div><p className="issue-key" title={item.id}>{displayCaseKey(item.id)}</p><h1>{item.subject}</h1><p>From {item.sender} · {new Date(item.received_at).toLocaleString()}</p></div>
            <div className="issue-header-actions"><Button onClick={() => void act({ kind: "retry", reason: controlled ? "Reviewer requested live processing for the saved illustrative sample" : "Reviewer requested a processing retry" }, controlled ? "Live check requested." : "Processing retry requested.")} disabled={pending || processingActive || !session?.live_enabled} title={!session?.live_enabled ? "Live AI processing is disabled" : processingActive ? "A processing run is already active" : controlled ? "Run live AI processing on this saved illustrative sample" : undefined}><RotateCcw size={15} />{processingActive ? "Live check running..." : controlled ? "Run live check" : "Retry"}</Button><Select value={item.workflow} label="Workflow status" onValueChange={(workflow) => void act({ kind: "workflow", workflow: workflow as CaseView["workflow"], reason: "Workflow status changed" }, "Moved to " + workflow + ".")} disabled={pending}><SelectItem value="open">Open</SelectItem><SelectItem value="waiting">Waiting</SelectItem><SelectItem value="completed">Completed</SelectItem></Select></div>
          </header>
          {controlled ? <div className="demo-banner compact"><strong>Saved illustrative scenario</strong><span>{session?.live_enabled ? "The email and source documents are synthetic. Live AI can check this saved sample." : "Classification is illustrative; comparison and corrections are deterministic and persisted in this server session. Live AI and email are off."}</span></div> : !session?.live_enabled ? <div className="demo-banner compact"><strong>Controlled server demo</strong><span>Live AI and email are off.</span></div> : null}
          {error ? <div className="inline-message error" role="alert"><AlertCircle size={16} />{error}</div> : null}
          {notice ? <div className="inline-message success" role="status"><CheckCircle2 size={16} />{notice}</div> : null}
          <div className="issue-actions-row"><Button variant="primary" onClick={() => setTab("comparison")}>Review comparison</Button><Button onClick={() => setTab("documents")}>View source documents</Button><Button onClick={() => setTab("activity")}>View history</Button></div>
          <div className="issue-layout">
            <div className="issue-main">
              <section className={`result-banner ${summary?.tone}`}><span className="result-icon">{summary?.tone === "success" ? <Check size={20} /> : <AlertCircle size={20} />}</span><div><strong>{summary?.label}</strong><p>{summary?.detail}</p></div></section>
              <section className="classification-panel">
                <div><h2>Classification</h2><p>Confidence shows certainty in the category prediction. It is not measured accuracy.</p></div>
                <div className="classification-controls"><Select value={categoryDraft} label="Email category" onValueChange={(value) => setCategoryDraft(value as Category)} disabled={pending}>{(Object.entries(CATEGORY_LABELS) as [Category, string][]).map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</Select><span className="confidence-pill">{classificationConfidence ?? "—"}% confidence</span><Button size="sm" onClick={() => void act({ kind: "category", category: categoryDraft, reason: "Reviewer accepted the email category" }, "Category accepted.")} disabled={pending || categoryDraft === item.classification?.accepted}>Accept category</Button></div>
              </section>
              <div className="content-tabs" role="tablist"><button type="button" role="tab" aria-selected={tab === "comparison"} onClick={() => setTab("comparison")}>Comparison</button><button type="button" role="tab" aria-selected={tab === "documents"} onClick={() => setTab("documents")}>Source documents</button><button type="button" role="tab" aria-selected={tab === "activity"} onClick={() => setTab("activity")}>Activity</button></div>
              {tab === "comparison" ? <>
                <section className="comparison-section"><div className="section-heading"><div><h2>Shipment comparison</h2><p>Shipping instruction is the reference.</p></div><span>{item.report?.findings?.length ?? 0} of 7 fields read</span></div>
                  <div className="comparison-table-wrap"><table className="comparison-table"><thead><tr><th>Field</th><th>Shipping instruction</th><th>Draft bill of lading</th><th>Result</th></tr></thead><tbody>{FIELDS.map((field) => {
                    const finding = item.report?.findings?.find((candidate) => candidate.field === field);
                    return <tr key={field} className={activeField === field ? "active" : ""} onClick={() => setActiveField(field)}><th><button type="button" onClick={() => setActiveField(field)}>{FIELD_LABELS[field]}</button></th><td><span className={!finding?.si.text ? "empty-value" : ""}>{finding?.si.text || "Not found"}</span><small>{readingProvenanceLabel(finding?.si)}</small></td><td><span className={!finding?.bl.text ? "empty-value" : ""}>{finding?.bl.text || "Not found"}</span><small>{readingProvenanceLabel(finding?.bl)}</small></td><td><span className={`status-lozenge ${finding?.outcome === "match" ? "success" : finding?.outcome === "mismatch" ? "danger" : "warning"}`}>{finding ? outcomeLabel(finding.outcome) : "NOT READ"}</span></td></tr>;
                  })}</tbody></table></div>
                </section>
                <section className="evidence-section"><div className="section-heading"><div><h2>Evidence for {FIELD_LABELS[activeField].toLocaleLowerCase()}</h2><p>Select a field above to inspect its exact source.</p></div></div><div className="evidence-grid"><EvidencePane attachment={siAttachment} selectedIds={activeFinding?.si.evidence_ids ?? []} title="Shipping instruction" onCorrect={() => openCorrection("si")} /><EvidencePane attachment={blAttachment} selectedIds={activeFinding?.bl.evidence_ids ?? []} title="Draft bill of lading" onCorrect={() => openCorrection("bl")} /></div></section>
              </> : null}
              {tab === "documents" ? <section className="documents-section">
                <div className="section-heading"><div><h2>Source documents</h2><p>Choose the current SI and draft BL used for comparison. Previous versions remain available as history.</p></div></div>
                <div className="pair-controls"><label><span>Shipping instruction</span><Select value={pairSi} label="Shipping instruction document" onValueChange={setPairSi}>{currentAttachments.map((attachment) => <SelectItem key={attachment.id} value={attachment.id}>{attachment.filename}</SelectItem>)}</Select></label><label><span>Draft bill of lading</span><Select value={pairBl} label="Draft bill of lading document" onValueChange={setPairBl}>{currentAttachments.map((attachment) => <SelectItem key={attachment.id} value={attachment.id}>{attachment.filename}</SelectItem>)}</Select></label><Button variant="primary" disabled={!pairChanged || !pairSi || !pairBl || pairSi === pairBl || pending} onClick={() => void act({ kind: "pair", si_id: pairSi, bl_id: pairBl, reason: "Reviewer selected the current document pair" }, "Document pair updated.")}>Recompute comparison</Button></div>
                <div className="attachment-list">{item.attachments.map((attachment) => <a key={attachment.id} className={attachment.superseded ? "previous-version" : ""} href={`/api/documents/${encodeURIComponent(attachment.id)}/content`} target="_blank" rel="noreferrer"><FileText size={20} /><span><strong>{attachment.filename}</strong><small>{attachment.superseded ? "Previous version" : attachment.role} · {attachment.evidence?.blocks?.length ?? 0} evidence blocks</small></span><Download size={16} /></a>)}</div>
                {controlled ? <Button onClick={() => void act({ kind: "revision", reason: "Reviewer requested the controlled revised draft" }, "Controlled revised draft attached and comparison recomputed.")} disabled={pending}><RefreshCw size={15} />Attach controlled revised draft</Button> : <p className="readonly-note">New source versions require the authorized operator upload workflow.</p>}
              </section> : null}
              {tab === "activity" ? <section className="activity-section"><div className="section-heading"><div><h2>Activity</h2><p>Classification, corrections, assignments, and workflow changes are retained.</p></div></div><ol>{item.history.map((entry, index) => <li key={`${entry.at}-${index}`}><span className="activity-icon"><History size={15} /></span><div><p><strong>{entry.actor}</strong> · {entry.action}</p><span>{entry.detail}</span><small>{new Date(entry.at).toLocaleString()}</small></div></li>)}</ol></section> : null}
            </div>
            <aside className="issue-details"><div className="details-heading"><h2>Details</h2><ChevronDown size={17} /></div><dl><div><dt>Status</dt><dd><span className={`status-lozenge ${item.workflow === "completed" ? "success" : item.workflow === "waiting" ? "warning" : "neutral"}`}>{item.workflow.toUpperCase()}</span></dd></div><div><dt>Assignee</dt><dd><Select value={item.assignee} label="Assignee" onValueChange={(assignee) => void act({ kind: "assign", assignee, reason: "Case assigned" }, `Assigned to ${assignee}.`)} disabled={pending}>{(session?.reviewers ?? []).map((reviewer) => <SelectItem key={reviewer} value={reviewer}>{reviewer}</SelectItem>)}</Select></dd></div><div><dt>Processing</dt><dd>{item.processing}<small>{item.stage}</small><small>{item.processing_attempts} of 3 attempts</small>{item.processing_error ? <small className="processing-error">{item.processing_error}</small> : null}</dd></div><div><dt>Input revision</dt><dd>{item.input_revision}</dd></div><div><dt>Case revision</dt><dd>{item.revision}</dd></div><div><dt>Reporter</dt><dd><UserRound size={15} />{item.sender}</dd></div></dl><div className="email-description"><h3>Email message</h3><p>{item.body}</p></div></aside>
          </div>
        </> : null}
      </div>
      <Dialog open={correctSide !== null} onOpenChange={(open) => { if (!open) setCorrectSide(null); }} title={`Correct ${FIELD_LABELS[activeField].toLocaleLowerCase()} reading`} description="This changes Averis's reading of the source. It does not alter the original document or hide a real discrepancy.">
        <div className="correction-form">
          {selectedAreOcr ? <label><span>Verified OCR transcription</span><Textarea value={transcription} onChange={(event) => setTranscription(event.target.value)} rows={3} /></label> : <div className="correction-note"><p>Select the exact native source block below. Averis will recompute from that unchanged source text.</p><blockquote>{selectedCorrectionBlocks.length ? selectedCorrectionBlocks.map((block) => block.text).join("\\n") : "No evidence selected"}</blockquote></div>}
          <fieldset><legend>Evidence from {correctionAttachment?.filename ?? "selected document"}</legend>{correctionAttachment?.evidence?.blocks?.map((block) => <label className="evidence-option" key={block.id}><input type="checkbox" checked={evidenceIds.includes(block.id)} onChange={(event) => setEvidenceIds((values) => event.target.checked ? [...values, block.id] : values.filter((idValue) => idValue !== block.id))} /><span><strong>{locationLabel(block)}</strong>{block.text}</span></label>)}</fieldset>
          {selectedAreOcr ? <label className="verify-check"><input type="checkbox" checked={verified} onChange={(event) => setVerified(event.target.checked)} /><span>I checked this transcription against the rendered original.</span></label> : null}
          <label><span>Reason for correction</span><Input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="What evidence selection or reading was wrong?" /></label>
          <div className="dialog-actions"><Button onClick={() => setCorrectSide(null)}>Cancel</Button><Button variant="primary" onClick={() => void saveCorrection()} disabled={!evidenceIds.length || !reason.trim() || pending || (selectedAreOcr && (!transcription.trim() || !verified))}>{pending ? <><LoaderCircle className="spin" size={15} />Saving…</> : "Save and recompute"}</Button></div>
        </div>
      </Dialog>
    </AppShell>
  );
}

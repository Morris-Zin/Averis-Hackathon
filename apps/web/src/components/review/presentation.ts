import type { CaseView, Finding } from "@/lib/contracts";
import { CATEGORY_LABELS } from "@/lib/contracts";

export function outcomeLabel(outcome: Finding["outcome"]) {
  if (outcome === "match") return "MATCH";
  if (outcome === "mismatch") return "MISMATCH";
  return "NEEDS REVIEW";
}

export function readingProvenanceLabel(reading?: Finding["si"]) {
  if (!reading) return "Not read";
  if (reading.provenance === "human_verified") return "Human verified";
  if (reading.provenance === "human_transcribed") return "Human transcription";
  return Math.round(reading.confidence * 100) + "% field confidence";
}

function processingFailureDetail(item: CaseView) {
  const attempts = item.processing_attempts
    ? " after " +
      item.processing_attempts +
      (item.processing_attempts === 1 ? " attempt" : " attempts")
    : "";
  const reason = item.processing_error ? " " + item.processing_error : "";
  return (
    "Document processing could not finish" +
    attempts +
    "." +
    reason +
    " Review the source documents, then run the check again when live AI processing is available."
  );
}

export function resultSummary(item: CaseView) {
  const kind = item.summary.kind;
  const mismatches = item.summary.mismatches;
  const accepted = item.classification?.accepted;
  switch (kind) {
    case "failed":
      return {
        label: "Processing failed",
        tone: "danger",
        detail: processingFailureDetail(item),
      };
    case "queued":
    case "running":
      return {
        label: `Processing ${kind}`,
        tone: "neutral",
        detail: item.stage || "The comparison is not ready yet.",
      };
    case "unclassified":
      return {
        label: "Classification unavailable",
        tone: "warning",
        detail: "Review the email before continuing.",
      };
    case "categorized":
      return {
        label: "Comparison not applicable",
        tone: "neutral",
        detail: accepted
          ? `This email is categorized as ${CATEGORY_LABELS[accepted]}.`
          : "This email does not require a shipment comparison.",
      };
    case "match":
      return {
        label: "No mismatch detected",
        tone: "success",
        detail:
          "The pair is valid and all seven shipment fields agree with no blocking report issues.",
      };
    case "mismatch":
      return {
        label: `${mismatches} ${mismatches === 1 ? "mismatch" : "mismatches"} found`,
        tone: "danger",
        detail: "This case is routed to human review.",
      };
    case "mismatch_review":
      return {
        label: `${mismatches} ${mismatches === 1 ? "mismatch" : "mismatches"}; review also required`,
        tone: "danger",
        detail:
          "Known mismatches are retained while incomplete or uncertain evidence is reviewed.",
      };
    case "needs_review":
      return {
        label: "Needs review",
        tone: "warning",
        detail:
          item.review_reasons.join(" · ") ||
          item.report?.issues?.join(" · ") ||
          "The report is incomplete or contains uncertain evidence.",
      };
  }
}

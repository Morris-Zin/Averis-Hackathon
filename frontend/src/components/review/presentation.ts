import type { CaseView, Finding } from "@/lib/contracts";
import { CATEGORY_LABELS } from "@/lib/contracts";

export function readingDisplayValue(reading?: Finding["si"]) {
  if (reading?.numeric_selection && reading.normalized != null) {
    return `${reading.normalized}${reading.field === "gross_weight_kg" ? " kg" : ""}`;
  }
  return reading?.text || "Not found";
}

export const PAIR_REVIEW_REASON =
  "Human review requested: we could not verify a shared shipment reference between the SI and draft BL.";

const READING_ISSUES: Record<string, string> = {
  ambiguous_source_fields:
    "Several fields appear together in the selected text. Select this field and check its source before correcting our reading.",
  source_field_mismatch:
    "The selected text appears to describe a different field. Check the source and select the correct evidence.",
  incomplete_party_evidence:
    "Part of the name or address may be missing. Check the source and include all relevant lines.",
  missing_value:
    "No value was found. Check whether the source contains this field or request a complete document.",
  missing_or_ambiguous_value:
    "We could not read one clear value or its required unit. Check the source before correcting our reading.",
  low_field_confidence:
    "The AI is unsure which text belongs to this field. Check the selected evidence.",
  low_ocr_confidence:
    "The scanned text was not read reliably. Check the image and verify the reading, or upload a clearer document.",
  unknown_ocr_confidence:
    "We could not verify the scanned text's reading quality. Check the image and verify the reading.",
  unverified_transcription:
    "This typed reading has not been verified against the image. Check it and confirm it matches the original image.",
  destination_port_requires_review:
    "The document also lists a discharge port. Check that field; the final destination may be a different port.",
};

export function readingIssueLabel(issue: string) {
  return (
    READING_ISSUES[issue] ??
    `Check the source before accepting this reading (${issue.replaceAll("_", " ")}).`
  );
}

export function issueLabel(
  issue: NonNullable<NonNullable<CaseView["report"]>["issues"]>[number],
) {
  if (typeof issue === "string")
    return issue === "pair_requires_review"
      ? PAIR_REVIEW_REASON
      : issue.replaceAll("_", " ");
  const scope =
    issue.scope === "unused_attachment" ? "Unused attachment: " : "";
  return `${scope}${issue.code.replaceAll("_", " ")}${issue.detail ? `: ${issue.detail}` : ""}`;
}

export function confidenceDisplay(classification: CaseView["classification"]) {
  if (!classification) return null;
  const percent = Math.round(classification.confidence * 100);
  if (classification.source === "human")
    return {
      kind: "reviewer" as const,
      percent,
      headline: classification.accepted
        ? "Reviewer classified"
        : "Reviewer marked not spam; category required",
      detail: `Original AI suggestion: ${CATEGORY_LABELS[classification.suggested]} (${percent}%)`,
    };
  if (classification.source === "fixture")
    return {
      kind: "demo" as const,
      percent,
      headline: `Classification confidence: ${percent}%`,
      detail: "Illustrative demo value, not a live AI result",
    };
  return {
    kind: "ai" as const,
    percent,
    headline: `Classification confidence: ${percent}%`,
    detail: `Suggested by ${classification.model}. AI certainty in the category, not measured accuracy.`,
  };
}

export function outcomeLabel(outcome: Finding["outcome"]) {
  if (outcome === "match") return "MATCH";
  if (outcome === "mismatch") return "MISMATCH";
  return "NEEDS REVIEW";
}

export function readingProvenanceLabel(reading?: Finding["si"]) {
  if (!reading) return "Not read";
  if (reading.provenance === "human_verified") return "Human verified";
  if (reading.provenance === "human_transcribed") return "Human transcription";
  if (reading.assistance_error)
    return "Additional AI unavailable; review the source";
  if (reading.acceptance_basis === "explicit_source" && !reading.issue)
    return "Selected by DeepSeek · source checks passed";
  if (reading.acceptance_basis === "explicit_source")
    return "Selected by DeepSeek · source check requires review";
  if (reading.confidence == null)
    return "Machine reading · confidence unavailable";
  return (
    Math.round(reading.confidence * 100) +
    "% AI selection confidence" +
    (reading.issue ? " · source check requires review" : "")
  );
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
    case "suspected_spam":
      return {
        label: "Suspected spam",
        tone: "warning",
        detail:
          "The AI suggested spam, but the classification was not accepted. Kept in Spam for optional inspection. Choose Not spam to return it to review.",
      };
    case "spam":
      return {
        label: "Spam",
        tone: "neutral",
        detail:
          "This message is classified as spam and retained here. Choose Not spam to return it to classification review.",
      };
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
        detail:
          item.stage === "classified"
            ? "Category decided; reading source documents."
            : item.stage || "The comparison is not ready yet.",
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
          item.report?.pair_valid === false
            ? `${PAIR_REVIEW_REASON} Open Source documents to check whether they belong to the same shipment.`
            : item.review_reasons.join(" · ") ||
              item.report?.issues?.map(issueLabel).join(" · ") ||
              "The report is incomplete or contains uncertain evidence.",
      };
  }
}

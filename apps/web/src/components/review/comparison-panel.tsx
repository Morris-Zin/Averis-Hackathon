import type { AttachmentView, CaseView, Field, Finding } from "@/lib/contracts";
import { FIELD_LABELS, FIELDS } from "@/lib/contracts";
import { EvidencePane } from "./evidence-pane";
import {
  issueLabel,
  outcomeLabel,
  readingProvenanceLabel,
} from "./presentation";

type Props = {
  summaryKind: CaseView["summary"]["kind"];
  report: CaseView["report"];
  activeField: Field;
  setActiveField: (field: Field) => void;
  activeFinding?: Finding;
  siAttachment?: AttachmentView;
  blAttachment?: AttachmentView;
  openCorrection: (side: "si" | "bl") => void;
};

export function ComparisonPanel({
  summaryKind,
  report,
  activeField,
  setActiveField,
  activeFinding,
  siAttachment,
  blAttachment,
  openCorrection,
}: Props) {
  if (summaryKind === "categorized") {
    return (
      <section className="comparison-section">
        <div className="section-heading">
          <div>
            <h2>No shipment comparison needed</h2>
            <p>
              Review the email and its category, then update the workflow when
              your work is complete. Source documents and history remain
              available.
            </p>
          </div>
        </div>
      </section>
    );
  }
  const checkedFields =
    report?.findings?.filter((finding) => finding.outcome !== "unresolved")
      .length ?? 0;
  return (
    <>
      <section className="comparison-section">
        <div className="section-heading">
          <div>
            <h2>Shipment comparison</h2>
            <p>Shipping instruction is the reference.</p>
          </div>
          <span>{checkedFields} of 7 fields checked</span>
        </div>
        <div className="comparison-table-wrap">
          {report?.issues?.length ? (
            <ul aria-label="Document review reasons">
              {report.issues.map((issue, index) => (
                <li key={index}>{issueLabel(issue)}</li>
              ))}
            </ul>
          ) : null}
          <table className="comparison-table">
            <thead>
              <tr>
                <th>Field</th>
                <th>Shipping instruction</th>
                <th>Draft bill of lading</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {FIELDS.map((field) => {
                const finding = report?.findings?.find(
                  (candidate) => candidate.field === field,
                );
                return (
                  <tr
                    key={field}
                    className={activeField === field ? "active" : ""}
                    onClick={() => setActiveField(field)}
                  >
                    <th>
                      <button
                        type="button"
                        onClick={() => setActiveField(field)}
                      >
                        {FIELD_LABELS[field]}
                      </button>
                    </th>
                    <td>
                      <span className={!finding?.si.text ? "empty-value" : ""}>
                        {finding?.si.text || "Not found"}
                      </span>
                      <small>{readingProvenanceLabel(finding?.si)}</small>
                      {finding?.si.issue ? (
                        <small>
                          Needs review: {finding.si.issue.replaceAll("_", " ")}
                        </small>
                      ) : null}
                    </td>
                    <td>
                      <span className={!finding?.bl.text ? "empty-value" : ""}>
                        {finding?.bl.text || "Not found"}
                      </span>
                      <small>{readingProvenanceLabel(finding?.bl)}</small>
                      {finding?.bl.issue ? (
                        <small>
                          Needs review: {finding.bl.issue.replaceAll("_", " ")}
                        </small>
                      ) : null}
                    </td>
                    <td>
                      <span
                        className={`status-lozenge ${finding?.outcome === "match" ? "success" : finding?.outcome === "mismatch" ? "danger" : "warning"}`}
                      >
                        {finding ? outcomeLabel(finding.outcome) : "NOT READ"}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      <section className="evidence-section">
        <div className="section-heading">
          <div>
            <h2>
              Evidence for {FIELD_LABELS[activeField].toLocaleLowerCase()}
            </h2>
            <p>Select a field above to inspect its exact source.</p>
          </div>
        </div>
        <div className="evidence-grid">
          <EvidencePane
            attachment={siAttachment}
            selectedIds={activeFinding?.si.evidence_ids ?? []}
            title="Shipping instruction"
            onCorrect={() => openCorrection("si")}
          />
          <EvidencePane
            attachment={blAttachment}
            selectedIds={activeFinding?.bl.evidence_ids ?? []}
            title="Draft bill of lading"
            onCorrect={() => openCorrection("bl")}
          />
        </div>
      </section>
    </>
  );
}

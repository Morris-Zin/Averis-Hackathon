import type { components } from "./generated/api";

export type Category = components["schemas"]["CategoryAction"]["category"];
export type Field = components["schemas"]["CorrectAction"]["field"];
export type EvidenceBlock = components["schemas"]["EvidenceBlock"];
export type AttachmentView = components["schemas"]["AttachmentView"];
export type Finding = components["schemas"]["Finding"];
export type CaseView = components["schemas"]["CaseResponse"];
export type CasePage = components["schemas"]["CasePageResponse"];
export type SessionView = components["schemas"]["SessionView"];
export type Action =
  | components["schemas"]["CategoryAction"]
  | components["schemas"]["PairAction"]
  | components["schemas"]["CorrectAction"]
  | components["schemas"]["AssignAction"]
  | components["schemas"]["WorkflowAction"]
  | components["schemas"]["RetryAction"]
  | components["schemas"]["RevisionAction"];
// Drafts omit the revision; each action sends only its own relevant fields.
// Required payload fields fail at the HTTP boundary; ownership and source
// validity remain domain checks.
export type ActionDraft =
  | Omit<components["schemas"]["CategoryAction"], "expected_revision">
  | Omit<components["schemas"]["PairAction"], "expected_revision">
  | Omit<components["schemas"]["CorrectAction"], "expected_revision">
  | Omit<components["schemas"]["AssignAction"], "expected_revision">
  | Omit<components["schemas"]["WorkflowAction"], "expected_revision">
  | Omit<components["schemas"]["RetryAction"], "expected_revision">
  | Omit<components["schemas"]["RevisionAction"], "expected_revision">;

export const FIELDS: Field[] = [
  "shipper",
  "consignee",
  "notify_party",
  "port_of_loading",
  "port_of_discharge",
  "container_count",
  "gross_weight_kg",
];

export const FIELD_LABELS: Record<Field, string> = {
  shipper: "Shipper",
  consignee: "Consignee",
  notify_party: "Notify party",
  port_of_loading: "Port of loading",
  port_of_discharge: "Port of discharge",
  container_count: "Container count",
  gross_weight_kg: "Gross weight",
};

export const CATEGORY_LABELS: Record<Category, string> = {
  BL_COMPARISON: "Shipping instruction check",
  SI_REQUEST: "Shipping instruction request",
  INVOICE_QUERY: "Invoice query",
  GENERAL: "General",
  SPAM: "Spam",
};

export type QueueView =
  | "all"
  | "mismatches"
  | "review"
  | "waiting"
  | "completed";

export function displayCaseKey(id: string) {
  const compact = id
    .replace(/[^a-zA-Z0-9]/g, "")
    .slice(0, 8)
    .toUpperCase();
  return `AV-${compact}`;
}

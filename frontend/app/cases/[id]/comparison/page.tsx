"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import CaseTabs from "../../../components/CaseTabs";
import Header from "../../../components/Header";
import Sidebar from "../../../components/Sidebar";
import StatusBadge from "../../../components/StatusBadge";

type FieldResult = "match" | "mismatch" | "review";

type ReviewDecision = "match" | "mismatch" | null;

type ComparisonField = {
  field: string;
  siValue: string;
  blValue: string;
  result: FieldResult;
};

type ComparisonCase = {
  status: string;
  subject: string;
  comparison: ComparisonField[];
};

const comparisonCases: Record<string, ComparisonCase> = {
  "SHP-001": {
    status: "Analysing",
    subject: "Draft BL verification - MAERSK LIMA",
    comparison: [
      {
        field: "Shipper",
        siValue: "ABC Logistics Sdn Bhd",
        blValue: "ABC Logistics Sdn Bhd",
        result: "match",
      },
      {
        field: "Consignee",
        siValue: "XYZ Trading Pte Ltd",
        blValue: "XYZ Trading Pte Ltd",
        result: "match",
      },
      {
        field: "Notify Party",
        siValue: "XYZ Trading Pte Ltd",
        blValue: "XYZ Trading Pte Ltd",
        result: "match",
      },
      {
        field: "Port of Loading",
        siValue: "Port Klang, Malaysia",
        blValue: "Port Klang, Malaysia",
        result: "match",
      },
      {
        field: "Port of Discharge",
        siValue: "Singapore",
        blValue: "Singapore",
        result: "match",
      },
      {
        field: "Container Count",
        siValue: "3",
        blValue: "3",
        result: "match",
      },
      {
        field: "Gross Weight",
        siValue: "12,500 kg",
        blValue: "Processing...",
        result: "review",
      },
    ],
  },

  "SHP-002": {
    status: "Mismatch",
    subject: "Shipping documents for booking 839201",
    comparison: [
      {
        field: "Shipper",
        siValue: "ABC Logistics Sdn Bhd",
        blValue: "ABC Logistics Sdn Bhd",
        result: "match",
      },
      {
        field: "Consignee",
        siValue: "XYZ Trading Pte Ltd",
        blValue: "XYZ Trading Pte Ltd",
        result: "match",
      },
      {
        field: "Notify Party",
        siValue: "XYZ Trading Pte Ltd",
        blValue: "XYZ Trading Pte Ltd",
        result: "match",
      },
      {
        field: "Port of Loading",
        siValue: "Port Klang, Malaysia",
        blValue: "Port Klang, Malaysia",
        result: "match",
      },
      {
        field: "Port of Discharge",
        siValue: "Singapore",
        blValue: "Singapore",
        result: "match",
      },
      {
        field: "Container Count",
        siValue: "3",
        blValue: "4",
        result: "mismatch",
      },
      {
        field: "Gross Weight",
        siValue: "12,500 kg",
        blValue: "12,500 kg",
        result: "match",
      },
    ],
  },

  "SHP-003": {
    status: "No mismatch",
    subject: "BL draft for verification",
    comparison: [
      {
        field: "Shipper",
        siValue: "ABC Logistics Sdn Bhd",
        blValue: "ABC Logistics Sdn Bhd",
        result: "match",
      },
      {
        field: "Consignee",
        siValue: "XYZ Trading Pte Ltd",
        blValue: "XYZ Trading Pte Ltd",
        result: "match",
      },
      {
        field: "Notify Party",
        siValue: "XYZ Trading Pte Ltd",
        blValue: "XYZ Trading Pte Ltd",
        result: "match",
      },
      {
        field: "Port of Loading",
        siValue: "Port Klang, Malaysia",
        blValue: "Port Klang, Malaysia",
        result: "match",
      },
      {
        field: "Port of Discharge",
        siValue: "Singapore",
        blValue: "Singapore",
        result: "match",
      },
      {
        field: "Container Count",
        siValue: "3",
        blValue: "3",
        result: "match",
      },
      {
        field: "Gross Weight",
        siValue: "12,500 kg",
        blValue: "12,500 kg",
        result: "match",
      },
    ],
  },

  "SHP-004": {
    status: "Needs review",
    subject: "Document verification required",
    comparison: [
      {
        field: "Shipper",
        siValue: "ABC Logistics Sdn Bhd",
        blValue: "ABC Logistics Sdn Bhd",
        result: "match",
      },
      {
        field: "Consignee",
        siValue: "XYZ Trading Pte Ltd",
        blValue: "XYZ Trading Pte Ltd",
        result: "match",
      },
      {
        field: "Notify Party",
        siValue: "XYZ Trading Pte Ltd",
        blValue: "XYZ Trading Pte Ltd",
        result: "match",
      },
      {
        field: "Port of Loading",
        siValue: "Port Klang, Malaysia",
        blValue: "Port Klang, Malaysia",
        result: "match",
      },
      {
        field: "Port of Discharge",
        siValue: "Singapore",
        blValue: "Singapore",
        result: "match",
      },
      {
        field: "Container Count",
        siValue: "3",
        blValue: "3",
        result: "match",
      },
      {
        field: "Gross Weight",
        siValue: "12,500 kg",
        blValue: "Unable to verify",
        result: "review",
      },
    ],
  },
};

export default function ComparisonPage() {
  const params = useParams();
  const caseId = params.id as string;

  const caseData = comparisonCases[caseId];

  const [reviewNote, setReviewNote] = useState("");
  const [reviewDecision, setReviewDecision] =
    useState<ReviewDecision>(null);

  if (!caseData) {
    return (
      <main className="flex min-h-screen bg-white text-gray-900">
        <Sidebar />

        <section className="min-w-0 flex-1">
          <Header />

          <div className="p-8">
            <h1 className="text-2xl font-semibold">
              Case not found
            </h1>

            <p className="mt-2 text-sm text-gray-500">
              The requested verification case does not exist.
            </p>

            <Link
              href="/"
              className="mt-4 inline-block text-sm font-medium text-blue-600 hover:underline"
            >
              ← Back to verification queue
            </Link>
          </div>
        </section>
      </main>
    );
  }

  const mismatchCount = caseData.comparison.filter(
    (item) => item.result === "mismatch"
  ).length;

  const reviewCount = caseData.comparison.filter(
    (item) => item.result === "review"
  ).length;

  const matchCount = caseData.comparison.filter(
    (item) => item.result === "match"
  ).length;

  const isAnalysing =
    caseData.status === "Analysing";

  const needsReview =
    caseData.status === "Needs review";

  const handleReviewDecision = (
    decision: "match" | "mismatch"
  ) => {
    setReviewDecision(decision);
  };

  return (
    <main className="flex min-h-screen bg-white text-gray-900">
      <Sidebar />

      <section className="min-w-0 flex-1">
        <Header />

        <div className="p-8">
          {/* Breadcrumb */}
          <div className="mb-5 text-sm text-gray-500">
            <Link
              href="/"
              className="hover:text-blue-600 hover:underline"
            >
              Verification queue
            </Link>

            <span> / </span>

            <Link
              href={`/cases/${caseId}`}
              className="hover:text-blue-600 hover:underline"
            >
              {caseId}
            </Link>

            <span> / Comparison</span>
          </div>

          {/* Case heading */}
          <div className="flex items-start gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">
              {caseId}
            </h1>

            <div className="pt-1">
              <StatusBadge
                status={
                  reviewDecision === "match"
                    ? "No mismatch"
                    : reviewDecision === "mismatch"
                      ? "Mismatch"
                      : caseData.status
                }
              />
            </div>
          </div>

          <p className="mt-2 text-base text-gray-600">
            {caseData.subject}
          </p>

          {/* Navigation */}
          <CaseTabs
            caseId={caseId}
            activeTab="comparison"
          />

          {/* Comparison heading */}
          <div className="mt-6 flex items-start justify-between gap-5">
            <div>
              <h2 className="text-lg font-semibold">
                Document comparison
              </h2>

              <p className="mt-1 text-sm text-gray-500">
                Shipping Instruction compared with the
                draft Bill of Lading across 7 required
                fields.
              </p>
            </div>

            {caseData.status === "No mismatch" && (
              <span className="shrink-0 rounded-md bg-green-100 px-3 py-1.5 text-sm font-medium text-green-700">
                No mismatch detected
              </span>
            )}

            {caseData.status === "Mismatch" && (
              <span className="shrink-0 rounded-md bg-red-100 px-3 py-1.5 text-sm font-medium text-red-700">
                {mismatchCount} mismatch detected
              </span>
            )}

            {isAnalysing && (
              <span className="shrink-0 rounded-md bg-blue-100 px-3 py-1.5 text-sm font-medium text-blue-700">
                Analysis in progress
              </span>
            )}

            {needsReview &&
              !reviewDecision && (
                <span className="shrink-0 rounded-md bg-yellow-100 px-3 py-1.5 text-sm font-medium text-yellow-700">
                  Human review required
                </span>
              )}

            {reviewDecision === "match" && (
              <span className="shrink-0 rounded-md bg-green-100 px-3 py-1.5 text-sm font-medium text-green-700">
                Reviewed manually
              </span>
            )}

            {reviewDecision === "mismatch" && (
              <span className="shrink-0 rounded-md bg-red-100 px-3 py-1.5 text-sm font-medium text-red-700">
                Reviewed manually
              </span>
            )}
          </div>

          {/* Analysing notice */}
          {isAnalysing && (
            <div className="mt-5 rounded-lg border border-blue-200 bg-blue-50 p-4">
              <p className="text-sm font-semibold text-blue-900">
                Comparison is still in progress
              </p>

              <p className="mt-1 text-sm leading-6 text-blue-800">
                Some fields have already been extracted
                and compared. The final verification
                result will only be shown after all
                required fields have been processed.
              </p>
            </div>
          )}

          {/* Needs review notice */}
          {needsReview &&
            !reviewDecision && (
              <div className="mt-5 rounded-lg border border-yellow-200 bg-yellow-50 p-4">
                <p className="text-sm font-semibold text-yellow-900">
                  Human review required
                </p>

                <p className="mt-1 text-sm leading-6 text-yellow-800">
                  The system could not confidently verify
                  one or more fields. No value has been
                  guessed. A reviewer should check the
                  original documents before making the
                  final decision.
                </p>
              </div>
            )}

          {/* Comparison table */}
          <div className="mt-6 overflow-hidden rounded-lg border border-gray-200">
            <div className="grid grid-cols-[220px_1fr_1fr_130px] border-b border-gray-200 bg-gray-50">
              <div className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
                Field
              </div>

              <div className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
                Shipping Instruction
              </div>

              <div className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
                Bill of Lading
              </div>

              <div className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
                Result
              </div>
            </div>

            {caseData.comparison.map((item) => {
              let displayedResult =
                item.result;

              /*
               * Only replace a field requiring review
               * after the human reviewer decides.
               */
              if (
                item.result === "review" &&
                needsReview &&
                reviewDecision
              ) {
                displayedResult =
                  reviewDecision;
              }

              const isMatch =
                displayedResult === "match";

              const isMismatch =
                displayedResult === "mismatch";

              const isReview =
                displayedResult === "review";

              return (
                <div
                  key={item.field}
                  className={`grid grid-cols-[220px_1fr_1fr_130px] border-b border-gray-100 last:border-b-0 ${
                    isMismatch
                      ? "bg-red-50"
                      : isReview
                        ? "bg-yellow-50"
                        : "bg-white"
                  }`}
                >
                  <div className="px-5 py-5 text-sm font-medium">
                    {item.field}
                  </div>

                  <div className="px-5 py-5 text-sm text-gray-700">
                    {item.siValue}
                  </div>

                  <div
                    className={`px-5 py-5 text-sm ${
                      isMismatch
                        ? "font-medium text-red-700"
                        : isReview
                          ? "font-medium text-yellow-800"
                          : "text-gray-700"
                    }`}
                  >
                    {item.blValue}
                  </div>

                  <div className="px-5 py-5">
                    {isMatch && (
                      <span className="rounded bg-green-100 px-2 py-1 text-xs font-medium text-green-700">
                        Match
                      </span>
                    )}

                    {isMismatch && (
                      <span className="rounded bg-red-100 px-2 py-1 text-xs font-medium text-red-700">
                        Mismatch
                      </span>
                    )}

                    {isReview && (
                      <span className="rounded bg-yellow-100 px-2 py-1 text-xs font-medium text-yellow-700">
                        Review
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Normal completed results */}
          {caseData.status ===
            "No mismatch" && (
            <div className="mt-5 rounded-lg border border-green-200 bg-green-50 p-5">
              <h3 className="text-sm font-semibold text-green-900">
                No mismatch detected
              </h3>

              <p className="mt-1 text-sm leading-6 text-green-800">
                All {matchCount} of 7 required fields
                match between the Shipping Instruction
                and draft Bill of Lading.
              </p>
            </div>
          )}

          {caseData.status === "Mismatch" && (
            <div className="mt-5 rounded-lg border border-red-200 bg-red-50 p-5">
              <h3 className="text-sm font-semibold text-red-900">
                Verification requires attention
              </h3>

              <p className="mt-1 text-sm leading-6 text-red-800">
                {mismatchCount} of 7 required fields do
                not match between the Shipping
                Instruction and draft Bill of Lading.
              </p>
            </div>
          )}

          {isAnalysing && (
            <div className="mt-5 rounded-lg border border-blue-200 bg-blue-50 p-5">
              <h3 className="text-sm font-semibold text-blue-900">
                Verification not completed yet
              </h3>

              <p className="mt-1 text-sm leading-6 text-blue-800">
                {matchCount} fields have been verified
                so far. {reviewCount} field is still
                being processed.
              </p>
            </div>
          )}

          {/* Human review */}
          {needsReview &&
            !reviewDecision && (
              <section className="mt-5 overflow-hidden rounded-lg border border-yellow-300 bg-white">
                <div className="border-b border-yellow-200 bg-yellow-50 px-5 py-4">
                  <h3 className="text-sm font-semibold text-yellow-900">
                    Manual verification required
                  </h3>

                  <p className="mt-1 text-sm text-yellow-800">
                    {matchCount} fields were verified
                    successfully, while {reviewCount}{" "}
                    field could not be verified
                    confidently.
                  </p>
                </div>

                <div className="p-5">
                  <div className="rounded-md border border-gray-200 bg-gray-50 p-4">
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                      Field requiring review
                    </p>

                    <p className="mt-2 text-sm font-semibold text-gray-900">
                      Gross Weight
                    </p>

                    <div className="mt-4 grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-xs text-gray-500">
                          Shipping Instruction
                        </p>

                        <p className="mt-1 text-sm font-medium">
                          12,500 kg
                        </p>
                      </div>

                      <div>
                        <p className="text-xs text-gray-500">
                          Bill of Lading
                        </p>

                        <p className="mt-1 text-sm font-medium text-yellow-700">
                          Unable to verify
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="mt-5">
                    <label
                      htmlFor="review-note"
                      className="text-sm font-medium text-gray-900"
                    >
                      Reviewer note
                    </label>

                    <p className="mt-1 text-xs text-gray-500">
                      Add an optional note explaining
                      your decision.
                    </p>

                    <textarea
                      id="review-note"
                      value={reviewNote}
                      onChange={(event) =>
                        setReviewNote(
                          event.target.value
                        )
                      }
                      rows={3}
                      placeholder="Enter reviewer note..."
                      className="mt-3 w-full resize-none rounded-md border border-gray-300 px-3 py-2 text-sm outline-none transition placeholder:text-gray-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                    />
                  </div>

                  <div className="mt-5 flex flex-wrap items-center justify-between gap-4">
                    <Link
                      href={`/cases/${caseId}/attachments`}
                      className="text-sm font-medium text-blue-600 hover:underline"
                    >
                      Review original documents →
                    </Link>

                    <div className="flex gap-3">
                      <button
                        type="button"
                        onClick={() =>
                          handleReviewDecision(
                            "match"
                          )
                        }
                        className="rounded-md border border-green-300 bg-white px-4 py-2 text-sm font-medium text-green-700 hover:bg-green-50"
                      >
                        Confirm match
                      </button>

                      <button
                        type="button"
                        onClick={() =>
                          handleReviewDecision(
                            "mismatch"
                          )
                        }
                        className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
                      >
                        Confirm mismatch
                      </button>
                    </div>
                  </div>
                </div>
              </section>
            )}

          {/* Human decision result */}
          {needsReview &&
            reviewDecision && (
              <section
                className={`mt-5 rounded-lg border p-5 ${
                  reviewDecision === "match"
                    ? "border-green-200 bg-green-50"
                    : "border-red-200 bg-red-50"
                }`}
              >
                <div className="flex items-start justify-between gap-5">
                  <div>
                    <h3
                      className={`text-sm font-semibold ${
                        reviewDecision ===
                        "match"
                          ? "text-green-900"
                          : "text-red-900"
                      }`}
                    >
                      Human review completed
                    </h3>

                    <p
                      className={`mt-1 text-sm leading-6 ${
                        reviewDecision ===
                        "match"
                          ? "text-green-800"
                          : "text-red-800"
                      }`}
                    >
                      The reviewer confirmed the
                      unresolved field as{" "}
                      <strong>
                        {reviewDecision ===
                        "match"
                          ? "Match"
                          : "Mismatch"}
                      </strong>
                      .
                    </p>

                    {reviewNote.trim() && (
                      <div className="mt-4">
                        <p className="text-xs font-semibold uppercase tracking-wide opacity-70">
                          Reviewer note
                        </p>

                        <p className="mt-1 text-sm">
                          {reviewNote}
                        </p>
                      </div>
                    )}
                  </div>

                  <span
                    className={`shrink-0 rounded px-2.5 py-1 text-xs font-medium ${
                      reviewDecision === "match"
                        ? "bg-green-100 text-green-700"
                        : "bg-red-100 text-red-700"
                    }`}
                  >
                    Reviewed manually
                  </span>
                </div>

                <button
                  type="button"
                  onClick={() =>
                    setReviewDecision(null)
                  }
                  className="mt-4 text-sm font-medium underline"
                >
                  Change decision
                </button>
              </section>
            )}
        </div>
      </section>
    </main>
  );
}
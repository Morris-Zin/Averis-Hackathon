"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import CaseTabs from "../../../components/CaseTabs";
import Header from "../../../components/Header";
import Sidebar from "../../../components/Sidebar";
import StatusBadge from "../../../components/StatusBadge";

type StepStatus =
  | "completed"
  | "processing"
  | "review";

type AnalysisData = {
  id: string;
  subject: string;
  status: string;
  classification: string;
  decision: string;
  summary: string;
  steps: {
    label: string;
    status: StepStatus;
  }[];
};

const analysisCases: Record<string, AnalysisData> = {
  "SHP-001": {
    id: "SHP-001",
    subject: "Draft BL verification - MAERSK LIMA",
    status: "Analysing",
    classification: "Document comparison",
    decision: "Processing",
    summary:
      "The AI is currently extracting and comparing information from the Shipping Instruction and draft Bill of Lading.",
    steps: [
      {
        label: "Email classified as document comparison",
        status: "completed",
      },
      {
        label: "Shipping Instruction identified",
        status: "completed",
      },
      {
        label: "Bill of Lading identified",
        status: "completed",
      },
      {
        label: "Document fields extracted",
        status: "completed",
      },
      {
        label:
          "Comparing Shipping Instruction and Bill of Lading",
        status: "processing",
      },
    ],
  },

  "SHP-002": {
    id: "SHP-002",
    subject: "Shipping documents for booking 839201",
    status: "Mismatch",
    classification: "Document comparison",
    decision: "Automatic verification completed",
    summary:
      "The AI completed the document comparison and detected 1 discrepancy between the Shipping Instruction and draft Bill of Lading.",
    steps: [
      {
        label: "Email classified as document comparison",
        status: "completed",
      },
      {
        label: "Shipping Instruction identified",
        status: "completed",
      },
      {
        label: "Bill of Lading identified",
        status: "completed",
      },
      {
        label: "Document fields extracted",
        status: "completed",
      },
      {
        label:
          "Shipping Instruction and Bill of Lading compared",
        status: "completed",
      },
    ],
  },

  "SHP-003": {
    id: "SHP-003",
    subject: "BL draft for verification",
    status: "No mismatch",
    classification: "Document comparison",
    decision: "Automatic verification completed",
    summary:
      "The AI completed the document comparison. All required fields match between the Shipping Instruction and draft Bill of Lading.",
    steps: [
      {
        label: "Email classified as document comparison",
        status: "completed",
      },
      {
        label: "Shipping Instruction identified",
        status: "completed",
      },
      {
        label: "Bill of Lading identified",
        status: "completed",
      },
      {
        label: "Document fields extracted",
        status: "completed",
      },
      {
        label:
          "Shipping Instruction and Bill of Lading compared",
        status: "completed",
      },
    ],
  },

  "SHP-004": {
    id: "SHP-004",
    subject: "Document verification required",
    status: "Needs review",
    classification: "Document comparison",
    decision: "Human review required",
    summary:
      "The AI could not confidently complete the verification. The case has been routed for human review instead of making an uncertain decision.",
    steps: [
      {
        label: "Email classified as document comparison",
        status: "completed",
      },
      {
        label: "Shipping Instruction identified",
        status: "completed",
      },
      {
        label: "Bill of Lading identified",
        status: "completed",
      },
      {
        label: "Document fields extracted",
        status: "completed",
      },
      {
        label: "Verification requires human review",
        status: "review",
      },
    ],
  },
};

export default function AnalysisPage() {
  const params = useParams();
  const caseId = params.id as string;

  const caseData = analysisCases[caseId];

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

            <span> / AI Analysis</span>
          </div>

          {/* Heading */}
          <div className="flex items-start gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">
              {caseData.id}
            </h1>

            <div className="pt-1">
              <StatusBadge status={caseData.status} />
            </div>
          </div>

          <p className="mt-2 text-base text-gray-600">
            {caseData.subject}
          </p>

          {/* Shared tabs */}
          <CaseTabs
            caseId={caseId}
            activeTab="analysis"
          />

          <div className="mt-6">
            <h2 className="text-lg font-semibold">
              AI Analysis
            </h2>

            <p className="mt-1 text-sm text-gray-500">
              Automated document classification, extraction and verification.
            </p>
          </div>

          <div className="mt-6 grid grid-cols-[1fr_340px] gap-5">
            {/* Processing */}
            <section className="rounded-lg border border-gray-200 bg-white">
              <div className="border-b border-gray-200 px-6 py-4">
                <h3 className="text-sm font-semibold">
                  Processing
                </h3>

                <p className="mt-1 text-xs text-gray-500">
                  Steps performed by the verification system.
                </p>
              </div>

              <div className="p-6">
                <div className="space-y-5">
                  {caseData.steps.map(
                    (step, index) => (
                      <div
                        key={step.label}
                        className="flex items-start gap-4"
                      >
                        {step.status ===
                          "completed" && (
                          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-green-100 text-sm font-semibold text-green-700">
                            ✓
                          </div>
                        )}

                        {step.status ===
                          "processing" && (
                          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs font-semibold text-blue-700">
                            ...
                          </div>
                        )}

                        {step.status ===
                          "review" && (
                          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-yellow-100 text-sm font-semibold text-yellow-700">
                            !
                          </div>
                        )}

                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium">
                            {step.label}
                          </p>

                          <p className="mt-1 text-xs text-gray-500">
                            Step {index + 1}
                          </p>
                        </div>

                        {step.status ===
                          "completed" && (
                          <span className="rounded bg-green-50 px-2 py-1 text-xs font-medium text-green-700">
                            Completed
                          </span>
                        )}

                        {step.status ===
                          "processing" && (
                          <span className="rounded bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700">
                            Processing
                          </span>
                        )}

                        {step.status ===
                          "review" && (
                          <span className="rounded bg-yellow-50 px-2 py-1 text-xs font-medium text-yellow-700">
                            Review
                          </span>
                        )}
                      </div>
                    )
                  )}
                </div>
              </div>
            </section>

            {/* Right column */}
            <div className="space-y-5">
              <section className="rounded-lg border border-gray-200 bg-white p-5">
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Classification
                </p>

                <p className="mt-2 text-sm font-semibold">
                  {caseData.classification}
                </p>
              </section>

              <section className="rounded-lg border border-gray-200 bg-white p-5">
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Result
                </p>

                <div className="mt-3">
                  <StatusBadge
                    status={caseData.status}
                  />
                </div>

                <p className="mt-4 text-sm leading-6 text-gray-600">
                  {caseData.summary}
                </p>
              </section>

              <section className="rounded-lg border border-gray-200 bg-white p-5">
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Verification decision
                </p>

                <p className="mt-2 text-sm font-medium">
                  {caseData.decision}
                </p>

                {caseData.status ===
                "Needs review" ? (
                  <p className="mt-2 text-xs leading-5 text-gray-500">
                    The system will not guess when
                    verification cannot be completed
                    confidently.
                  </p>
                ) : (
                  <p className="mt-2 text-xs leading-5 text-gray-500">
                    The verification process did not
                    require manual intervention.
                  </p>
                )}
              </section>
            </div>
          </div>

          {caseData.status !== "Analysing" && (
            <div className="mt-5 flex justify-end">
              <Link
                href={`/cases/${caseId}/comparison`}
                className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
              >
                View field comparison →
              </Link>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
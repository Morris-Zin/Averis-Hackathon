"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import CaseTabs from "../../components/CaseTabs";
import Header from "../../components/Header";
import Sidebar from "../../components/Sidebar";
import StatusBadge from "../../components/StatusBadge";

type CaseData = {
  id: string;
  subject: string;
  sender: string;
  status: string;
  classification: string;
  siFile: string;
  blFile: string;
  aiResult: string;
};

const cases: Record<string, CaseData> = {
  "SHP-001": {
    id: "SHP-001",
    subject: "Draft BL verification - MAERSK LIMA",
    sender: "operations@shipping.com",
    status: "Analysing",
    classification: "Document comparison",
    siFile: "SI-MAERSK-LIMA.pdf",
    blFile: "Draft-BL-MAERSK-LIMA.pdf",
    aiResult:
      "AI analysis is currently in progress. The documents are being compared.",
  },

  "SHP-002": {
    id: "SHP-002",
    subject: "Shipping documents for booking 839201",
    sender: "export@logistics.com",
    status: "Mismatch",
    classification: "Document comparison",
    siFile: "SI-839201.pdf",
    blFile: "Draft-BL-839201.pdf",
    aiResult:
      "1 discrepancy was detected between the Shipping Instruction and draft Bill of Lading.",
  },

  "SHP-003": {
    id: "SHP-003",
    subject: "BL draft for verification",
    sender: "docs@freight.com",
    status: "No mismatch",
    classification: "Document comparison",
    siFile: "SI-FREIGHT-003.pdf",
    blFile: "Draft-BL-FREIGHT-003.pdf",
    aiResult:
      "No mismatch was detected between the Shipping Instruction and draft Bill of Lading.",
  },

  "SHP-004": {
    id: "SHP-004",
    subject: "Document verification required",
    sender: "operations@cargo.com",
    status: "Needs review",
    classification: "Document comparison",
    siFile: "SI-CARGO-004.pdf",
    blFile: "Draft-BL-CARGO-004.pdf",
    aiResult:
      "The AI could not confidently complete the verification. Human review is required.",
  },
};

export default function CasePage() {
  const params = useParams();
  const caseId = params.id as string;

  const caseData = cases[caseId];

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

            <span> / {caseData.id}</span>
          </div>

          {/* Case heading */}
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

          {/* Shared navigation */}
          <CaseTabs
            caseId={caseId}
            activeTab="overview"
          />

          {/* Overview */}
          <div className="mt-6 grid grid-cols-2 gap-5">
            {/* Verification summary */}
            <section className="rounded-lg border border-gray-200 bg-white p-6">
              <h2 className="text-base font-semibold">
                Verification summary
              </h2>

              <div className="mt-6 grid grid-cols-2 gap-x-8 gap-y-6">
                <div>
                  <p className="text-sm text-gray-500">
                    Sender
                  </p>

                  <p className="mt-1 break-words text-sm font-medium">
                    {caseData.sender}
                  </p>
                </div>

                <div>
                  <p className="text-sm text-gray-500">
                    Classification
                  </p>

                  <p className="mt-1 text-sm font-medium">
                    {caseData.classification}
                  </p>
                </div>

                <div>
                  <p className="text-sm text-gray-500">
                    Shipping Instruction
                  </p>

                  <p className="mt-1 break-words text-sm font-medium">
                    {caseData.siFile}
                  </p>
                </div>

                <div>
                  <p className="text-sm text-gray-500">
                    Bill of Lading
                  </p>

                  <p className="mt-1 break-words text-sm font-medium">
                    {caseData.blFile}
                  </p>
                </div>
              </div>

              <Link
                href={`/cases/${caseId}/attachments`}
                className="mt-6 inline-block text-sm font-medium text-blue-600 hover:underline"
              >
                View attachments →
              </Link>
            </section>

            {/* AI result */}
            <section className="rounded-lg border border-gray-200 bg-white p-6">
              <h2 className="text-base font-semibold">
                AI result
              </h2>

              <div className="mt-5">
                <StatusBadge status={caseData.status} />
              </div>

              <p className="mt-5 text-sm leading-6 text-gray-600">
                {caseData.aiResult}
              </p>

              {caseData.status === "Analysing" && (
                <div className="mt-5">
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
                    <div className="h-full w-2/3 rounded-full bg-blue-500" />
                  </div>

                  <p className="mt-2 text-xs text-gray-500">
                    Comparing Shipping Instruction and Bill of Lading...
                  </p>
                </div>
              )}

              <div className="mt-5 flex flex-wrap gap-5">
                <Link
                  href={`/cases/${caseId}/analysis`}
                  className="text-sm font-medium text-blue-600 hover:underline"
                >
                  View AI analysis →
                </Link>

                {(caseData.status === "Mismatch" ||
                  caseData.status === "No mismatch") && (
                  <Link
                    href={`/cases/${caseId}/comparison`}
                    className="text-sm font-medium text-blue-600 hover:underline"
                  >
                    View comparison →
                  </Link>
                )}
              </div>

              {caseData.status === "Needs review" && (
                <div className="mt-5 rounded-md border border-yellow-200 bg-yellow-50 p-3">
                  <p className="text-xs leading-5 text-yellow-800">
                    Automatic verification could not be completed
                    confidently. This case requires human review.
                  </p>
                </div>
              )}
            </section>
          </div>
        </div>
      </section>
    </main>
  );
}
"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import CaseTabs from "../../../components/CaseTabs";
import Header from "../../../components/Header";
import Sidebar from "../../../components/Sidebar";
import StatusBadge from "../../../components/StatusBadge";

type EmailData = {
  id: string;
  subject: string;
  sender: string;
  senderName: string;
  recipient: string;
  received: string;
  status: string;
  body: string[];
  attachments: {
    name: string;
    type: string;
  }[];
};

const emailCases: Record<string, EmailData> = {
  "SHP-001": {
    id: "SHP-001",
    subject: "Draft BL verification - MAERSK LIMA",
    sender: "operations@shipping.com",
    senderName: "Shipping Operations",
    recipient: "verification@averis.com",
    received: "2 minutes ago",
    status: "Analysing",
    body: [
      "Hi Team,",
      "Please find attached the Shipping Instruction and draft Bill of Lading for MAERSK LIMA.",
      "Kindly verify the draft Bill of Lading against the Shipping Instruction and advise if there are any discrepancies.",
      "Thank you.",
      "Regards,\nShipping Operations",
    ],
    attachments: [
      {
        name: "SI-MAERSK-LIMA.pdf",
        type: "Shipping Instruction",
      },
      {
        name: "Draft-BL-MAERSK-LIMA.pdf",
        type: "Bill of Lading",
      },
    ],
  },

  "SHP-002": {
    id: "SHP-002",
    subject: "Shipping documents for booking 839201",
    sender: "export@logistics.com",
    senderName: "Export Operations",
    recipient: "verification@averis.com",
    received: "12 minutes ago",
    status: "Mismatch",
    body: [
      "Hi Team,",
      "Please find attached the Shipping Instruction and draft Bill of Lading for booking 839201.",
      "Kindly verify the draft BL against the SI and advise if there are any discrepancies.",
      "Please let us know if any amendments are required.",
      "Regards,\nExport Operations",
    ],
    attachments: [
      {
        name: "SI-839201.pdf",
        type: "Shipping Instruction",
      },
      {
        name: "Draft-BL-839201.pdf",
        type: "Bill of Lading",
      },
    ],
  },

  "SHP-003": {
    id: "SHP-003",
    subject: "BL draft for verification",
    sender: "docs@freight.com",
    senderName: "Freight Documentation",
    recipient: "verification@averis.com",
    received: "24 minutes ago",
    status: "No mismatch",
    body: [
      "Hi Team,",
      "Attached are the Shipping Instruction and draft Bill of Lading for verification.",
      "Please check the draft BL against the provided Shipping Instruction.",
      "Thank you for your assistance.",
      "Regards,\nFreight Documentation",
    ],
    attachments: [
      {
        name: "SI-FREIGHT-003.pdf",
        type: "Shipping Instruction",
      },
      {
        name: "Draft-BL-FREIGHT-003.pdf",
        type: "Bill of Lading",
      },
    ],
  },

  "SHP-004": {
    id: "SHP-004",
    subject: "Document verification required",
    sender: "operations@cargo.com",
    senderName: "Cargo Operations",
    recipient: "verification@averis.com",
    received: "1 hour ago",
    status: "Needs review",
    body: [
      "Hi Team,",
      "Please review the attached shipping documents and verify the draft Bill of Lading against the Shipping Instruction.",
      "Some information in the documents may require additional checking.",
      "Please advise if further clarification is required.",
      "Regards,\nCargo Operations",
    ],
    attachments: [
      {
        name: "SI-CARGO-004.pdf",
        type: "Shipping Instruction",
      },
      {
        name: "Draft-BL-CARGO-004.pdf",
        type: "Bill of Lading",
      },
    ],
  },
};

export default function EmailPage() {
  const params = useParams();
  const caseId = params.id as string;

  const emailData = emailCases[caseId];

  if (!emailData) {
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

            <span> / </span>

            <Link
              href={`/cases/${caseId}`}
              className="hover:text-blue-600 hover:underline"
            >
              {caseId}
            </Link>

            <span> / Email</span>
          </div>

          {/* Case heading */}
          <div className="flex items-start gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">
              {emailData.id}
            </h1>

            <div className="pt-1">
              <StatusBadge status={emailData.status} />
            </div>
          </div>

          <p className="mt-2 text-base text-gray-600">
            {emailData.subject}
          </p>

          {/* Shared navigation */}
          <CaseTabs
            caseId={caseId}
            activeTab="email"
          />

          {/* Page heading */}
          <div className="mt-6">
            <h2 className="text-lg font-semibold">
              Original email
            </h2>

            <p className="mt-1 text-sm text-gray-500">
              Incoming email associated with this verification case.
            </p>
          </div>

          {/* Email card */}
          <section className="mt-6 overflow-hidden rounded-lg border border-gray-200 bg-white">
            {/* Email header */}
            <div className="border-b border-gray-200 px-6 py-5">
              <div className="flex items-start justify-between gap-6">
                <div className="min-w-0">
                  <h3 className="text-lg font-semibold text-gray-900">
                    {emailData.subject}
                  </h3>

                  <div className="mt-4 flex items-center gap-3">
                    {/* Sender avatar */}
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gray-100 text-sm font-semibold text-gray-600">
                      {emailData.senderName
                        .split(" ")
                        .map((word) => word[0])
                        .join("")
                        .slice(0, 2)}
                    </div>

                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm font-medium text-gray-900">
                          {emailData.senderName}
                        </p>

                        <p className="text-sm text-gray-500">
                          &lt;{emailData.sender}&gt;
                        </p>
                      </div>

                      <p className="mt-1 text-xs text-gray-500">
                        To: {emailData.recipient}
                      </p>
                    </div>
                  </div>
                </div>

                <p className="shrink-0 text-sm text-gray-500">
                  {emailData.received}
                </p>
              </div>
            </div>

            {/* Email body */}
            <div className="px-6 py-7">
              <div className="max-w-3xl">
                {emailData.body.map((paragraph, index) => (
                  <p
                    key={index}
                    className={`whitespace-pre-line text-sm leading-7 text-gray-700 ${
                      index === 0 ? "" : "mt-4"
                    }`}
                  >
                    {paragraph}
                  </p>
                ))}
              </div>
            </div>

            {/* Email attachments */}
            <div className="border-t border-gray-200 bg-gray-50 px-6 py-5">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-sm font-semibold text-gray-900">
                    Attachments
                  </h4>

                  <p className="mt-1 text-xs text-gray-500">
                    {emailData.attachments.length} documents attached
                  </p>
                </div>

                <Link
                  href={`/cases/${caseId}/attachments`}
                  className="text-sm font-medium text-blue-600 hover:underline"
                >
                  View all attachments →
                </Link>
              </div>

              <div className="mt-4 grid max-w-3xl grid-cols-2 gap-3">
                {emailData.attachments.map((attachment) => (
                  <Link
                    key={attachment.name}
                    href={`/cases/${caseId}/attachments`}
                    className="flex items-center gap-3 rounded-md border border-gray-200 bg-white p-4 hover:border-blue-300 hover:bg-blue-50"
                  >
                    {/* PDF icon */}
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded bg-red-100 text-xs font-semibold text-red-700">
                      PDF
                    </div>

                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-gray-900">
                        {attachment.name}
                      </p>

                      <p className="mt-1 text-xs text-gray-500">
                        {attachment.type}
                      </p>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          </section>

          {/* Classification notice */}
          <section className="mt-5 rounded-lg border border-blue-200 bg-blue-50 p-5">
            <div className="flex items-start gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-100 text-sm font-semibold text-blue-700">
                AI
              </div>

              <div>
                <h3 className="text-sm font-semibold text-blue-900">
                  Email classified as document comparison
                </h3>

                <p className="mt-1 text-sm leading-6 text-blue-800">
                  The system identified this email as a request to compare
                  shipping documents and routed it to the document
                  verification workflow.
                </p>

                <Link
                  href={`/cases/${caseId}/analysis`}
                  className="mt-3 inline-block text-sm font-medium text-blue-700 hover:underline"
                >
                  View AI analysis →
                </Link>
              </div>
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}
"use client";

import {
  ChangeEvent,
  useRef,
  useState,
} from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import CaseTabs from "../../../components/CaseTabs";
import Header from "../../../components/Header";
import Sidebar from "../../../components/Sidebar";

type Attachment = {
  id: number;
  name: string;
  type: "PDF document" | "Word document";
  url: string;
};

export default function AttachmentsPage() {
  const params = useParams();
  const caseId = params.id as string;

  const fileInputRef = useRef<HTMLInputElement>(null);

  const [attachments, setAttachments] = useState<
    Attachment[]
  >([]);

  const [selectedAttachment, setSelectedAttachment] =
    useState<Attachment | null>(null);

  const openFilePicker = () => {
    fileInputRef.current?.click();
  };

  const handleFileUpload = (
    event: ChangeEvent<HTMLInputElement>
  ) => {
    const file = event.target.files?.[0];

    if (!file) {
      return;
    }

    const fileName = file.name.toLowerCase();

    const isPdf =
      file.type === "application/pdf" ||
      fileName.endsWith(".pdf");

    const isWord =
      file.type === "application/msword" ||
      file.type ===
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
      fileName.endsWith(".doc") ||
      fileName.endsWith(".docx");

    if (!isPdf && !isWord) {
      alert("Please upload a PDF or Word document.");

      event.target.value = "";
      return;
    }

    const fileUrl = URL.createObjectURL(file);

    const newAttachment: Attachment = {
      id: Date.now(),
      name: file.name,
      type: isPdf
        ? "PDF document"
        : "Word document",
      url: fileUrl,
    };

    setAttachments((previousAttachments) => [
      ...previousAttachments,
      newAttachment,
    ]);

    setSelectedAttachment(newAttachment);

    event.target.value = "";
  };

  const isPdf =
    selectedAttachment?.type === "PDF document";

  const isWord =
    selectedAttachment?.type === "Word document";

  return (
    <main className="flex min-h-screen bg-white text-gray-900">
      <Sidebar />

      <section className="min-w-0 flex-1">
        <Header />

        <div className="p-8">
          {/* Hidden file input shared by BOTH upload buttons */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            onChange={handleFileUpload}
            className="hidden"
          />

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

            <span> / Attachments</span>
          </div>

          {/* Case heading */}
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              {caseId}
            </h1>

            <p className="mt-1 text-sm text-gray-600">
              Shipping document verification
            </p>
          </div>

          {/* Navigation */}
          <CaseTabs
            caseId={caseId}
            activeTab="attachments"
          />

          {/* Attachments heading */}
          <div className="mb-5 mt-6 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">
                Attachments
              </h2>

              <p className="mt-1 text-sm text-gray-500">
                Upload and preview shipping documents.
              </p>
            </div>

            {/* TOP-RIGHT UPLOAD BUTTON */}
            <button
              type="button"
              onClick={openFilePicker}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              Upload document
            </button>
          </div>

          {/* Document workspace */}
          <div className="grid min-h-[600px] grid-cols-[280px_minmax(0,1fr)] overflow-hidden rounded-lg border border-gray-200">
            {/* LEFT SIDE - Document list */}
            <aside className="border-r border-gray-200 bg-gray-50">
              <div className="border-b border-gray-200 px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Documents
                </p>
              </div>

              {attachments.length === 0 ? (
                <div className="p-5">
                  <p className="text-sm font-medium text-gray-700">
                    No documents yet
                  </p>

                  <p className="mt-1 text-xs leading-5 text-gray-500">
                    Upload a PDF or Word document to start
                    previewing it.
                  </p>
                </div>
              ) : (
                <div className="p-2">
                  {attachments.map((attachment) => {
                    const isSelected =
                      selectedAttachment?.id ===
                      attachment.id;

                    return (
                      <button
                        key={attachment.id}
                        type="button"
                        onClick={() =>
                          setSelectedAttachment(
                            attachment
                          )
                        }
                        className={`mb-1 w-full rounded-md p-3 text-left ${
                          isSelected
                            ? "bg-blue-50"
                            : "hover:bg-gray-100"
                        }`}
                      >
                        <div className="flex items-start gap-3">
                          <div
                            className={`flex h-9 w-9 shrink-0 items-center justify-center rounded text-xs font-semibold ${
                              attachment.type ===
                              "PDF document"
                                ? "bg-red-100 text-red-700"
                                : "bg-blue-100 text-blue-700"
                            }`}
                          >
                            {attachment.type ===
                            "PDF document"
                              ? "PDF"
                              : "DOC"}
                          </div>

                          <div className="min-w-0">
                            <p className="truncate text-sm font-medium">
                              {attachment.name}
                            </p>

                            <p className="mt-1 text-xs text-gray-500">
                              {attachment.type}
                            </p>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </aside>

            {/* RIGHT SIDE - Preview */}
            <section className="flex min-w-0 flex-col bg-white">
              {selectedAttachment ? (
                <>
                  {/* Preview header */}
                  <div className="flex h-14 items-center justify-between border-b border-gray-200 px-5">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">
                        {selectedAttachment.name}
                      </p>

                      <p className="text-xs text-gray-500">
                        {selectedAttachment.type}
                      </p>
                    </div>

                    <a
                      href={selectedAttachment.url}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
                    >
                      Open document
                    </a>
                  </div>

                  {/* PDF preview */}
                  {isPdf && (
                    <div className="flex-1 bg-gray-100 p-4">
                      <iframe
                        src={selectedAttachment.url}
                        title={selectedAttachment.name}
                        className="h-full min-h-[520px] w-full rounded-md border border-gray-300 bg-white"
                      />
                    </div>
                  )}

                  {/* Word preview fallback */}
                  {isWord && (
                    <div className="flex flex-1 items-center justify-center bg-gray-50 p-8">
                      <div className="max-w-md text-center">
                        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-lg bg-blue-100 text-sm font-bold text-blue-700">
                          DOC
                        </div>

                        <h3 className="text-base font-semibold">
                          Word document selected
                        </h3>

                        <p className="mt-2 text-sm leading-6 text-gray-500">
                          The document was uploaded
                          successfully. Browsers cannot
                          reliably display a local Word
                          document directly inside an
                          iframe.
                        </p>

                        <p className="mt-2 text-sm leading-6 text-gray-500">
                          The backend can later convert
                          Word documents to PDF before
                          displaying them.
                        </p>

                        <a
                          href={selectedAttachment.url}
                          download={
                            selectedAttachment.name
                          }
                          className="mt-5 inline-block rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium hover:bg-gray-50"
                        >
                          Open / download document
                        </a>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                /* EMPTY STATE */
                <div className="flex flex-1 items-center justify-center bg-gray-50">
                  <div className="max-w-sm px-6 text-center">
                    {/* CLICKABLE + BUTTON */}
                    <button
                      type="button"
                      onClick={openFilePicker}
                      aria-label="Upload document"
                      className="mx-auto mb-4 flex h-16 w-16 cursor-pointer items-center justify-center rounded-lg border border-gray-300 bg-white text-2xl text-gray-400 transition hover:border-blue-400 hover:bg-blue-50 hover:text-blue-600"
                    >
                      +
                    </button>

                    <h3 className="text-sm font-semibold">
                      No document selected
                    </h3>

                    <p className="mt-2 text-sm leading-6 text-gray-500">
                      Upload a PDF or Word document to
                      preview the shipping document here.
                    </p>

                    {/* Extra clickable text */}
                    <button
                      type="button"
                      onClick={openFilePicker}
                      className="mt-4 text-sm font-medium text-blue-600 hover:underline"
                    >
                      Choose a document
                    </button>
                  </div>
                </div>
              )}
            </section>
          </div>
        </div>
      </section>
    </main>
  );
}
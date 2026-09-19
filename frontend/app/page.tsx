"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import Header from "./components/Header";
import Sidebar from "./components/Sidebar";
import StatusBadge from "./components/StatusBadge";

type CaseStatus =
  | "Analysing"
  | "Mismatch"
  | "No mismatch"
  | "Needs review";

type VerificationCase = {
  id: string;
  subject: string;
  sender: string;
  status: CaseStatus;
  received: string;
};

const cases: VerificationCase[] = [
  {
    id: "SHP-001",
    subject: "Draft BL verification - MAERSK LIMA",
    sender: "operations@shipping.com",
    status: "Analysing",
    received: "2 min ago",
  },
  {
    id: "SHP-002",
    subject: "Shipping documents for booking 839201",
    sender: "export@logistics.com",
    status: "Mismatch",
    received: "12 min ago",
  },
  {
    id: "SHP-003",
    subject: "BL draft for verification",
    sender: "docs@freight.com",
    status: "No mismatch",
    received: "24 min ago",
  },
  {
    id: "SHP-004",
    subject: "Document verification required",
    sender: "operations@cargo.com",
    status: "Needs review",
    received: "1 hour ago",
  },
];

export default function HomePage() {
  const searchParams = useSearchParams();

  const filter = searchParams.get("filter");

  const [searchQuery, setSearchQuery] =
    useState("");

  /*
   * First filter by sidebar selection.
   */
  const statusFilteredCases = useMemo(() => {
    if (filter === "mismatch") {
      return cases.filter(
        (item) => item.status === "Mismatch"
      );
    }

    if (filter === "review") {
      return cases.filter(
        (item) => item.status === "Needs review"
      );
    }

    /*
     * Verification queue and All cases currently
     * display every case.
     */
    return cases;
  }, [filter]);

  /*
   * Then apply the search box.
   *
   * User can search:
   * - SHP-002
   * - booking 839201
   * - export@logistics.com
   * - Mismatch
   */
  const visibleCases = useMemo(() => {
    const query = searchQuery
      .trim()
      .toLowerCase();

    if (!query) {
      return statusFilteredCases;
    }

    return statusFilteredCases.filter(
      (item) =>
        item.id.toLowerCase().includes(query) ||
        item.subject
          .toLowerCase()
          .includes(query) ||
        item.sender
          .toLowerCase()
          .includes(query) ||
        item.status
          .toLowerCase()
          .includes(query)
    );
  }, [searchQuery, statusFilteredCases]);

  /*
   * Page title changes according to sidebar.
   */
  const pageTitle =
    filter === "mismatch"
      ? "Mismatches"
      : filter === "review"
        ? "Needs review"
        : filter === "all"
          ? "All cases"
          : "Verification queue";

  const pageDescription =
    filter === "mismatch"
      ? "Cases where discrepancies were detected between shipping documents."
      : filter === "review"
        ? "Cases that require manual verification."
        : filter === "all"
          ? "All document verification cases."
          : "Incoming shipping document verification cases.";

  /*
   * Dashboard counts.
   */
  const analysingCount = cases.filter(
    (item) => item.status === "Analysing"
  ).length;

  const mismatchCount = cases.filter(
    (item) => item.status === "Mismatch"
  ).length;

  const noMismatchCount = cases.filter(
    (item) => item.status === "No mismatch"
  ).length;

  const reviewCount = cases.filter(
    (item) => item.status === "Needs review"
  ).length;

  return (
    <main className="flex min-h-screen bg-white text-gray-900">
      <Sidebar />

      <section className="min-w-0 flex-1">
        <Header />

        <div className="p-8">
          {/* Page heading */}
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              {pageTitle}
            </h1>

            <p className="mt-1 text-sm text-gray-500">
              {pageDescription}
            </p>
          </div>

          {/* Summary cards */}
          <div className="mt-6 grid grid-cols-4 gap-4">
            {/* Total */}
            <div className="rounded-lg border border-gray-200 bg-white p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                Total cases
              </p>

              <p className="mt-2 text-2xl font-semibold">
                {cases.length}
              </p>
            </div>

            {/* Analysing */}
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-blue-700">
                Analysing
              </p>

              <p className="mt-2 text-2xl font-semibold text-blue-800">
                {analysingCount}
              </p>
            </div>

            {/* Mismatches */}
            <div className="rounded-lg border border-red-200 bg-red-50 p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-red-700">
                Mismatches
              </p>

              <p className="mt-2 text-2xl font-semibold text-red-800">
                {mismatchCount}
              </p>
            </div>

            {/* Needs review */}
            <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-yellow-700">
                Needs review
              </p>

              <p className="mt-2 text-2xl font-semibold text-yellow-800">
                {reviewCount}
              </p>
            </div>
          </div>

          {/* Queue */}
          <section className="mt-6 overflow-hidden rounded-lg border border-gray-200 bg-white">
            {/* Queue toolbar */}
            <div className="flex items-center justify-between border-b border-gray-200 px-5 py-4">
              <div>
                <h2 className="text-sm font-semibold">
                  {pageTitle}
                </h2>

                <p className="mt-1 text-xs text-gray-500">
                  Showing {visibleCases.length} of{" "}
                  {statusFilteredCases.length} cases
                </p>
              </div>

              {/* Search */}
              <div className="relative">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"
                >
                  <circle
                    cx="11"
                    cy="11"
                    r="8"
                  />

                  <path d="m21 21-4.35-4.35" />
                </svg>

                <input
                  type="text"
                  value={searchQuery}
                  onChange={(event) =>
                    setSearchQuery(
                      event.target.value
                    )
                  }
                  placeholder="Search cases..."
                  className="w-72 rounded-md border border-gray-300 bg-white py-2 pl-9 pr-3 text-sm outline-none transition placeholder:text-gray-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                />
              </div>
            </div>

            {/* Table */}
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50 text-left">
                    <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
                      Case
                    </th>

                    <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
                      Subject
                    </th>

                    <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
                      Sender
                    </th>

                    <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
                      Status
                    </th>

                    <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
                      Received
                    </th>

                    <th className="w-12 px-5 py-3">
                      <span className="sr-only">
                        Open
                      </span>
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {visibleCases.map((item) => (
                    <tr
                      key={item.id}
                      className="border-b border-gray-100 last:border-b-0 hover:bg-gray-50"
                    >
                      {/* Case ID */}
                      <td className="px-5 py-4">
                        <Link
                          href={`/cases/${item.id}`}
                          className="font-medium text-blue-600 hover:underline"
                        >
                          {item.id}
                        </Link>
                      </td>

                      {/* Subject */}
                      <td className="px-5 py-4">
                        <Link
                          href={`/cases/${item.id}`}
                          className="block text-sm font-medium text-gray-900 hover:text-blue-600"
                        >
                          {item.subject}
                        </Link>
                      </td>

                      {/* Sender */}
                      <td className="px-5 py-4 text-sm text-gray-500">
                        {item.sender}
                      </td>

                      {/* Status */}
                      <td className="px-5 py-4">
                        <StatusBadge
                          status={item.status}
                        />
                      </td>

                      {/* Received */}
                      <td className="whitespace-nowrap px-5 py-4 text-sm text-gray-500">
                        {item.received}
                      </td>

                      {/* Open arrow */}
                      <td className="px-5 py-4 text-right">
                        <Link
                          href={`/cases/${item.id}`}
                          aria-label={`Open ${item.id}`}
                          className="text-lg text-gray-400 hover:text-blue-600"
                        >
                          →
                        </Link>
                      </td>
                    </tr>
                  ))}

                  {/* Empty search/filter state */}
                  {visibleCases.length === 0 && (
                    <tr>
                      <td
                        colSpan={6}
                        className="px-6 py-16 text-center"
                      >
                        <div className="mx-auto max-w-sm">
                          <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-gray-100 text-gray-400">
                            ?
                          </div>

                          <h3 className="mt-4 text-sm font-semibold text-gray-900">
                            No cases found
                          </h3>

                          <p className="mt-1 text-sm leading-6 text-gray-500">
                            No verification cases match
                            your current search or filter.
                          </p>

                          {searchQuery && (
                            <button
                              type="button"
                              onClick={() =>
                                setSearchQuery("")
                              }
                              className="mt-3 text-sm font-medium text-blue-600 hover:underline"
                            >
                              Clear search
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between border-t border-gray-200 bg-gray-50 px-5 py-3">
              <p className="text-xs text-gray-500">
                {visibleCases.length} case
                {visibleCases.length === 1
                  ? ""
                  : "s"}{" "}
                displayed
              </p>

              <div className="flex items-center gap-4 text-xs text-gray-500">
                <span>
                  No mismatch:{" "}
                  <strong className="font-semibold text-green-700">
                    {noMismatchCount}
                  </strong>
                </span>

                <span>
                  Needs review:{" "}
                  <strong className="font-semibold text-yellow-700">
                    {reviewCount}
                  </strong>
                </span>
              </div>
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}
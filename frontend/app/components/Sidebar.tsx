"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

export default function Sidebar() {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const currentFilter = searchParams.get("filter");

  const isQueuePage = pathname === "/";

  const isActive = (filter: string | null) => {
    if (!isQueuePage) {
      return false;
    }

    if (filter === null) {
      return currentFilter === null;
    }

    return currentFilter === filter;
  };

  const navItemClass = (active: boolean) =>
    `block rounded-md px-3 py-2 text-sm transition ${
      active
        ? "bg-blue-50 font-medium text-blue-600"
        : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
    }`;

  return (
    <aside className="flex min-h-screen w-64 shrink-0 flex-col border-r border-gray-200 bg-gray-50">
      {/* Brand */}
      <div className="border-b border-gray-200 px-6 py-5">
        <p className="text-xs font-medium uppercase tracking-wide text-gray-400">
          Averis
        </p>

        <h1 className="mt-1 text-base font-semibold text-gray-900">
          Document Verification
        </h1>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-4 py-5">
        <p className="mb-2 px-3 text-xs font-medium uppercase tracking-wide text-gray-400">
          Verification
        </p>

        <div className="space-y-1">
          <Link
            href="/"
            className={navItemClass(isActive(null))}
          >
            Verification queue
          </Link>

          <Link
            href="/?filter=all"
            className={navItemClass(isActive("all"))}
          >
            All cases
          </Link>

          <Link
            href="/?filter=mismatch"
            className={navItemClass(
              isActive("mismatch")
            )}
          >
            Mismatches
          </Link>

          <Link
            href="/?filter=review"
            className={navItemClass(isActive("review"))}
          >
            Needs review
          </Link>
        </div>
      </nav>

      {/* Team */}
      <div className="border-t border-gray-200 px-6 py-5">
        <p className="text-xs font-medium text-gray-500">
          Verification Team
        </p>

        <p className="mt-1 text-xs text-gray-400">
          Shipping Operations
        </p>
      </div>
    </aside>
  );
}
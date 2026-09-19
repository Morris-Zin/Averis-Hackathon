"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CasePage, CaseView, Category, QueueView } from "@/lib/contracts";
import { CATEGORY_LABELS, displayCaseKey } from "@/lib/contracts";
import { useActivePolling } from "@/lib/use-active-polling";
import { AppShell, queueLabels } from "./app-shell";
import { useSession } from "./session-provider";
import { Button, Input, Select, SelectItem, Spinner } from "./ui";

const QUEUES: QueueView[] = [
  "all",
  "mismatches",
  "review",
  "waiting",
  "completed",
];
const ALL_FILTERS = "all";

function isActiveProcessing(item: CaseView) {
  return item.processing === "queued" || item.processing === "running";
}

function resultFor(item: CaseView) {
  const labels = {
    failed: ["FAILED", "danger"],
    queued: ["QUEUED", "neutral"],
    running: ["RUNNING", "neutral"],
    unclassified: ["UNCLASSIFIED", "warning"],
    categorized: ["CATEGORIZED", "neutral"],
    needs_review: ["NEEDS REVIEW", "warning"],
    mismatch: ["MISMATCH", "danger"],
    mismatch_review: ["MISMATCH + REVIEW", "danger"],
    match: ["NO MISMATCH", "success"],
  } as const;
  const [label, tone] = labels[item.summary.kind];
  return { label, tone };
}
function relativeDate(value: string) {
  const date = new Date(value);
  const today = new Date();
  if (date.toDateString() === today.toDateString())
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return date.toLocaleDateString([], { day: "numeric", month: "short" });
}

export function InboxView() {
  const { api, session } = useSession();
  const searchParams = useSearchParams();
  const requestedView = searchParams.get("view");
  const initialView = QUEUES.includes(requestedView as QueueView)
    ? (requestedView as QueueView)
    : "all";
  const [view, setView] = useState<QueueView>(initialView);
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<Category | typeof ALL_FILTERS>(
    ALL_FILTERS,
  );
  const [assignee, setAssignee] = useState(ALL_FILTERS);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<CasePage | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const requestVersion = useRef(0);
  const requestController = useRef<AbortController | null>(null);

  useEffect(() => {
    const next = QUEUES.includes(requestedView as QueueView)
      ? (requestedView as QueueView)
      : "all";
    setView(next);
    setPage(1);
  }, [requestedView]);

  const load = useCallback(
    async (
      background = false,
      pollingSignal?: AbortSignal,
    ): Promise<boolean> => {
      if (background && requestController.current) return false;
      requestController.current?.abort();
      const controller = new AbortController();
      requestController.current = controller;
      const version = ++requestVersion.current;
      const abortForPolling = () => controller.abort();
      pollingSignal?.addEventListener("abort", abortForPolling, { once: true });
      if (!background) {
        setLoading(true);
        setError("");
      }
      try {
        const value = await api.cases(
          view,
          query,
          page,
          category === ALL_FILTERS ? undefined : category,
          assignee === ALL_FILTERS ? undefined : assignee,
          controller.signal,
        );
        if (controller.signal.aborted || version !== requestVersion.current)
          return false;
        setData(value);
        return true;
      } catch (reason) {
        if (controller.signal.aborted || version !== requestVersion.current)
          return false;
        if (!background)
          setError(
            reason instanceof Error
              ? reason.message
              : "Cases could not be loaded.",
          );
        return false;
      } finally {
        pollingSignal?.removeEventListener("abort", abortForPolling);
        if (version === requestVersion.current) {
          requestController.current = null;
          if (!background) setLoading(false);
        }
      }
    },
    [api, assignee, category, page, query, view],
  );

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(
    () => () => {
      requestVersion.current += 1;
      requestController.current?.abort();
    },
    [],
  );

  const poll = useCallback((signal: AbortSignal) => load(true, signal), [load]);
  const pollingActive =
    !loading && Boolean(data?.items.some(isActiveProcessing));
  useActivePolling(pollingActive, poll);
  const lastPage = useMemo(
    () => (data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1),
    [data],
  );

  return (
    <AppShell
      activeView={view}
      onViewChange={(next) => {
        setView(next);
        setPage(1);
      }}
    >
      <div className="page-header">
        <div className="breadcrumbs">
          <span>Projects</span>
          <span>/</span>
          <span>Shipping review</span>
          <span>/</span>
          <span>Queues</span>
        </div>
        <div className="page-title-row">
          <div>
            <h1>{queueLabels[view]}</h1>
            <p>
              {data
                ? `${data.total} ${data.total === 1 ? "case" : "cases"}`
                : "Review incoming shipping documents"}
            </p>
          </div>
          <Button variant="primary" onClick={() => void load()}>
            <RefreshCw size={15} />
            Refresh
          </Button>
        </div>
      </div>
      {!session?.live_enabled ? (
        <div className="demo-banner">
          <strong>Controlled server demo</strong>
          <span>
            These are saved illustrative scenarios. Classification is
            illustrative; document comparison is deterministic. Live AI and
            email are off.
          </span>
        </div>
      ) : null}
      <form
        className="filter-bar"
        onSubmit={(event) => {
          event.preventDefault();
          setQuery(draft);
          setPage(1);
        }}
      >
        <div className="filter-search">
          <Search size={16} />
          <Input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Search cases"
            aria-label="Search cases"
          />
        </div>
        <Button type="submit">
          <SlidersHorizontal size={15} />
          Search
        </Button>
        <div className="queue-filter">
          <Select
            value={category}
            label="Filter by category"
            onValueChange={(value) => {
              setCategory(value as Category | typeof ALL_FILTERS);
              setPage(1);
            }}
          >
            <SelectItem value={ALL_FILTERS}>All categories</SelectItem>
            {(Object.entries(CATEGORY_LABELS) as [Category, string][]).map(
              ([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ),
            )}
          </Select>
        </div>
        <div className="queue-filter">
          <Select
            value={assignee}
            label="Filter by assignee"
            onValueChange={(value) => {
              setAssignee(value);
              setPage(1);
            }}
          >
            <SelectItem value={ALL_FILTERS}>All assignees</SelectItem>
            {(session?.reviewers ?? []).map((reviewer) => (
              <SelectItem key={reviewer} value={reviewer}>
                {reviewer}
              </SelectItem>
            ))}
          </Select>
        </div>
        {category !== ALL_FILTERS || assignee !== ALL_FILTERS || query ? (
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setDraft("");
              setQuery("");
              setCategory(ALL_FILTERS);
              setAssignee(ALL_FILTERS);
              setPage(1);
            }}
          >
            Clear filters
          </Button>
        ) : null}
      </form>
      <div className="issue-list" aria-busy={loading}>
        {loading ? (
          <div className="table-state">
            <Spinner label="Loading cases" />
          </div>
        ) : error ? (
          <div className="table-state error-state">
            <strong>Cases could not be loaded</strong>
            <span>{error}</span>
            <Button onClick={() => void load()}>Try again</Button>
          </div>
        ) : data?.items.length ? (
          <div className="table-scroll">
            <table className="cases-table">
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Summary</th>
                  <th>Classification</th>
                  <th>Result</th>
                  <th>Assignee</th>
                  <th>Received</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => {
                  const result = resultFor(item);
                  return (
                    <tr key={item.id}>
                      <td>
                        <Link
                          className="case-key"
                          title={item.id}
                          href={`/review/?case=${encodeURIComponent(item.id)}`}
                        >
                          {displayCaseKey(item.id)}
                        </Link>
                      </td>
                      <td>
                        <Link
                          className="case-summary"
                          href={`/review/?case=${encodeURIComponent(item.id)}`}
                        >
                          {item.subject}
                        </Link>
                        <span className="sender-line">{item.sender}</span>
                      </td>
                      <td>
                        {item.classification
                          ? CATEGORY_LABELS[
                              item.classification.accepted ??
                                item.classification.suggested
                            ]
                          : "Unclassified"}
                      </td>
                      <td>
                        <span className={`status-lozenge ${result.tone}`}>
                          {result.label}
                        </span>
                      </td>
                      <td>
                        <span className="assignee-cell">
                          <span className="mini-avatar">
                            {item.assignee
                              .split(" ")
                              .map((part) => part[0])
                              .join("")
                              .slice(0, 2)}
                          </span>
                          {item.assignee}
                        </span>
                      </td>
                      <td>{relativeDate(item.received_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="table-state">
            <strong>No cases in this queue</strong>
            <span>Try another queue or change your search.</span>
          </div>
        )}
        {data ? (
          <div className="pagination">
            <span>
              {data.total
                ? `${(page - 1) * data.page_size + 1}–${Math.min(page * data.page_size, data.total)} of ${data.total}`
                : "0 cases"}
            </span>
            <Button
              variant="ghost"
              size="sm"
              aria-label="Previous page"
              disabled={page <= 1}
              onClick={() => setPage((value) => value - 1)}
            >
              <ChevronLeft size={17} />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              aria-label="Next page"
              disabled={page >= lastPage}
              onClick={() => setPage((value) => value + 1)}
            >
              <ChevronRight size={17} />
            </Button>
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}

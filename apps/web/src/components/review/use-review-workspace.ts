"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type {
  Action,
  ActionDraft,
  CaseView,
  Category,
  Field,
} from "@/lib/contracts";
import { ApiError } from "@/lib/api";
import { useActivePolling } from "@/lib/use-active-polling";
import { isActionAllowed, shouldIgnoreLateResponse } from "@/lib/case-binding";
import { useSession } from "../session-provider";
import { resultSummary } from "./presentation";

type Side = "si" | "bl";
type Tab = "comparison" | "documents" | "activity";

export function useReviewWorkspace(id: string) {
  const { status, session, api, sessionActionPending } = useSession();
  const [item, setItem] = useState<CaseView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState(false);
  const [tab, setTab] = useState<Tab>("comparison");
  const [activeField, setActiveField] = useState<Field>("shipper");
  const [correctSide, setCorrectSide] = useState<Side | null>(null);
  const [categoryOverride, setCategoryDraft] = useState<Category | null>(null);
  const [pairSiOverride, setPairSi] = useState<string | null>(null);
  const [pairBlOverride, setPairBl] = useState<string | null>(null);
  const requestVersion = useRef(0);
  const requestController = useRef<AbortController | null>(null);

  useEffect(() => {
    if (status === "ready") return;
    requestVersion.current += 1;
    requestController.current?.abort();
    requestController.current = null;
    setItem(null);
    setError("");
    setNotice("");
    setPending(false);
    setCorrectSide(null);
    setCategoryDraft(null);
    setPairSi(null);
    setPairBl(null);
  }, [status]);

  const load = useCallback(
    async (
      background = false,
      resetDrafts = !background,
      pollingSignal?: AbortSignal,
    ): Promise<boolean> => {
      if (status !== "ready") return false;
      if (!id) {
        setItem(null);
        setError("No case was selected.");
        setLoading(false);
        return false;
      }
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
        const value = await api.case(id, controller.signal);
        if (
          controller.signal.aborted ||
          shouldIgnoreLateResponse(
            id,
            value.id,
            version,
            requestVersion.current,
          )
        )
          return false;
        setItem(value);
        if (resetDrafts) {
          setCategoryDraft(null);
          setPairSi(null);
          setPairBl(null);
          const important = value.report?.findings?.find(
            (finding) => finding.outcome !== "match",
          )?.field;
          if (important) setActiveField(important);
        }
        return true;
      } catch (reasonValue) {
        if (controller.signal.aborted || version !== requestVersion.current)
          return false;
        if (!background)
          setError(
            reasonValue instanceof Error
              ? reasonValue.message
              : "Case could not be loaded.",
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
    [api, id, status],
  );

  useEffect(() => {
    // Navigating to another case invalidates the previous case view immediately.
    // A failed load must never leave actions enabled against the previous case.
    setItem(null);
    setPending(false);
    setCorrectSide(null);
    setNotice("");
    setError("");
    setCategoryDraft(null);
    setPairSi(null);
    setPairBl(null);
    void load(false, true);
    return () => {
      requestVersion.current += 1;
      requestController.current?.abort();
    };
  }, [load]);

  const act = useCallback(
    async (action: ActionDraft, success: string) => {
      // Bind every mutation to the requested case ID. Refreshing the same case
      // preserves drafts; a stale view for another case can never mutate.
      if (
        !item ||
        !isActionAllowed(id, item.id) ||
        !session ||
        sessionActionPending
      )
        return false;
      requestVersion.current += 1;
      requestController.current?.abort();
      requestController.current = null;
      const mutationVersion = requestVersion.current;
      setPending(true);
      setError("");
      setNotice("");
      try {
        // Send only fields relevant to that action; required fields are
        // validated at the HTTP boundary.
        const updated = await api.action(
          id,
          {
            ...action,
            expected_revision: item.revision,
          } as unknown as Action,
          session.csrf_token,
        );
        if (mutationVersion !== requestVersion.current) return false;
        // Ignore late mutation responses that no longer match the requested case.
        if (updated.id !== id) return false;
        setItem(updated);
        if (action.kind === "revision" || action.kind === "pair") {
          setPairSi(null);
          setPairBl(null);
          setCorrectSide(null);
        }
        if (action.kind === "category") {
          setCategoryDraft(null);
        }
        setNotice(success);
        return true;
      } catch (reasonValue) {
        if (mutationVersion !== requestVersion.current) return false;
        if (reasonValue instanceof ApiError && reasonValue.status === 409) {
          setPending(false);
          const refreshed = await load(false, false);
          if (refreshed)
            setError(
              "This case changed while you were reviewing it. Your change was not saved. The latest version has been loaded.",
            );
        } else
          setError(
            reasonValue instanceof Error
              ? reasonValue.message
              : "The action could not be saved.",
          );
        return false;
      } finally {
        if (mutationVersion === requestVersion.current) setPending(false);
      }
    },
    [api, id, item, load, session, sessionActionPending],
  );

  const processingActive =
    item?.processing === "queued" || item?.processing === "running";
  const poll = useCallback(
    (signal: AbortSignal) => load(true, false, signal),
    [load],
  );
  useActivePolling(
    status === "ready" &&
      Boolean(item) &&
      processingActive &&
      !pending &&
      !sessionActionPending &&
      !loading,
    poll,
  );

  const activeFinding = item?.report?.findings?.find(
    (finding) => finding.field === activeField,
  );
  const siAttachment = activeFinding
    ? item?.attachments.find(
        (attachment) => attachment.id === activeFinding.si.document_id,
      )
    : item?.attachments.find(
        (attachment) => attachment.role === "SI" && !attachment.superseded,
      );
  const blAttachment = activeFinding
    ? item?.attachments.find(
        (attachment) => attachment.id === activeFinding.bl.document_id,
      )
    : item?.attachments.find(
        (attachment) => attachment.role === "BL" && !attachment.superseded,
      );
  const correctionReading =
    correctSide === "si" ? activeFinding?.si : activeFinding?.bl;
  const correctionAttachment = item?.attachments.find(
    (attachment) =>
      attachment.id === correctionReading?.document_id &&
      !attachment.superseded,
  );
  const currentAttachments =
    item?.attachments.filter((attachment) => !attachment.superseded) ?? [];
  const controlled =
    item?.history.some((entry) => entry.actor === "Demo setup") ?? false;
  const summary = item ? resultSummary(item) : null;
  const classificationConfidence = item?.classification
    ? Math.round(item.classification.confidence * 100)
    : null;
  // Untouched controls follow worker updates; explicit reviewer drafts survive polling.
  const categoryDraft =
    categoryOverride ??
    item?.classification?.accepted ??
    item?.classification?.suggested ??
    "GENERAL";
  const pairSi =
    pairSiOverride ?? currentAttachments.find((a) => a.role === "SI")?.id ?? "";
  const pairBl =
    pairBlOverride ?? currentAttachments.find((a) => a.role === "BL")?.id ?? "";
  const pairChanged = item
    ? pairSi !==
        (item.attachments.find(
          (attachment) => attachment.role === "SI" && !attachment.superseded,
        )?.id ?? "") ||
      pairBl !==
        (item.attachments.find(
          (attachment) => attachment.role === "BL" && !attachment.superseded,
        )?.id ?? "")
    : false;
  function openCorrection(side: Side) {
    const reading = side === "si" ? activeFinding?.si : activeFinding?.bl;
    const source = item?.attachments.find(
      (attachment) =>
        attachment.id === reading?.document_id && !attachment.superseded,
    );
    if (!reading || !source) return;
    setCorrectSide(side);
  }

  return {
    status,
    session,
    item,
    loading,
    error,
    notice,
    pending: pending || sessionActionPending,
    act,
    navigation: { tab, setTab, activeField, setActiveField },
    category: { categoryDraft, setCategoryDraft, classificationConfidence },
    documents: {
      pairSi,
      setPairSi,
      pairBl,
      setPairBl,
      pairChanged,
      currentAttachments,
    },
    comparison: { activeFinding, siAttachment, blAttachment, summary },
    correction: {
      correctSide,
      setCorrectSide,
      correctionReading,
      correctionAttachment,
      openCorrection,
    },
    controlled,
    processingActive,
  };
}

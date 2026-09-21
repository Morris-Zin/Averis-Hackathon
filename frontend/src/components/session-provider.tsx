"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ApiError, liveApi, type AppApi } from "@/lib/api";
import type { SessionView } from "@/lib/contracts";

type SessionState = {
  status: "loading" | "signed-out" | "unavailable" | "ready";
  session: SessionView | null;
  api: AppApi;
  unavailableMessage: string;
  sessionMessage: string;
  sessionActionPending: boolean;
  sessionActionError: string;
  enterDemo: () => Promise<void>;
  setActor: (actor: string) => Promise<void>;
  logout: () => Promise<void>;
};

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionState["status"]>("loading");
  const [session, setSession] = useState<SessionView | null>(null);
  const [unavailableMessage, setUnavailableMessage] = useState("");
  const [sessionMessage, setSessionMessage] = useState("");
  const [sessionActionPending, setSessionActionPending] = useState(false);
  const [sessionActionError, setSessionActionError] = useState("");
  const sessionActionInFlight = useRef(false);

  const expireSession = useCallback(() => {
    setSession(null);
    setStatus("signed-out");
    setUnavailableMessage("");
    setSessionActionError("");
    setSessionMessage(
      "Your workspace session expired. Its saved cases are no longer shown. Enter a new demo workspace to continue.",
    );
  }, []);

  const guard = useCallback(
    async <T,>(operation: Promise<T>): Promise<T> => {
      try {
        return await operation;
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) expireSession();
        throw error;
      }
    },
    [expireSession],
  );

  const api = useMemo<AppApi>(
    () => ({
      importEmail: (...args: Parameters<AppApi["importEmail"]>) =>
        guard(liveApi.importEmail(...args)),
      bulkPreview: (...args: Parameters<AppApi["bulkPreview"]>) =>
        guard(liveApi.bulkPreview(...args)),
      bulkImport: (...args: Parameters<AppApi["bulkImport"]>) =>
        guard(liveApi.bulkImport(...args)),
      session: () => guard(liveApi.session()),
      enterDemo: () => guard(liveApi.enterDemo()),
      cases: (...args: Parameters<AppApi["cases"]>) =>
        guard(liveApi.cases(...args)),
      case: (...args: Parameters<AppApi["case"]>) =>
        guard(liveApi.case(...args)),
      action: (...args: Parameters<AppApi["action"]>) =>
        guard(liveApi.action(...args)),
      actor: (...args: Parameters<AppApi["actor"]>) =>
        guard(liveApi.actor(...args)),
      logout: (...args: Parameters<AppApi["logout"]>) =>
        guard(liveApi.logout(...args)),
    }),
    [guard],
  );

  useEffect(() => {
    void liveApi
      .session()
      .then((value) => {
        setSession(value);
        setStatus("ready");
        setUnavailableMessage("");
        setSessionMessage("");
      })
      .catch((error: unknown) => {
        setSession(null);
        if (error instanceof ApiError && error.status === 401) {
          setStatus("signed-out");
          return;
        }
        setUnavailableMessage(
          error instanceof Error
            ? error.message
            : "The Averis server is unavailable.",
        );
        setStatus("unavailable");
      });
  }, []);

  const enterDemo = useCallback(async () => {
    const value = await liveApi.enterDemo();
    setSession(value);
    setStatus("ready");
    setUnavailableMessage("");
    setSessionMessage("");
  }, []);

  const setActor = useCallback(
    async (actor: string) => {
      if (!session || sessionActionInFlight.current) return;
      sessionActionInFlight.current = true;
      setSessionActionPending(true);
      setSessionActionError("");
      try {
        const value = await api.actor(actor, session.csrf_token);
        setSession(value);
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 401))
          setSessionActionError(
            error instanceof Error
              ? error.message
              : "The reviewer change could not be saved.",
          );
      } finally {
        sessionActionInFlight.current = false;
        setSessionActionPending(false);
      }
    },
    [api, session],
  );

  const logout = useCallback(async () => {
    if (!session || sessionActionInFlight.current) return;
    sessionActionInFlight.current = true;
    setSessionActionPending(true);
    setSessionActionError("");
    try {
      try {
        await api.logout(session.csrf_token);
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return;
        throw error;
      }
      setSession(null);
      setStatus("signed-out");
      setSessionMessage("");
    } catch (error) {
      setSessionActionError(
        error instanceof Error ? error.message : "Could not log out.",
      );
    } finally {
      sessionActionInFlight.current = false;
      setSessionActionPending(false);
    }
  }, [api, session]);

  const value = useMemo<SessionState>(
    () => ({
      status,
      session,
      api,
      unavailableMessage,
      sessionMessage,
      sessionActionPending,
      sessionActionError,
      enterDemo,
      setActor,
      logout,
    }),
    [
      status,
      session,
      api,
      unavailableMessage,
      sessionMessage,
      sessionActionPending,
      sessionActionError,
      enterDemo,
      setActor,
      logout,
    ],
  );
  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}

export function useSession() {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}

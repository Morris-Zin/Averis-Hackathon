import type { Action, CasePage, CaseView, Category, QueueView, SessionView } from "./contracts";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) {
        const issues = body.detail
          .map((issue: unknown) => issue && typeof issue === "object" && "msg" in issue ? issue.msg : null)
          .filter((issue): issue is string => typeof issue === "string")
          .slice(0, 3);
        if (issues.length) message = issues.join(". ");
      }
    } catch {
      // Keep the status-based message for non-JSON failures.
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const liveApi = {
  session: () => request<SessionView>("/api/session"),
  enterDemo: () => request<SessionView>("/api/demo/session", { method: "POST", body: "{}" }),
  cases: (view: QueueView, query: string, page: number, category?: Category, assignee?: string, signal?: AbortSignal) => {
    const params = new URLSearchParams({ view, q: query, page: String(page) });
    if (category) params.set("category", category);
    if (assignee) params.set("assignee", assignee);
    return request<CasePage>(`/api/cases?${params.toString()}`, { signal });
  },
  case: (id: string, signal?: AbortSignal) => request<CaseView>(`/api/cases/${encodeURIComponent(id)}`, { signal }),
  action: (id: string, action: Action, csrfToken: string) => request<CaseView>(`/api/cases/${encodeURIComponent(id)}/actions`, { method: "POST", body: JSON.stringify(action), headers: { "X-CSRF-Token": csrfToken } }),
  actor: (actor: string, csrfToken: string) => request<SessionView>("/api/session/actor", { method: "POST", body: JSON.stringify({ actor }), headers: { "X-CSRF-Token": csrfToken } }),
  logout: (csrfToken: string) => request<{ ok: boolean }>("/api/session/logout", { method: "POST", body: "{}", headers: { "X-CSRF-Token": csrfToken } }),
};

export type AppApi = typeof liveApi;
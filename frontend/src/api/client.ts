// In HTTPS dev mode the API is proxied through the page's own origin (see vite.config.ts).
import { cacheable, cachedResponse, connectivity, enforceLimit, markOffline, markOnline, saveResponse } from "./offline";

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.MODE === "https" ? "" : "http://localhost:8000")).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

type ValidationIssue = { loc?: (string | number)[]; msg?: string };

function describeDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return (detail as ValidationIssue[])
      .map((issue) => {
        const field = (issue.loc ?? []).filter((part) => part !== "body").join(".");
        const msg = (issue.msg ?? "Invalid value").replace(/^Value error, /, "");
        return field ? `${field}: ${msg}` : msg;
      })
      .join("; ");
  }
  return null;
}

const RETRY_DELAY_MS = 300;

// The session token sent with every request. Set by the auth provider; null while signed out.
let sessionToken: string | null = null;
export const setSessionToken = (token: string | null) => { sessionToken = token; };
/** Fired when the API rejects the session (expired, revoked or the account disabled). */
export const SESSION_EXPIRED_EVENT = "dockyard:session-expired";

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  // A read that fails before reaching the server (a dropped connection, not an abort or an HTTP error) is
  // retried once; reads are safe to repeat. Writes are never retried here, so they cannot be duplicated.
  const isRead = (init.method ?? "GET").toUpperCase() === "GET";
  const attempts = isRead ? 2 : 1;
  // Read-only offline mode: no change is sent while the API is known to be unreachable.
  if (!isRead && connectivity().offline && !path.startsWith("/api/v1/auth/")) {
    throw new ApiError("You are offline: changes are disabled until the connection to the server returns.", 0);
  }
  let response: Response | undefined;
  for (let attempt = 1; !response; attempt++) {
    try {
      response = await fetch(`${API_BASE_URL}${path}`, {
        ...init,
        headers: { "Content-Type": "application/json", ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}), ...init.headers },
      });
    } catch (err) {
      if (init.signal?.aborted) throw err;
      if (attempt >= attempts) {
        const cached = isRead && cacheable(path) ? cachedResponse<T>(path) : null;
        if (cached) {
          markOffline(cached.at);
          return cached.body;
        }
        if (isRead) markOffline(null);
        throw new ApiError(`Cannot reach the API at ${API_BASE_URL}. Check that the backend is running.`, 0);
      }
      await new Promise((resolve) => window.setTimeout(resolve, RETRY_DELAY_MS));
      if (init.signal?.aborted) throw err;
    }
  }
  if (!response) throw new ApiError(`Cannot reach the API at ${API_BASE_URL}.`, 0);  // unreachable; narrows the type

  markOnline();
  const body = await response.json().catch(() => null);
  if (response.ok && isRead && cacheable(path)) {
    saveResponse(path, body);
    if (Math.random() < 0.05) enforceLimit();
  }
  if (!response.ok) {
    if (response.status === 401 && sessionToken && !path.startsWith("/api/v1/auth/login")) {
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
    const message = describeDetail(body?.detail) ?? `Request failed with status ${response.status}`;
    throw new ApiError(message, response.status);
  }
  return body as T;
}

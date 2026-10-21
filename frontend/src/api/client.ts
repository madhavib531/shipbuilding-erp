export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

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

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  // A read that fails before reaching the server (a dropped connection, not an abort or an HTTP error) is
  // retried once; reads are safe to repeat. Writes are never retried here, so they cannot be duplicated.
  const attempts = (init.method ?? "GET").toUpperCase() === "GET" ? 2 : 1;
  let response: Response | undefined;
  for (let attempt = 1; !response; attempt++) {
    try {
      response = await fetch(`${API_BASE_URL}${path}`, {
        ...init,
        headers: { "Content-Type": "application/json", ...init.headers },
      });
    } catch (err) {
      if (init.signal?.aborted) throw err;
      if (attempt >= attempts) {
        throw new ApiError(`Cannot reach the API at ${API_BASE_URL}. Check that the backend is running.`, 0);
      }
      await new Promise((resolve) => window.setTimeout(resolve, RETRY_DELAY_MS));
      if (init.signal?.aborted) throw err;
    }
  }
  if (!response) throw new ApiError(`Cannot reach the API at ${API_BASE_URL}.`, 0);  // unreachable; narrows the type

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message = describeDetail(body?.detail) ?? `Request failed with status ${response.status}`;
    throw new ApiError(message, response.status);
  }
  return body as T;
}

/** Read-only offline support: the last successful response of each read is kept in this browser and served when
 * the API cannot be reached. Writes are refused while offline, so nothing is ever changed from stale data.
 * The cache belongs to the signed-in user and is cleared on sign-out. */

const PREFIX = "dockyard.cache:";
const MAX_ENTRIES = 300;

export const OFFLINE_EVENT = "dockyard:connectivity";
let offlineSince: string | null = null;  // time of the cached data being shown, while offline

export type Connectivity = { offline: boolean; dataFrom: string | null };
export const connectivity = (): Connectivity => ({ offline: offlineSince !== null, dataFrom: offlineSince });

function announce() {
  window.dispatchEvent(new CustomEvent(OFFLINE_EVENT, { detail: connectivity() }));
}

export function markOnline() {
  if (offlineSince === null) return;
  offlineSince = null;
  announce();
}

export function markOffline(dataFrom: string | null) {
  // Keep the oldest time shown, so the banner never claims the data is fresher than it is.
  const next = offlineSince && dataFrom && offlineSince < dataFrom ? offlineSince : dataFrom ?? offlineSince ?? new Date().toISOString();
  const changed = offlineSince === null || next !== offlineSince;
  offlineSince = next;
  if (changed) announce();
}

/** Only ordinary data reads are cached: never sign-in, the session, health checks or the AI assistant. */
export const cacheable = (path: string) =>
  path.startsWith("/api/v1/") && !path.startsWith("/api/v1/auth/") && !path.startsWith("/api/v1/assistant/") && !path.startsWith("/api/v1/users");

export function saveResponse(path: string, body: unknown) {
  try {
    localStorage.setItem(PREFIX + path, JSON.stringify({ at: new Date().toISOString(), body }));
  } catch {
    trim(Math.ceil(MAX_ENTRIES / 3));  // storage full: drop the oldest entries; this response is simply not cached
  }
}

export function cachedResponse<T>(path: string): { at: string; body: T } | null {
  try {
    const raw = localStorage.getItem(PREFIX + path);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function entries(): { key: string; at: string }[] {
  const out = [];
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (!key?.startsWith(PREFIX)) continue;
      try { out.push({ key, at: JSON.parse(localStorage.getItem(key) ?? "{}").at ?? "" }); } catch { out.push({ key, at: "" }); }
    }
  } catch { /* storage unavailable */ }
  return out;
}

function trim(count: number) {
  for (const e of entries().sort((a, b) => a.at.localeCompare(b.at)).slice(0, count)) {
    try { localStorage.removeItem(e.key); } catch { /* ignore */ }
  }
}

export function enforceLimit() {
  const all = entries();
  if (all.length > MAX_ENTRIES) trim(all.length - MAX_ENTRIES);
}

export function clearCache() {
  for (const e of entries()) {
    try { localStorage.removeItem(e.key); } catch { /* ignore */ }
  }
  offlineSince = null;
}

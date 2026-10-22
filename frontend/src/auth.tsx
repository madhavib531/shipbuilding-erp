import { createContext, useCallback, useContext, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { ApiError, SESSION_EXPIRED_EVENT, setSessionToken } from "./api/client";
import { clearCache } from "./api/offline";
import { getMe, login as apiLogin, logout as apiLogout, type Me, type Permission } from "./api/auth";
import { Button, Icon, Input } from "./components/ui";

const STORAGE_KEY = "dockyard.session";
type Stored = { token: string; expiresAt: string; user: Me };

type AuthState = {
  user: Me;
  can: (permission: Permission) => boolean;
  signOut: () => void;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth outside AuthProvider");
  return value;
}

/** Title for a control the signed-in user's role cannot use, or undefined when allowed. */
export function useDenied() {
  const { user, can } = useAuth();
  return (permission: Permission) => (can(permission) ? undefined : `Your role (${user.role}) can't do this`);
}

const read = (): Stored | null => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const stored = raw ? (JSON.parse(raw) as Stored) : null;
    return stored && new Date(stored.expiresAt) > new Date() ? stored : null;
  } catch { return null; }
};
const write = (s: Stored | null) => {
  try { if (s) localStorage.setItem(STORAGE_KEY, JSON.stringify(s)); else localStorage.removeItem(STORAGE_KEY); } catch { /* storage unavailable */ }
};

export const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]!.toUpperCase()).join("") || "?";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Stored | null>(() => {
    const stored = read();
    setSessionToken(stored?.token ?? null);
    return stored;
  });
  const [notice, setNotice] = useState("");

  const clear = useCallback((message = "") => {
    clearCache();  // saved offline data belongs to the user who signed out
    setSessionToken(null);
    write(null);
    setSession(null);
    setNotice(message);
  }, []);

  // Confirm a remembered session is still valid and pick up role changes. If the API cannot be reached the
  // remembered profile is kept, so the read-only offline view still knows who is signed in.
  const refresh = useCallback(async () => {
    const stored = read();
    if (!stored) return;
    try {
      const user = await getMe();
      const next = { ...stored, user };
      write(next);
      setSession(next);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) clear("Your session has ended. Sign in again.");
    }
  }, [clear]);

  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    const onExpired = () => clear("Your session has ended. Sign in again.");
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, [clear]);

  const signOut = useCallback(() => {
    apiLogout().catch(() => {});  // the token is forgotten locally either way
    clear();
  }, [clear]);

  const value = useMemo<AuthState | null>(() => session && {
    user: session.user,
    can: (permission) => session.user.permissions.includes(permission),
    signOut,
    refresh,
  }, [session, signOut, refresh]);

  if (!value) {
    return <SignIn notice={notice} onSignedIn={(s) => {
      clearCache();
      setSessionToken(s.token);
      write(s);
      setNotice("");
      setSession(s);
    }}/>;
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function SignIn({ notice, onSignedIn }: { notice: string; onSignedIn: (s: Stored) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!username.trim() || !password) return setError("Enter your username and password.");
    setBusy(true);
    setError("");
    try {
      const r = await apiLogin(username.trim(), password);
      onSignedIn({ token: r.token, expiresAt: r.expires_at, user: r.user });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
      setBusy(false);
    }
  };

  return <div className="signin-page">
    <form className="signin-card" onSubmit={submit} noValidate>
      <div className="signin-brand"><span className="brand-mark"><Icon name="ship"/></span><div><strong>Dockyard Materials Command</strong><small>Sign in to continue</small></div></div>
      {notice && <div className="notice" role="status"><Icon name="warning"/>{notice}</div>}
      <label><span>Username</span><Input name="username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} disabled={busy} autoFocus/></label>
      <label><span>Password</span><Input name="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} disabled={busy}/></label>
      {error && <div className="notice" role="alert"><Icon name="warning"/>{error}</div>}
      <Button type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Button>
      <p className="muted-copy">Accounts are created by an admin. The first admin is created with <code>python scripts/create_user.py</code> in the backend folder.</p>
    </form>
  </div>;
}

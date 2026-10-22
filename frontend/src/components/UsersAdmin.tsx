import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Badge, Button, Icon, Input, Select } from "./ui";
import { ROLES, ROLE_SUMMARY, changePassword, createUser, listUsers, resetPassword, updateUser, type Role, type UserAccount } from "../api/auth";
import { useAuth } from "../auth";

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "Never");

/** Admin-only: create accounts, change roles, deactivate, reset passwords. */
export function UsersAdmin() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<UserAccount[] | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [adding, setAdding] = useState(false);
  const [resetFor, setResetFor] = useState<UserAccount | null>(null);

  const load = useCallback(() => listUsers().then((u) => { setUsers(u); setError(""); }).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  const change = async (u: UserAccount, body: Parameters<typeof updateUser>[1], done: string) => {
    setError(""); setMessage("");
    try { await updateUser(u.id, body); setMessage(done); await load(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  };

  return <div className="users-admin">
    <div className="users-head"><h3>User accounts</h3><Button icon="plus" onClick={() => setAdding(true)}>Add user</Button></div>
    {error && <div className="notice" role="alert"><Icon name="warning"/>{error}</div>}
    {message && <div className="notice" role="status"><Icon name="check"/>{message}</div>}
    {!users ? <p className="muted-copy">Loading users…</p> : <div className="table-scroll"><table><thead><tr><th>User</th><th>Role</th><th>Last sign-in</th><th>Status</th><th aria-label="Actions"/></tr></thead><tbody>
      {users.map((u) => <tr key={u.id}>
        <td><strong>{u.display_name}{u.id === me.id ? " (you)" : ""}</strong><small>{u.username}{u.email ? ` · ${u.email}` : ""}</small></td>
        <td><Select aria-label={`Role of ${u.username}`} value={u.role} onChange={(e) => change(u, { role: e.target.value as Role }, `${u.display_name} is now ${e.target.value}`)}>{ROLES.map((r) => <option key={r}>{r}</option>)}</Select></td>
        <td><small>{when(u.last_login_at)}</small></td>
        <td><Badge tone={u.is_active ? "success" : "neutral"}>{u.is_active ? "Active" : "Disabled"}</Badge></td>
        <td className="users-actions">
          <Button variant="ghost" onClick={() => setResetFor(u)}>Reset password</Button>
          {u.id !== me.id && <Button variant="secondary" onClick={() => change(u, { is_active: !u.is_active }, `${u.display_name} ${u.is_active ? "disabled and signed out" : "enabled"}`)}>{u.is_active ? "Disable" : "Enable"}</Button>}
        </td>
      </tr>)}
    </tbody></table></div>}
    <div className="role-legend">{ROLES.map((r) => <p key={r}><strong>{r}</strong> — {ROLE_SUMMARY[r]}</p>)}</div>
    {adding && <AddUserDialog onClose={() => setAdding(false)} onDone={(m) => { setAdding(false); setMessage(m); load(); }}/>}
    {resetFor && <ResetPasswordDialog user={resetFor} onClose={() => setResetFor(null)} onDone={(m) => { setResetFor(null); setMessage(m); }}/>}
  </div>;
}

function Dialog({ title, onClose, onSubmit, busy, error, submitLabel, children }: {
  title: string; onClose: () => void; onSubmit: (e: FormEvent) => void; busy: boolean; error: string; submitLabel: string; children: ReactNode;
}) {
  return <div className="dialog-layer" role="dialog" aria-modal="true" aria-label={title}>
    <button className="dialog-scrim" onClick={onClose} aria-label="Close dialog"/>
    <form className="dialog" onSubmit={onSubmit} noValidate>
      <div className="dialog-header"><div><h2>{title}</h2></div><button type="button" className="icon-button" onClick={onClose} aria-label="Close dialog"><Icon name="close"/></button></div>
      <div className="form-grid">{children}</div>
      {error && <div className="notice" role="alert"><Icon name="warning"/>{error}</div>}
      <div className="dialog-actions"><Button type="button" variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button><Button type="submit" disabled={busy}>{busy ? "Saving…" : submitLabel}</Button></div>
    </form>
  </div>;
}

function AddUserDialog({ onClose, onDone }: { onClose: () => void; onDone: (message: string) => void }) {
  const [form, setForm] = useState({ username: "", display_name: "", email: "", role: "Viewer" as Role, password: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.username.trim() || !form.display_name.trim()) return setError("Username and name are required.");
    if (form.password.length < 10) return setError("The password must be at least 10 characters long.");
    setBusy(true); setError("");
    try {
      const u = await createUser({ ...form, username: form.username.trim(), display_name: form.display_name.trim(), email: form.email.trim() || undefined });
      onDone(`${u.display_name} can now sign in as ${u.username}`);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); setBusy(false); }
  };
  const full = { gridColumn: "1 / -1" } as const;
  return <Dialog title="Add user" onClose={onClose} onSubmit={submit} busy={busy} error={error} submitLabel="Create user">
    <label><span>Username</span><Input name="username" value={form.username} onChange={set("username")} autoComplete="off" autoFocus/></label>
    <label><span>Name (shown on changes)</span><Input name="display_name" value={form.display_name} onChange={set("display_name")}/></label>
    <label><span>Role</span><Select name="role" value={form.role} onChange={set("role")}>{ROLES.map((r) => <option key={r}>{r}</option>)}</Select></label>
    <label><span>Email (optional)</span><Input name="email" type="email" value={form.email} onChange={set("email")}/></label>
    <label style={full}><span>Initial password (at least 10 characters)</span><Input name="password" type="password" autoComplete="new-password" value={form.password} onChange={set("password")}/></label>
    <p className="muted-copy" style={full}>{ROLE_SUMMARY[form.role]}. Give the password to the user directly; they can change it after signing in.</p>
  </Dialog>;
}

function ResetPasswordDialog({ user, onClose, onDone }: { user: UserAccount; onClose: () => void; onDone: (message: string) => void }) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (password.length < 10) return setError("The password must be at least 10 characters long.");
    setBusy(true); setError("");
    try { await resetPassword(user.id, password); onDone(`Password reset for ${user.display_name}; they have been signed out everywhere`); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); setBusy(false); }
  };
  return <Dialog title={`Reset password for ${user.display_name}`} onClose={onClose} onSubmit={submit} busy={busy} error={error} submitLabel="Reset password">
    <label style={{ gridColumn: "1 / -1" }}><span>New password (at least 10 characters)</span><Input name="password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus/></label>
  </Dialog>;
}

/** Change your own password; every session (including this one) is signed out afterwards. */
export function ChangePasswordDialog({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (next.length < 10) return setError("The new password must be at least 10 characters long.");
    if (next !== repeat) return setError("The new passwords do not match.");
    setBusy(true); setError("");
    try {
      await changePassword(current, next);
      onDone();
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); setBusy(false); }
  };
  const full = { gridColumn: "1 / -1" } as const;
  return <Dialog title="Change password" onClose={onClose} onSubmit={submit} busy={busy} error={error} submitLabel="Change password">
    <label style={full}><span>Current password</span><Input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} autoFocus/></label>
    <label><span>New password</span><Input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)}/></label>
    <label><span>Repeat new password</span><Input type="password" autoComplete="new-password" value={repeat} onChange={(e) => setRepeat(e.target.value)}/></label>
    <p className="muted-copy" style={full}>You will be signed out on every device and asked to sign in with the new password.</p>
  </Dialog>;
}

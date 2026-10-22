import { useCallback, useEffect, useRef, useState } from "react";
import { Icon } from "./ui";
import type { PageName } from "../data/mockData";
import { getInspectionSummary } from "../api/inspections";
import { getMaterialSummary } from "../api/materials";
import { getPurchaseOrderSummary } from "../api/purchaseOrders";
import { getTransferSummary } from "../api/transfers";
import { listNotifications, markAllNotificationsRead, markNotificationRead, type StoredNotification } from "../api/notifications";

type Alert = { key: string; count: number; text: string; page: PageName };

const REFRESH_MS = 60_000;
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** Things that need attention, read live from the summary endpoints. These are not stored notifications:
 * there is no read/unread state, and an item disappears once the underlying records no longer need action. */
async function loadAlerts(signal: AbortSignal): Promise<{ alerts: Alert[]; failed: number; at: Date }> {
  const [materials, orders, inspections, transfers] = await Promise.allSettled([
    getMaterialSummary(signal), getPurchaseOrderSummary(signal), getInspectionSummary(signal), getTransferSummary(signal),
  ]);
  const alerts: Alert[] = [];
  if (materials.status === "fulfilled")
    alerts.push({ key: "low", count: materials.value.low_stock_batches, text: `${plural(materials.value.low_stock_batches, "batch", "batches")} flagged Low stock`, page: "Inventory" });
  if (orders.status === "fulfilled")
    alerts.push({ key: "overdue", count: orders.value.overdue, text: `${plural(orders.value.overdue, "purchase order", "purchase orders")} past the expected delivery date`, page: "Procurement" });
  if (inspections.status === "fulfilled")
    alerts.push({ key: "qi", count: inspections.value.open, text: `${plural(inspections.value.open, "inspection", "inspections")} awaiting a decision`, page: "Quality" });
  if (transfers.status === "fulfilled") {
    const t = transfers.value;
    alerts.push({ key: "approve", count: t.awaiting_approval, text: `${plural(t.awaiting_approval, "transfer", "transfers")} awaiting approval`, page: "Movements" });
    alerts.push({ key: "dispatch", count: t.ready_to_dispatch, text: `${plural(t.ready_to_dispatch, "transfer", "transfers")} ready to dispatch`, page: "Movements" });
    alerts.push({ key: "receive", count: t.in_transit, text: `${plural(t.in_transit, "transfer", "transfers")} in transit, to be received`, page: "Movements" });
  }
  const failed = [materials, orders, inspections, transfers].filter((r) => r.status === "rejected").length;
  return { alerts: alerts.filter((a) => a.count > 0), failed, at: new Date() };
}

const ago = (iso: string) => {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  return minutes < 1 ? "just now" : minutes < 60 ? `${minutes} min ago` : minutes < 1440 ? `${Math.round(minutes / 60)} h ago` : new Date(iso).toLocaleDateString();
};

export function AlertsMenu({ onNavigate }: { onNavigate: (page: PageName) => void }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<{ alerts: Alert[]; failed: number; at: Date } | null>(null);
  const [inbox, setInbox] = useState<{ notifications: StoredNotification[]; unread: number; email_enabled: boolean } | null>(null);
  const [tick, setTick] = useState(0);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    loadAlerts(controller.signal).then(setData).catch(() => {});
    listNotifications(controller.signal).then(setInbox).catch(() => {});
    const id = window.setTimeout(() => setTick((t) => t + 1), REFRESH_MS);
    return () => { controller.abort(); window.clearTimeout(id); };
  }, [tick]);

  const toggle = () => { if (!open) setTick((t) => t + 1); setOpen(!open); };

  const close = useCallback(() => setOpen(false), []);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) close(); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open, close]);

  const total = data?.alerts.reduce((n, a) => n + a.count, 0) ?? 0;
  const unread = inbox?.unread ?? 0;
  const openNote = async (n: StoredNotification) => {
    close();
    if (!n.read_at) await markNotificationRead(n.id).catch(() => {});
    setTick((t) => t + 1);
    if (n.page) onNavigate(n.page as PageName);
  };
  const readAll = async () => { await markAllNotificationsRead().catch(() => {}); setTick((t) => t + 1); };
  return <div className="alerts-menu" ref={root}>
    <button className="icon-button notification-button" aria-label={unread ? `Notifications: ${unread} unread` : total ? `Alerts: ${total} items need attention` : "Notifications"} aria-expanded={open} aria-haspopup="true" title="Notifications and items that need attention" onClick={toggle}>
      <Icon name="bell"/>{unread > 0 ? <b className="alert-count">{unread > 99 ? "99+" : unread}</b> : total > 0 && <b className="alert-count muted">{total > 99 ? "99+" : total}</b>}
    </button>
    {open && <div className="alerts-panel" role="dialog" aria-label="Notifications">
      <div className="alerts-head"><strong>Notifications</strong>{unread > 0 ? <button className="link-button" onClick={readAll}>Mark all read</button> : <small>{inbox ? "All read" : "Loading…"}</small>}</div>
      <div className="notification-list">
        {inbox && inbox.notifications.length === 0 && <p className="alerts-empty">No notifications yet.</p>}
        {inbox?.notifications.map((n) => <button key={n.id} className={`alert-item notification-item${n.read_at ? "" : " unread"}`} onClick={() => openNote(n)}>
          <span><strong>{n.title}</strong>{n.body && <small>{n.body}</small>}</span><small>{ago(n.created_at)}</small>
        </button>)}
      </div>
      <div className="alerts-head"><strong>Needs attention</strong><small>{data ? `Live · checked ${data.at.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}` : "Loading…"}</small></div>
      {data && data.alerts.length === 0 && !data.failed && <p className="alerts-empty">Nothing needs attention right now.</p>}
      {data?.alerts.map((a) => <button key={a.key} className="alert-item" onClick={() => { close(); onNavigate(a.page); }}>
        <span>{a.text}</span><small>{a.page}<Icon name="chevron" size={12}/></small>
      </button>)}
      {data && data.failed > 0 && <p className="alerts-empty" role="alert">{plural(data.failed, "source", "sources")} couldn’t be checked; the list may be incomplete.</p>}
      <p className="alerts-foot">Notifications are kept for your role{inbox?.email_enabled ? " and also emailed when you have an address" : ""}. “Needs attention” is read live from current records.</p>
    </div>}
  </div>;
}

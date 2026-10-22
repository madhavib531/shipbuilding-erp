import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Icon, Input } from "./ui";
import { ApiError } from "../api/client";
import { useDenied } from "../auth";
import type { ReferenceData } from "../api/materials";
import { actOnPurchaseOrder, formatMoney, getPurchaseOrder, type OrderAction, type PurchaseOrder } from "../api/purchaseOrders";
import { PurchaseOrderDialog } from "./PurchaseOrderDialog";
import { GoodsReceiptDialog } from "./GoodsReceiptDialog";

const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

export const orderTone = (status: string) =>
  status === "Received" ? "success" as const
    : status === "Cancelled" ? "danger" as const
      : status === "Partially received" ? "warning" as const
        : status === "Approved" ? "info" as const : "neutral" as const;

const VERB: Record<OrderAction, string> = { approve: "approved", reopen: "reopened as a draft", cancel: "cancelled", close: "closed" };

export function PurchaseOrderDetailDialog({ orderId, refs, refsError, onClose, onChanged }: {
  orderId: number;
  refs: ReferenceData | null;
  refsError: string;
  onClose: () => void;
  onChanged: (message: string) => void;
}) {
  const denied = useDenied();
  const [order, setOrder] = useState<PurchaseOrder | null>(null);
  const [loadError, setLoadError] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [sub, setSub] = useState<"edit" | "receive" | null>(null);

  const load = useCallback((signal?: AbortSignal) =>
    getPurchaseOrder(orderId, signal)
      .then((o) => { setOrder(o); setLoadError(""); })
      .catch((err) => { if (!signal?.aborted) setLoadError(err.message); }), [orderId]);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const act = async (action: OrderAction) => {
    if (!order) return;
    if (action !== "approve" && !reason.trim()) return setError(`A reason is required to ${action === "reopen" ? "reopen" : action} ${order.display_id}.`);
    setBusy(true);
    setError("");
    try {
      const updated = await actOnPurchaseOrder(order.id, action, order.version, reason.trim() || null);
      setOrder(null);
      setReason("");
      await load();
      onChanged(`${updated.display_id} ${VERB[action]}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The request failed.");
      if (err instanceof ApiError && err.status === 409) await load();
    } finally {
      setBusy(false);
    }
  };

  const subDone = async (message: string) => {
    setSub(null);
    setError("");
    await load();
    onChanged(message);
  };

  if (order && sub === "edit") return <PurchaseOrderDialog order={order} refs={refs} refsError={refsError} onClose={() => setSub(null)} onDone={(m) => subDone(m)}/>;
  if (order && sub === "receive") return <GoodsReceiptDialog order={order} refs={refs} refsError={refsError} onClose={() => setSub(null)} onDone={subDone}/>;

  const status = order?.status;
  const full = { gridColumn: "1 / -1" } as const;
  const needsReason = status === "Draft" || status === "Approved" || status === "Partially received";
  return <div className="dialog-layer" role="dialog" aria-modal="true" aria-labelledby="po-detail-title">
    <button className="dialog-scrim" onClick={onClose} aria-label="Close dialog"/>
    <div className="dialog" style={{ width: "min(860px, 100%)" }}>
      <div className="dialog-header">
        <div>
          <p className="eyebrow">{order?.display_id ?? "Purchase order"}</p>
          <h2 id="po-detail-title">{order ? order.supplier.name : "Loading purchase order…"}</h2>
          {order && <p><Badge tone={orderTone(order.status)}>{order.status}</Badge>{order.is_overdue && <> <Badge tone="danger">Overdue</Badge></>}</p>}
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close dialog"><Icon name="close"/></button>
      </div>

      {loadError && <div className="notice" role="alert" style={{ marginTop: 18 }}><Icon name="warning"/>{loadError}</div>}

      {order && <div style={{ padding: "0 22px" }}>
        <div className="material-detail" style={{ marginTop: 18 }}>
          <dl style={{ marginTop: 0 }}>
            <div><dt>Order value</dt><dd>{formatMoney(order.total_value, order.currency)}</dd></div>
            <div><dt>Outstanding value</dt><dd>{formatMoney(order.outstanding_value, order.currency)}</dd></div>
            <div><dt>Expected delivery</dt><dd>{order.expected_delivery_date ?? "Not set"}{order.delivery_yard ? ` · ${order.delivery_yard.name}` : ""}</dd></div>
            <div><dt>Received</dt><dd>{order.received_quantity} of {order.ordered_quantity} units ordered</dd></div>
            <div><dt>Created by</dt><dd>{order.created_by}</dd></div>
            <div><dt>Approved by</dt><dd>{order.approved_by ? `${order.approved_by} · ${when(order.approved_at!)}` : "Not approved"}</dd></div>
            <div><dt>Supplier status</dt><dd>{order.supplier.status}</dd></div>
            {order.notes && <div><dt>Notes</dt><dd>{order.notes}</dd></div>}
          </dl>
        </div>
        <div className="table-scroll" style={{ marginTop: 14 }}><table>
          <thead><tr><th>Line</th><th>Ordered</th><th>Received</th><th>Rejected</th><th>Cancelled</th><th>Outstanding</th><th>Unit price</th><th>Line total</th></tr></thead>
          <tbody>{order.lines.length === 0
            ? <tr><td colSpan={8}>No lines yet — edit the draft to add them.</td></tr>
            : order.lines.map((l) => <tr key={l.id}>
              <td><strong>{l.line_no}. {l.description}</strong><small>{l.category.name}{l.supplier_part_number ? ` · ${l.supplier_part_number}` : ""}</small></td>
              <td>{l.ordered_quantity} {l.unit}</td><td>{l.received_quantity}</td><td>{l.rejected_quantity}</td><td>{l.cancelled_quantity}</td>
              <td><strong>{l.outstanding_quantity}</strong></td>
              <td>{formatMoney(l.unit_price, l.currency)}</td><td>{formatMoney(l.line_total, l.currency)}</td>
            </tr>)}</tbody>
        </table></div>
      </div>}

      {order?.receipts && order.receipts.length > 0 && <div style={{ padding: "14px 22px 0" }}>
        <strong style={{ fontSize: 12 }}>Goods receipts</strong>
        <div className="table-scroll"><table>
          <thead><tr><th>Receipt</th><th>Received at</th><th>Lines</th></tr></thead>
          <tbody>{order.receipts.map((r) => <tr key={r.id}>
            <td><strong className="mono">{r.display_id}</strong><small>{r.delivery_note ?? "No delivery note"} · by {r.received_by}</small></td>
            <td><strong>{r.yard.name}{r.location ? ` · Zone ${r.location.zone}` : ""}</strong><small>{when(r.received_at)}</small></td>
            <td>{r.lines.map((l) => <small key={l.id}>Line {l.purchase_order_line.line_no}: {l.accepted_quantity} accepted{l.destination_material_id ? ` → ${l.destination_material_id}` : ""}{l.rejected_quantity ? ` · ${l.rejected_quantity} rejected (${l.rejection_reason})` : ""}{l.inspection_hold ? ` · ${l.inspection_hold.display_id} ${l.inspection_hold.status.toLowerCase()}` : ""}</small>)}</td>
          </tr>)}</tbody>
        </table></div>
      </div>}

      {needsReason && <div className="form-grid">
        <label style={full}><span>{status === "Draft" ? "Note (optional to approve; required to cancel)" : status === "Approved" ? "Reason (required to reopen or cancel)" : "Reason (required to close short)"}</span>
          <Input name="reason" placeholder="Recorded in the order history" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} disabled={busy}/></label>
      </div>}

      {order?.events && <div className="audit-timeline" aria-label="Order history">
        {order.events.map((e) => <div className="audit-event" key={e.id}>
          <span className="audit-dot"><Icon name="check" size={14}/></span>
          <div><strong>{(e.action[0].toUpperCase() + e.action.slice(1)).replace(/_/g, " ")}{e.from_status && e.from_status !== e.to_status ? ` · ${e.from_status} → ${e.to_status}` : ""}</strong><p>{e.actor}{e.reason ? ` · ${e.reason}` : ""}</p></div>
          <div><small>{when(e.created_at)}</small></div>
        </div>)}
      </div>}

      {error && <div className="notice" role="alert"><Icon name="warning"/>{error}</div>}

      <div className="dialog-actions">
        {status === "Draft" && <>
          <Button type="button" variant="danger" disabled={busy || !!denied("procurement")} title={denied("procurement")} onClick={() => act("cancel")}>Cancel order</Button>
          <Button type="button" variant="secondary" disabled={busy || !!denied("procurement")} title={denied("procurement")} onClick={() => setSub("edit")}>Edit draft</Button>
          <Button type="button" disabled={busy || !!denied("procurement")} title={denied("procurement")} onClick={() => act("approve")}>{busy ? "Saving…" : "Approve"}</Button>
        </>}
        {status === "Approved" && <>
          <Button type="button" variant="danger" disabled={busy || !!denied("procurement")} title={denied("procurement")} onClick={() => act("cancel")}>Cancel order</Button>
          <Button type="button" variant="ghost" disabled={busy || !!denied("procurement")} title={denied("procurement")} onClick={() => act("reopen")}>Reopen as draft</Button>
          <Button type="button" disabled={busy || !!denied("receiving")} title={denied("receiving")} onClick={() => setSub("receive")}>Receive goods</Button>
        </>}
        {status === "Partially received" && <>
          <Button type="button" variant="ghost" disabled={busy || !!denied("procurement")} title={denied("procurement")} onClick={() => act("close")}>Close short</Button>
          <Button type="button" disabled={busy || !!denied("receiving")} title={denied("receiving")} onClick={() => setSub("receive")}>Receive goods</Button>
        </>}
        {(!status || ["Received", "Cancelled", "Closed"].includes(status)) && <Button type="button" variant="secondary" onClick={onClose}>Close</Button>}
      </div>
    </div>
  </div>;
}

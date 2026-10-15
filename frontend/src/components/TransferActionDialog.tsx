import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Icon, Input } from "./ui";
import { ApiError } from "../api/client";
import {
  TRANSFER_STATUS_LABEL,
  approveTransfer,
  cancelTransfer,
  dispatchTransfer,
  getTransfer,
  receiveTransfer,
  rejectTransfer,
  type Transfer,
} from "../api/transfers";

const place = (yard: { name: string }, location: { zone: string; aisle: string } | null) =>
  `${yard.name}${location ? ` · Zone ${location.zone}, aisle ${location.aisle}` : ""}`;

const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

export function TransferActionDialog({ transferId, tone, onClose, onDone }: {
  transferId: number;
  tone: (label: string) => "success" | "warning" | "danger" | "info";
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const [transfer, setTransfer] = useState<Transfer | null>(null);
  const [loadError, setLoadError] = useState("");
  const [reason, setReason] = useState("");
  const [received, setReceived] = useState("");
  const [destination, setDestination] = useState("");
  const [discrepancy, setDiscrepancy] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback((signal?: AbortSignal) =>
    getTransfer(transferId, signal)
      .then((t) => { setTransfer(t); setReceived(String(t.quantity)); setLoadError(""); })
      .catch((err) => { if (!signal?.aborted) setLoadError(err.message); }), [transferId]);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const run = async (action: () => Promise<Transfer>, verb: string) => {
    setBusy(true);
    setError("");
    try {
      const t = await action();
      onDone(`Transfer ${t.display_id} ${verb}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The request failed.");
      if (err instanceof ApiError && err.status === 409) await load();
    } finally {
      setBusy(false);
    }
  };

  const needReason = (fn: (r: string) => Promise<Transfer>, verb: string) => {
    if (!reason.trim()) return setError(`A reason is required to ${verb === "rejected" ? "reject" : "cancel"} a transfer.`);
    run(() => fn(reason.trim()), verb);
  };

  const receive = () => {
    if (!transfer) return;
    const qty = Number(received);
    if (received.trim() === "" || !Number.isInteger(qty) || qty < 0) return setError("Received quantity must be a whole number of 0 or more.");
    if (qty > transfer.quantity) return setError(`Received quantity cannot exceed the dispatched ${transfer.quantity} ${transfer.unit}.`);
    if (qty < transfer.quantity && !discrepancy.trim()) return setError(`Explain the missing ${transfer.quantity - qty} ${transfer.unit} in the discrepancy reason.`);
    run(() => receiveTransfer(transfer.id, {
      received_quantity: qty,
      destination_material_id: destination.trim() || null,
      discrepancy_reason: discrepancy.trim() || null,
    }), "received");
  };

  const status = transfer?.status;
  const full = { gridColumn: "1 / -1" } as const;
  const shortfall = transfer && Number(received) < transfer.quantity;

  return <div className="dialog-layer" role="dialog" aria-modal="true" aria-labelledby="transfer-action-title">
    <button className="dialog-scrim" onClick={onClose} aria-label="Close dialog"/>
    <div className="dialog">
      <div className="dialog-header">
        <div>
          <p className="eyebrow">{transfer?.display_id ?? "Transfer"}</p>
          <h2 id="transfer-action-title">{transfer ? transfer.material.name : "Loading transfer…"}</h2>
          {transfer && <p><Badge tone={tone(TRANSFER_STATUS_LABEL[transfer.status])}>{TRANSFER_STATUS_LABEL[transfer.status]}</Badge></p>}
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close dialog"><Icon name="close"/></button>
      </div>

      {loadError && <div className="notice" role="alert" style={{ marginTop: 18 }}><Icon name="warning"/>{loadError}</div>}

      {transfer && <div style={{ padding: "0 22px" }}>
        <div className="material-detail" style={{ marginTop: 18 }}>
          <dl style={{ marginTop: 0 }}>
            <div><dt>Material</dt><dd>{transfer.material.id} · Batch {transfer.material.batch}</dd></div>
            <div><dt>Quantity</dt><dd>{transfer.quantity} {transfer.unit}</dd></div>
            <div><dt>From</dt><dd>{place(transfer.from_yard, transfer.from_location)}</dd></div>
            <div><dt>To</dt><dd>{place(transfer.to_yard, transfer.to_location)}</dd></div>
            <div><dt>Expected arrival</dt><dd>{transfer.expected_arrival ?? "Not set"}</dd></div>
            <div><dt>Requested by</dt><dd>{transfer.requested_by}</dd></div>
            {transfer.received_quantity !== null && <div><dt>Received</dt><dd>{transfer.received_quantity} {transfer.unit}{transfer.shortage_quantity ? ` (${transfer.shortage_quantity} short)` : ""}</dd></div>}
            {transfer.destination_material_id && <div><dt>Destination batch</dt><dd>{transfer.destination_material_id}</dd></div>}
            {transfer.notes && <div style={full}><dt>Notes</dt><dd>{transfer.notes}</dd></div>}
          </dl>
        </div>
      </div>}

      {(status === "Requested" || status === "Approved") && <div className="form-grid">
        <label style={full}><span>{status === "Requested" ? "Note (required to reject or cancel)" : "Note (required to cancel)"}</span>
          <Input name="reason" placeholder="Reason or note recorded in the history" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} disabled={busy}/></label>
      </div>}

      {status === "Dispatched" && <div className="form-grid">
        <label><span>Received quantity ({transfer!.unit})</span><Input name="received_quantity" type="number" min={0} max={transfer!.quantity} step={1} value={received} onChange={(e) => setReceived(e.target.value)} disabled={busy}/></label>
        <label><span>Destination batch ID</span><Input name="destination_material_id" placeholder={`e.g. ${transfer!.material_id}-${transfer!.to_yard.id}`} value={destination} onChange={(e) => setDestination(e.target.value)} maxLength={50} disabled={busy}/></label>
        <p className="muted-copy" style={full}>Enter an existing batch at {transfer!.to_yard.name} with the same category, batch and unit, or a new ID to create one. Leave it blank only when this transfer moved the whole batch, to keep the ID {transfer!.material_id}.</p>
        {shortfall && <label style={full}><span>Discrepancy reason (required)</span><Input name="discrepancy_reason" placeholder="What happened to the missing quantity?" value={discrepancy} onChange={(e) => setDiscrepancy(e.target.value)} maxLength={1000} disabled={busy}/></label>}
      </div>}

      {transfer && <div className="audit-timeline" aria-label="Transfer history">
        {transfer.events.map((e) => <div className="audit-event" key={e.id}>
          <span className="audit-dot"><Icon name="check" size={14}/></span>
          <div><strong>{e.action[0].toUpperCase() + e.action.slice(1)}{e.quantity !== null ? ` · ${e.quantity} ${transfer.unit}` : ""}</strong><p>{e.actor}{e.reason ? ` · ${e.reason}` : ""}</p></div>
          <div><small>{when(e.created_at)}</small></div>
        </div>)}
      </div>}

      {error && <div className="notice" role="alert"><Icon name="warning"/>{error}</div>}

      <div className="dialog-actions">
        {status === "Requested" && <>
          <Button type="button" variant="danger" disabled={busy} onClick={() => needReason((r) => rejectTransfer(transferId, r), "rejected")}>Reject</Button>
          <Button type="button" variant="ghost" disabled={busy} onClick={() => needReason((r) => cancelTransfer(transferId, r), "cancelled")}>Cancel transfer</Button>
          <Button type="button" disabled={busy} onClick={() => run(() => approveTransfer(transferId, reason.trim() || null), "approved")}>{busy ? "Saving…" : "Approve"}</Button>
        </>}
        {status === "Approved" && <>
          <Button type="button" variant="ghost" disabled={busy} onClick={() => needReason((r) => cancelTransfer(transferId, r), "cancelled")}>Cancel transfer</Button>
          <Button type="button" disabled={busy} onClick={() => run(() => dispatchTransfer(transferId, reason.trim() || null), "dispatched")}>{busy ? "Dispatching…" : "Dispatch"}</Button>
        </>}
        {status === "Dispatched" && <Button type="button" disabled={busy} onClick={receive}>{busy ? "Receiving…" : "Confirm receipt"}</Button>}
        {(!status || ["Received", "Rejected", "Cancelled"].includes(status)) && <Button type="button" variant="secondary" onClick={onClose}>Close</Button>}
      </div>
    </div>
  </div>;
}

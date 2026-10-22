import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Icon, Input, Select } from "./ui";
import { ApiError } from "../api/client";
import {
  REJECTION_DISPOSITIONS,
  getInspection,
  rejectInspection,
  releaseInspection,
  type Inspection,
  type RejectionDisposition,
} from "../api/inspections";

const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

export const inspectionTone = (status: string) =>
  status === "Released" ? "success" as const : status === "Rejected" ? "danger" as const : status === "Open" ? "warning" as const : "info" as const;

export function InspectionDialog({ inspectionId, onClose, onDone }: {
  inspectionId: number;
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const [hold, setHold] = useState<Inspection | null>(null);
  const [loadError, setLoadError] = useState("");
  const [decision, setDecision] = useState<"release" | "reject">("release");
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState("");
  const [disposition, setDisposition] = useState<RejectionDisposition>("Scrap");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback((signal?: AbortSignal) =>
    getInspection(inspectionId, signal)
      .then((h) => {
        setHold(h);
        setQuantity(String(h.outstanding_quantity));
        // Stock held by hand has no supplier delivery to return to.
        setDisposition(h.goods_receipt_line ? "Return to supplier" : "Scrap");
        setLoadError("");
      })
      .catch((err) => { if (!signal?.aborted) setLoadError(err.message); }), [inspectionId]);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const submit = async () => {
    if (!hold) return;
    const qty = Number(quantity);
    if (quantity.trim() === "" || !Number.isInteger(qty) || qty < 1) return setError("Quantity must be a whole number of 1 or more.");
    if (qty > hold.outstanding_quantity) return setError(`Only ${hold.outstanding_quantity} ${hold.material.unit} await a decision.`);
    if (decision === "reject" && !reason.trim()) return setError("A reason is required to reject goods.");
    setBusy(true);
    setError("");
    try {
      const updated = decision === "release"
        ? await releaseInspection(hold.id, hold.version, qty, reason.trim() || null)
        : await rejectInspection(hold.id, hold.version, qty, reason.trim(), disposition);
      onDone(`${updated.display_id}: ${qty} ${hold.material.unit} ${decision === "release" ? "released to stock" : `rejected (${disposition.toLowerCase()})`}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The request failed.");
      if (err instanceof ApiError && err.status === 409) await load();
    } finally {
      setBusy(false);
    }
  };

  const open = hold?.status === "Open";
  const full = { gridColumn: "1 / -1" } as const;
  const source = hold?.goods_receipt_line;

  return <div className="dialog-layer" role="dialog" aria-modal="true" aria-labelledby="inspection-dialog-title">
    <button className="dialog-scrim" onClick={onClose} aria-label="Close dialog"/>
    <div className="dialog">
      <div className="dialog-header">
        <div>
          <p className="eyebrow">{hold?.display_id ?? "Inspection"}</p>
          <h2 id="inspection-dialog-title">{hold ? hold.material.name : "Loading inspection…"}</h2>
          {hold && <p><Badge tone={inspectionTone(hold.status)}>{hold.status}</Badge></p>}
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close dialog"><Icon name="close"/></button>
      </div>

      {loadError && <div className="notice" role="alert" style={{ marginTop: 18 }}><Icon name="warning"/>{loadError}</div>}

      {hold && <div style={{ padding: "0 22px" }}>
        <div className="material-detail" style={{ marginTop: 18 }}>
          <dl style={{ marginTop: 0 }}>
            <div><dt>Batch</dt><dd>{hold.material.id} · Lot {hold.material.batch}</dd></div>
            <div><dt>Location</dt><dd>{hold.material.yard.name}{hold.material.location ? ` · Zone ${hold.material.location.zone}` : ""}</dd></div>
            <div><dt>{source ? "Held on receipt" : "Held from stock"}</dt><dd>{hold.quantity} {hold.material.unit}</dd></div>
            <div><dt>Awaiting decision</dt><dd>{hold.outstanding_quantity} {hold.material.unit}</dd></div>
            <div><dt>Released</dt><dd>{hold.released_quantity} {hold.material.unit}</dd></div>
            <div><dt>Rejected</dt><dd>{hold.rejected_quantity} {hold.material.unit}</dd></div>
            {source ? <>
              <div><dt>Purchase order</dt><dd>{source.receipt.purchase_order.display_id} · line {source.purchase_order_line.line_no} · {source.receipt.purchase_order.supplier.name}</dd></div>
              <div><dt>Goods receipt</dt><dd>{source.receipt.display_id}{source.receipt.delivery_note ? ` · ${source.receipt.delivery_note}` : ""}</dd></div>
            </> : <div><dt>Source</dt><dd>Existing stock, held by {hold.created_by}</dd></div>}
          </dl>
        </div>
      </div>}

      {open && <div className="form-grid">
        <label><span>Decision</span><Select name="decision" value={decision} onChange={(e) => setDecision(e.target.value as "release" | "reject")} disabled={busy}><option value="release">Release to stock</option><option value="reject">Reject</option></Select></label>
        <label><span>Quantity ({hold!.material.unit})</span><Input name="quantity" type="number" min={1} max={hold!.outstanding_quantity} step={1} value={quantity} onChange={(e) => setQuantity(e.target.value)} disabled={busy}/></label>
        {decision === "reject" && <label style={full}><span>Disposition</span><Select name="disposition" value={disposition} onChange={(e) => setDisposition(e.target.value as RejectionDisposition)} disabled={busy}>{(source ? REJECTION_DISPOSITIONS : ["Scrap"]).map((d) => <option key={d}>{d}</option>)}</Select></label>}
        <label style={full}><span>{decision === "reject" ? "Reason (required)" : "Inspection note (optional)"}</span>
          <Input name="reason" placeholder={decision === "reject" ? "What failed inspection?" : "Tests performed, certificate reference…"} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} disabled={busy}/></label>
        <p className="muted-copy" style={full}>{decision === "release"
          ? "Released goods become available for transfers and allocation."
          : !source
            ? "Rejected goods leave stock and are recorded as scrap. This stock was held from inventory, not from a delivery, so it cannot be returned to a supplier."
            : `Rejected goods leave stock and are recorded as ${disposition === "Scrap" ? "scrap" : "returned to the supplier"}. The quantity stays owed on ${source.receipt.purchase_order.display_id} for redelivery, unless the order is closed.`}</p>
      </div>}

      {hold?.events && <div className="audit-timeline" aria-label="Inspection history">
        {hold.events.map((e) => <div className="audit-event" key={e.id}>
          <span className="audit-dot"><Icon name="check" size={14}/></span>
          <div><strong>{e.action[0].toUpperCase() + e.action.slice(1)} · {e.quantity} {hold.material.unit}{e.disposition ? ` · ${e.disposition}` : ""}</strong><p>{e.actor}{e.reason ? ` · ${e.reason}` : ""}</p></div>
          <div><small>{when(e.created_at)}</small></div>
        </div>)}
      </div>}

      {error && <div className="notice" role="alert"><Icon name="warning"/>{error}</div>}

      <div className="dialog-actions">
        {open
          ? <Button type="button" variant={decision === "reject" ? "danger" : "primary"} disabled={busy} onClick={submit}>{busy ? "Saving…" : decision === "reject" ? "Reject goods" : "Release to stock"}</Button>
          : <Button type="button" variant="secondary" onClick={onClose}>Close</Button>}
      </div>
    </div>
  </div>;
}

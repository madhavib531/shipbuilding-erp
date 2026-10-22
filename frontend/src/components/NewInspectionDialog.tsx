import { useEffect, useState, type FormEvent } from "react";
import { Badge, Button, Icon, Input } from "./ui";
import { ApiError } from "../api/client";
import { createInspection } from "../api/inspections";
import { getMaterial, type ApiMaterial } from "../api/materials";

type Lookup = { phase: "idle" | "loading" } | { phase: "found"; material: ApiMaterial } | { phase: "error"; message: string };

/** Holds part of a batch's available stock for inspection. */
export function NewInspectionDialog({ onClose, onDone, initialBatchId = "" }: { onClose: () => void; onDone: (message: string) => void; initialBatchId?: string }) {
  const [batchId, setBatchId] = useState(initialBatchId);
  const [lookup, setLookup] = useState<Lookup>({ phase: "idle" });
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Looks the batch up as it is typed, so its available stock is shown before anything is held.
  useEffect(() => {
    const id = batchId.trim();
    if (!id) { setLookup({ phase: "idle" }); return; }
    const controller = new AbortController();
    setLookup({ phase: "loading" });
    const timer = window.setTimeout(() => {
      getMaterial(id, controller.signal)
        .then((material) => setLookup({ phase: "found", material }))
        .catch((err) => {
          if (controller.signal.aborted) return;
          setLookup({ phase: "error", message: err instanceof ApiError && err.status === 404 ? `No batch with ID ${id}.` : err.message });
        });
    }, 300);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [batchId]);

  const material = lookup.phase === "found" ? lookup.material : null;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!material) return setError("Enter the ID of an existing batch.");
    const qty = Number(quantity);
    if (quantity.trim() === "" || !Number.isInteger(qty) || qty < 1) return setError("Quantity must be a whole number of 1 or more.");
    if (qty > material.available) return setError(`Only ${material.available} ${material.unit} of ${material.id} are available to hold.`);
    if (!reason.trim()) return setError("A reason is required; it is recorded in the stock ledger.");
    setBusy(true);
    setError("");
    try {
      const hold = await createInspection(material.id, qty, reason.trim());
      onDone(`${hold.display_id}: ${qty} ${material.unit} of ${material.id} held for inspection`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The request failed.");
      setBusy(false);
    }
  };

  const full = { gridColumn: "1 / -1" } as const;
  return <div className="dialog-layer" role="dialog" aria-modal="true" aria-labelledby="new-inspection-title">
    <button className="dialog-scrim" onClick={onClose} aria-label="Close dialog"/>
    <form className="dialog" onSubmit={submit} noValidate>
      <div className="dialog-header">
        <div>
          <p className="eyebrow">New inspection</p>
          <h2 id="new-inspection-title">Hold stock for inspection</h2>
          <p>Held stock stays on hand but cannot be transferred or allocated until it is released or scrapped.</p>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close dialog"><Icon name="close"/></button>
      </div>

      <div className="form-grid">
        <label style={full}><span>Batch ID</span>
          <Input name="batch" placeholder="e.g. PO-00001-1" value={batchId} onChange={(e) => setBatchId(e.target.value)} disabled={busy} autoFocus/></label>
        <div style={full} aria-live="polite">
          {lookup.phase === "loading" && <p className="muted-copy">Looking up batch…</p>}
          {lookup.phase === "error" && <p className="muted-copy" role="alert">{lookup.message}</p>}
          {material && <div className="material-detail" style={{ marginTop: 0 }}>
            <h3>{material.name} <Badge tone={material.status === "Inspection" ? "warning" : "neutral"}>{material.status}</Badge></h3>
            <p>{material.id} · Lot {material.batch} · {material.yard.name}{material.location ? ` · Zone ${material.location.zone}` : ""}</p>
            <dl>
              <div><dt>On hand</dt><dd>{material.quantity} {material.unit}</dd></div>
              <div><dt>Available to hold</dt><dd>{material.available} {material.unit}</dd></div>
              <div><dt>Reserved</dt><dd>{material.reserved} {material.unit}</dd></div>
              <div><dt>Already on hold</dt><dd>{material.held_quantity} {material.unit}</dd></div>
            </dl>
          </div>}
        </div>
        <label><span>Quantity{material ? ` (${material.unit})` : ""}</span>
          <Input name="quantity" type="number" min={1} max={material?.available} step={1} value={quantity} onChange={(e) => setQuantity(e.target.value)} disabled={busy || !material || material.available === 0}/></label>
        <label style={full}><span>Reason (required)</span>
          <Input name="reason" placeholder="Why does this stock need inspecting?" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} disabled={busy}/></label>
        {material && material.available === 0 && <p className="muted-copy" style={full}>This batch has no available stock to hold.</p>}
      </div>

      {error && <div className="notice" role="alert"><Icon name="warning"/>{error}</div>}

      <div className="dialog-actions">
        <Button type="button" variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button type="submit" disabled={busy || !material || material.available === 0}>{busy ? "Holding…" : "Hold for inspection"}</Button>
      </div>
    </form>
  </div>;
}

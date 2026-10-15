import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Button, Icon, Input, Select } from "./ui";
import { listMaterials, type ApiMaterial, type ReferenceData } from "../api/materials";
import { newIdempotencyKey } from "../api/transfers";
import { postGoodsReceipt, type PurchaseOrder, type ReceiptLineInput } from "../api/purchaseOrders";

type LineForm = { accepted: string; rejected: string; reason: string; mode: "new" | "existing"; newId: string; batch: string; existingId: string; hold: boolean };

const count = (value: string) => (value.trim() === "" ? 0 : Number(value));

export function GoodsReceiptDialog({ order, refs, refsError, onClose, onDone }: {
  order: PurchaseOrder;
  refs: ReferenceData | null;
  refsError: string;
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  // One key per dialog: a retry after a lost response replays this receipt instead of adding stock twice.
  const [idempotencyKey] = useState(newIdempotencyKey);
  const open = useMemo(() => order.lines.filter((l) => l.outstanding_quantity > 0), [order]);
  const [yardId, setYardId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [deliveryNote, setDeliveryNote] = useState("");
  const [notes, setNotes] = useState("");
  const [forms, setForms] = useState<Record<number, LineForm>>(() => Object.fromEntries(open.map((l) => [l.id, {
    accepted: "", rejected: "", reason: "", mode: "new", newId: `${order.display_id}-${l.line_no}`, batch: "", existingId: "", hold: false,
  }])));
  const [candidates, setCandidates] = useState<ApiMaterial[]>([]);
  const [candidatesError, setCandidatesError] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Existing batches this delivery could go into, mirroring the server's compatibility checks.
  useEffect(() => {
    setCandidates([]);
    if (!yardId) return;
    const controller = new AbortController();
    const categories = [...new Set(open.map((l) => l.category.id))];
    Promise.all(categories.map((category) => listMaterials({ skip: 0, limit: 1000, category, yard: yardId }, controller.signal)))
      .then((pages) => { setCandidates(pages.flatMap((p) => p.materials)); setCandidatesError(""); })
      .catch((err) => { if (!controller.signal.aborted) setCandidatesError(`Existing batches could not be loaded: ${err.message}`); });
    return () => controller.abort();
  }, [yardId, open]);

  const compatible = (line: PurchaseOrder["lines"][number]) => candidates.filter((m) =>
    m.category_id === line.category.id && m.unit === line.unit && m.status !== "Inspection" && (!locationId || m.location_id === locationId));
  const set = (id: number, patch: Partial<LineForm>) => setForms((f) => ({ ...f, [id]: { ...f[id], ...patch } }));
  const locations = refs?.locations.filter((l) => l.yard_id === yardId) ?? [];

  const build = (): ReceiptLineInput[] | string => {
    if (!yardId) return "Select the receiving yard.";
    const out: ReceiptLineInput[] = [];
    const destinations = new Set<string>();
    for (const line of open) {
      const f = forms[line.id];
      const accepted = count(f.accepted), rejected = count(f.rejected);
      if (!accepted && !rejected) continue;
      const n = `Line ${line.line_no}`;
      if (![accepted, rejected].every((q) => Number.isInteger(q) && q >= 0)) return `${n}: quantities must be whole numbers of 0 or more.`;
      if (accepted + rejected > line.outstanding_quantity) return `${n}: only ${line.outstanding_quantity} ${line.unit} are outstanding; over-delivery is not accepted.`;
      if (rejected && !f.reason.trim()) return `${n}: give a reason for the rejected quantity.`;
      let destination: string | null = null;
      let batch: string | null = null;
      if (accepted) {
        if (f.mode === "new" || f.hold) {
          if (!f.newId.trim() || !f.batch.trim()) return `${n}: a new batch needs an ID and a batch (lot) number.`;
          destination = f.newId.trim();
          batch = f.batch.trim();
        } else {
          if (!f.existingId) return `${n}: choose the existing batch to receive into.`;
          destination = f.existingId;
        }
        if (destinations.has(destination)) return `${n}: batch ${destination} is already used by another line; use one batch per line.`;
        destinations.add(destination);
      }
      out.push({ purchase_order_line_id: line.id, accepted_quantity: accepted, rejected_quantity: rejected, rejection_reason: rejected ? f.reason.trim() : null, destination_material_id: destination, batch, hold_for_inspection: Boolean(accepted) && f.hold });
    }
    return out.length ? out : "Enter an accepted or rejected quantity on at least one line.";
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const lines = build();
    if (typeof lines === "string") return setError(lines);
    setBusy(true);
    setError("");
    try {
      const { receipt } = await postGoodsReceipt(order.id, order.version, {
        yard_id: yardId, location_id: locationId || null, delivery_note: deliveryNote.trim() || null, notes: notes.trim() || null, lines,
      }, idempotencyKey);
      const held = receipt.lines.filter((l) => l.inspection_hold).length;
      onDone(`${receipt.display_id} posted against ${order.display_id}${held ? ` · ${held} line${held === 1 ? "" : "s"} held for inspection` : ""}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The request failed.");
    } finally {
      setBusy(false);
    }
  };

  const full = { gridColumn: "1 / -1" } as const;
  return <div className="dialog-layer" role="dialog" aria-modal="true" aria-labelledby="receipt-dialog-title">
    <button className="dialog-scrim" onClick={onClose} aria-label="Close dialog"/>
    <form className="dialog" style={{ width: "min(1040px, 100%)" }} onSubmit={submit} noValidate>
      <div className="dialog-header">
        <div>
          <p className="eyebrow">{order.display_id} · {order.supplier.name}</p>
          <h2 id="receipt-dialog-title">Receive goods</h2>
          <p>Accepted goods enter stock now, or go on inspection hold in a new batch. Rejected goods never enter stock and stay owed by the supplier.</p>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close dialog"><Icon name="close"/></button>
      </div>
      <div className="form-grid">
        <label><span>Receiving yard</span><Select name="yard_id" value={yardId} onChange={(e) => { setYardId(e.target.value); setLocationId(""); }} disabled={busy || !refs}><option value="">Select yard</option>{refs?.yards.map((y) => <option key={y.id} value={y.id}>{y.name}</option>)}</Select></label>
        <label><span>Storage location</span><Select name="location_id" value={locationId} onChange={(e) => setLocationId(e.target.value)} disabled={busy || !yardId}><option value="">No specific location</option>{locations.map((l) => <option key={l.id} value={l.id}>Zone {l.zone} · Aisle {l.aisle}{l.bin ? ` · Bin ${l.bin}` : ""}</option>)}</Select></label>
        <label><span>Delivery note</span><Input name="delivery_note" placeholder="Supplier delivery note number" value={deliveryNote} onChange={(e) => setDeliveryNote(e.target.value)} maxLength={100} disabled={busy}/></label>
        <label><span>Notes</span><Input name="notes" placeholder="Optional" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={2000} disabled={busy}/></label>
        <div style={full} className="table-scroll"><table>
          <thead><tr><th>Line</th><th>Outstanding</th><th>Accepted</th><th>Rejected</th><th>Destination batch</th><th>Inspection</th></tr></thead>
          <tbody>{open.map((line) => {
            const f = forms[line.id];
            const options = compatible(line);
            return <tr key={line.id}>
              <td><strong>{line.line_no}. {line.description}</strong><small>{line.category.name}{line.supplier_part_number ? ` · ${line.supplier_part_number}` : ""}</small></td>
              <td><strong>{line.outstanding_quantity} {line.unit}</strong><small>{line.received_quantity} received · {line.rejected_quantity} rejected</small></td>
              <td><Input aria-label={`Line ${line.line_no} accepted`} type="number" min={0} max={line.outstanding_quantity} step={1} placeholder="0" value={f.accepted} onChange={(e) => set(line.id, { accepted: e.target.value })} disabled={busy}/></td>
              <td>
                <Input aria-label={`Line ${line.line_no} rejected`} type="number" min={0} max={line.outstanding_quantity} step={1} placeholder="0" value={f.rejected} onChange={(e) => set(line.id, { rejected: e.target.value })} disabled={busy}/>
                {count(f.rejected) > 0 && <Input aria-label={`Line ${line.line_no} rejection reason`} placeholder="Reason (required)" value={f.reason} onChange={(e) => set(line.id, { reason: e.target.value })} maxLength={1000} disabled={busy}/>}
              </td>
              <td>
                <Select aria-label={`Line ${line.line_no} destination type`} value={f.hold ? "new" : f.mode} onChange={(e) => set(line.id, { mode: e.target.value as LineForm["mode"] })} disabled={busy || f.hold}>
                  <option value="new">New batch</option>
                  <option value="existing" disabled={!options.length}>Existing batch{options.length ? "" : yardId ? " (none compatible)" : " (select a yard)"}</option>
                </Select>
                {f.mode === "existing" && !f.hold
                  ? <Select aria-label={`Line ${line.line_no} existing batch`} value={f.existingId} onChange={(e) => set(line.id, { existingId: e.target.value })} disabled={busy}><option value="">Select batch</option>{options.map((m) => <option key={m.id} value={m.id}>{m.id} · lot {m.batch} · {m.quantity} {m.unit}</option>)}</Select>
                  : <><Input aria-label={`Line ${line.line_no} new batch ID`} placeholder="New batch ID" value={f.newId} onChange={(e) => set(line.id, { newId: e.target.value })} maxLength={50} disabled={busy}/><Input aria-label={`Line ${line.line_no} batch number`} placeholder="Batch / lot number" value={f.batch} onChange={(e) => set(line.id, { batch: e.target.value })} maxLength={50} disabled={busy}/></>}
              </td>
              <td><label className="toggle-row" style={{ padding: 8 }}><span><strong>Hold</strong><small>Inspect first</small></span><input type="checkbox" aria-label={`Line ${line.line_no} hold for inspection`} checked={f.hold} onChange={(e) => set(line.id, { hold: e.target.checked })} disabled={busy}/></label></td>
            </tr>;
          })}</tbody>
        </table></div>
      </div>
      {(error || candidatesError || refsError) && <div className="notice" role="alert"><Icon name="warning"/>{error || candidatesError || refsError}</div>}
      <div className="dialog-actions">
        <Button type="button" variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button type="submit" disabled={busy || !refs || !open.length}>{busy ? "Posting…" : "Post receipt"}</Button>
      </div>
    </form>
  </div>;
}

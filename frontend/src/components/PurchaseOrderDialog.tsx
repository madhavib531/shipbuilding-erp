import { useEffect, useState, type FormEvent } from "react";
import { Button, Icon, Input, Select } from "./ui";
import type { ReferenceData } from "../api/materials";
import { newIdempotencyKey } from "../api/transfers";
import { ORDERABLE_SUPPLIER_STATUSES, listSuppliers, type Supplier } from "../api/suppliers";
import { createPurchaseOrder, updatePurchaseOrder, type LineInput, type OrderInput, type PurchaseOrder } from "../api/purchaseOrders";

type LineForm = { category_id: string; description: string; unit: string; supplier_part_number: string; ordered_quantity: string; unit_price: string };

const emptyLine = (): LineForm => ({ category_id: "", description: "", unit: "", supplier_part_number: "", ordered_quantity: "", unit_price: "" });
const PRICE = /^\d{1,10}(\.\d{1,4})?$/;

/** Comparable form of a line, so an unchanged draft is not rewritten. */
const lineKey = (l: LineInput) => JSON.stringify([l.category_id, l.description, l.unit, l.supplier_part_number, l.ordered_quantity, Number(l.unit_price).toFixed(4), l.currency]);

export function PurchaseOrderDialog({ order, refs, refsError, onClose, onDone }: {
  order?: PurchaseOrder;
  refs: ReferenceData | null;
  refsError: string;
  onClose: () => void;
  onDone: (message: string, orderId: number) => void;
}) {
  const editing = Boolean(order);
  // One key per dialog: retrying after a lost response replays the same order instead of creating two.
  const [idempotencyKey] = useState(newIdempotencyKey);
  const [suppliers, setSuppliers] = useState<Supplier[] | null>(null);
  const [suppliersError, setSuppliersError] = useState("");
  const [supplierId, setSupplierId] = useState(order?.supplier.id ?? "");
  const [delivery, setDelivery] = useState(order?.expected_delivery_date ?? "");
  const [deliveryYard, setDeliveryYard] = useState(order?.delivery_yard?.id ?? "");
  const [notes, setNotes] = useState(order?.notes ?? "");
  const [currency, setCurrency] = useState(order?.currency ?? "INR");
  const [lines, setLines] = useState<LineForm[]>(() => order?.lines.length
    ? order.lines.map((l) => ({ category_id: l.category.id, description: l.description, unit: l.unit, supplier_part_number: l.supplier_part_number ?? "", ordered_quantity: String(l.ordered_quantity), unit_price: String(Number(l.unit_price)) }))
    : [emptyLine()]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    listSuppliers({ skip: 0, limit: 200 }, controller.signal)
      .then(({ suppliers: all }) => setSuppliers(all))
      .catch((err) => { if (!controller.signal.aborted) setSuppliersError(`Suppliers could not be loaded: ${err.message}`); });
    return () => controller.abort();
  }, []);

  const orderable = suppliers?.filter((s) => ORDERABLE_SUPPLIER_STATUSES.includes(s.status) || s.id === order?.supplier.id) ?? [];
  const setLine = (i: number, key: keyof LineForm, value: string) => setLines((ls) => ls.map((l, j) => (j === i ? { ...l, [key]: value } : l)));

  const toInput = (): OrderInput | string => {
    if (!supplierId) return "Select a supplier.";
    const used = lines.filter((l) => Object.values(l).some((v) => v.trim()));
    const cur = currency.trim().toUpperCase();
    if (used.length && !/^[A-Z]{3}$/.test(cur)) return "Currency must be a three-letter code such as USD or EUR.";
    const out: LineInput[] = [];
    for (const [i, l] of used.entries()) {
      const n = i + 1;
      if (!l.category_id || !l.description.trim() || !l.unit.trim()) return `Line ${n}: category, description and unit are required.`;
      const qty = Number(l.ordered_quantity);
      if (!Number.isInteger(qty) || qty < 1) return `Line ${n}: quantity must be a whole number of 1 or more.`;
      if (!PRICE.test(l.unit_price.trim())) return `Line ${n}: unit price must be 0 or more with at most 4 decimal places.`;
      out.push({ category_id: l.category_id, description: l.description.trim(), unit: l.unit.trim(), supplier_part_number: l.supplier_part_number.trim() || null, ordered_quantity: qty, unit_price: l.unit_price.trim(), currency: cur });
    }
    return { supplier_id: supplierId, expected_delivery_date: delivery || null, delivery_yard_id: deliveryYard || null, notes: notes.trim() || null, lines: out };
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const input = toInput();
    if (typeof input === "string") return setError(input);
    setBusy(true);
    setError("");
    try {
      if (order) {
        const changes: Partial<OrderInput> = {};
        if (input.supplier_id !== order.supplier.id) changes.supplier_id = input.supplier_id;
        if (input.expected_delivery_date !== order.expected_delivery_date) changes.expected_delivery_date = input.expected_delivery_date;
        if (input.delivery_yard_id !== (order.delivery_yard?.id ?? null)) changes.delivery_yard_id = input.delivery_yard_id;
        if (input.notes !== order.notes) changes.notes = input.notes;
        const before = order.lines.map((l) => lineKey({ category_id: l.category.id, description: l.description, unit: l.unit, supplier_part_number: l.supplier_part_number, ordered_quantity: l.ordered_quantity, unit_price: l.unit_price, currency: l.currency }));
        if (JSON.stringify(before) !== JSON.stringify(input.lines.map(lineKey))) changes.lines = input.lines;
        if (Object.keys(changes).length === 0) return onClose();
        const saved = await updatePurchaseOrder(order.id, order.version, changes);
        onDone(`${saved.display_id} updated`, saved.id);
      } else {
        const created = await createPurchaseOrder(input, idempotencyKey);
        onDone(`${created.display_id} created as a draft`, created.id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "The request failed.");
    } finally {
      setBusy(false);
    }
  };

  const disabled = busy || !refs || !suppliers;
  const full = { gridColumn: "1 / -1" } as const;
  return <div className="dialog-layer" role="dialog" aria-modal="true" aria-labelledby="po-dialog-title">
    <button className="dialog-scrim" onClick={onClose} aria-label="Close dialog"/>
    <form className="dialog" style={{ width: "min(960px, 100%)" }} onSubmit={submit} noValidate>
      <div className="dialog-header">
        <div>
          <p className="eyebrow">{editing ? order!.display_id : "Supply chain"}</p>
          <h2 id="po-dialog-title">{editing ? "Edit draft purchase order" : "New purchase order"}</h2>
          <p>Saved as a draft. Approval needs at least one line and an expected delivery date.</p>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close dialog"><Icon name="close"/></button>
      </div>
      <div className="form-grid">
        <label><span>Supplier</span><Select name="supplier_id" value={supplierId} onChange={(e) => setSupplierId(e.target.value)} disabled={disabled}>
          <option value="">{suppliers && !orderable.length ? "No orderable suppliers — add one first" : "Select supplier"}</option>
          {orderable.map((s) => <option key={s.id} value={s.id}>{s.name} · {s.status}</option>)}
        </Select></label>
        <label><span>Expected delivery</span><Input name="expected_delivery_date" type="date" value={delivery} onChange={(e) => setDelivery(e.target.value)} disabled={disabled}/></label>
        <label><span>Deliver to yard</span><Select name="delivery_yard_id" value={deliveryYard} onChange={(e) => setDeliveryYard(e.target.value)} disabled={disabled}><option value="">Not set</option>{refs?.yards.map((y) => <option key={y.id} value={y.id}>{y.name}</option>)}</Select></label>
        <label><span>Currency (all lines)</span><Input name="currency" placeholder="e.g. USD" value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} maxLength={3} disabled={disabled}/></label>
        <label><span>Notes</span><Input name="notes" placeholder="Optional" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={2000} disabled={disabled}/></label>
        <div style={full} className="table-scroll"><table>
          <thead><tr><th>#</th><th>Category</th><th>Description</th><th>Unit</th><th>Supplier part no.</th><th>Quantity</th><th>Unit price</th><th aria-label="Remove"/></tr></thead>
          <tbody>{lines.map((l, i) => <tr key={i}>
            <td>{i + 1}</td>
            <td><Select aria-label={`Line ${i + 1} category`} value={l.category_id} onChange={(e) => setLine(i, "category_id", e.target.value)} disabled={disabled}><option value="">Category</option>{refs?.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></td>
            <td><Input aria-label={`Line ${i + 1} description`} placeholder="e.g. AH36 plate 12mm" value={l.description} onChange={(e) => setLine(i, "description", e.target.value)} maxLength={200} disabled={disabled}/></td>
            <td><Input aria-label={`Line ${i + 1} unit`} placeholder="sheets" value={l.unit} onChange={(e) => setLine(i, "unit", e.target.value)} maxLength={20} disabled={disabled}/></td>
            <td><Input aria-label={`Line ${i + 1} supplier part number`} placeholder="Optional" value={l.supplier_part_number} onChange={(e) => setLine(i, "supplier_part_number", e.target.value)} maxLength={100} disabled={disabled}/></td>
            <td><Input aria-label={`Line ${i + 1} quantity`} type="number" min={1} step={1} value={l.ordered_quantity} onChange={(e) => setLine(i, "ordered_quantity", e.target.value)} disabled={disabled}/></td>
            <td><Input aria-label={`Line ${i + 1} unit price`} inputMode="decimal" placeholder="0.00" value={l.unit_price} onChange={(e) => setLine(i, "unit_price", e.target.value)} disabled={disabled}/></td>
            <td><button type="button" className="icon-button" aria-label={`Remove line ${i + 1}`} onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))} disabled={disabled}><Icon name="close"/></button></td>
          </tr>)}</tbody>
        </table></div>
        <div style={full}><Button type="button" variant="secondary" icon="plus" onClick={() => setLines((ls) => [...ls, emptyLine()])} disabled={disabled || lines.length >= 200}>Add line</Button></div>
      </div>
      {(error || suppliersError || refsError) && <div className="notice" role="alert"><Icon name="warning"/>{error || suppliersError || refsError}</div>}
      <div className="dialog-actions">
        <Button type="button" variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button type="submit" disabled={disabled}>{busy ? "Saving…" : editing ? "Save draft" : "Create draft"}</Button>
      </div>
    </form>
  </div>;
}

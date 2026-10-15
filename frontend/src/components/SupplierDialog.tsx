import { useState, type FormEvent } from "react";
import { Button, Icon, Input, Select } from "./ui";
import { SUPPLIER_STATUSES, createSupplier, updateSupplier, type Supplier, type SupplierInput, type SupplierStatus } from "../api/suppliers";

type FormState = Record<"id" | "name" | "contact_person" | "contact_email" | "contact_phone" | "address" | "country" | "notes", string> & { status: SupplierStatus };

const fromSupplier = (s?: Supplier): FormState => ({
  id: s?.id ?? "", name: s?.name ?? "", contact_person: s?.contact_person ?? "", contact_email: s?.contact_email ?? "",
  contact_phone: s?.contact_phone ?? "", address: s?.address ?? "", country: s?.country ?? "", notes: s?.notes ?? "",
  status: s?.status ?? "Approved",
});

const toInput = (f: FormState): SupplierInput => ({
  name: f.name.trim(), contact_person: f.contact_person.trim() || null, contact_email: f.contact_email.trim() || null,
  contact_phone: f.contact_phone.trim() || null, address: f.address.trim() || null, country: f.country.trim() || null,
  notes: f.notes.trim() || null, status: f.status,
});

export function SupplierDialog({ supplier, onClose, onDone }: { supplier?: Supplier; onClose: () => void; onDone: (message: string) => void }) {
  const editing = Boolean(supplier);
  const [form, setForm] = useState<FormState>(() => fromSupplier(supplier));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (key: keyof FormState, value: string) => setForm((f) => ({ ...f, [key]: value }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!editing && !form.id.trim()) return setError("Supplier ID is required.");
    if (!form.name.trim()) return setError("Name is required.");
    if (form.contact_email.trim() && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.contact_email.trim())) return setError("Enter a valid contact email or leave it blank.");
    const input = toInput(form);
    setBusy(true);
    setError("");
    try {
      if (supplier) {
        const original = toInput(fromSupplier(supplier));
        const changes = Object.fromEntries(Object.entries(input).filter(([k, v]) => original[k as keyof SupplierInput] !== v));
        if (Object.keys(changes).length === 0) return onClose();
        await updateSupplier(supplier.id, changes);
        onDone(`Supplier ${supplier.id} updated`);
      } else {
        const created = await createSupplier({ id: form.id.trim(), ...input });
        onDone(`Supplier ${created.id} added`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "The request failed.");
    } finally {
      setBusy(false);
    }
  };

  const full = { gridColumn: "1 / -1" } as const;
  return <div className="dialog-layer" role="dialog" aria-modal="true" aria-labelledby="supplier-dialog-title">
    <button className="dialog-scrim" onClick={onClose} aria-label="Close dialog"/>
    <form className="dialog" onSubmit={submit} noValidate>
      <div className="dialog-header">
        <div>
          <p className="eyebrow">{editing ? `Supplier ${supplier!.id}` : "Supplier directory"}</p>
          <h2 id="supplier-dialog-title">{editing ? "Edit supplier" : "Add supplier"}</h2>
          <p>Approved, Conditional and Probation suppliers can receive new purchase orders; Inactive and Blocked cannot.</p>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close dialog"><Icon name="close"/></button>
      </div>
      <div className="form-grid">
        {!editing && <label><span>Supplier ID</span><Input name="id" placeholder="e.g. SUP-NMS" value={form.id} onChange={(e) => set("id", e.target.value)} maxLength={50} disabled={busy}/></label>}
        <label><span>Name</span><Input name="name" placeholder="e.g. Nordic Marine Steel" value={form.name} onChange={(e) => set("name", e.target.value)} maxLength={150} disabled={busy}/></label>
        <label><span>Status</span><Select name="status" value={form.status} onChange={(e) => set("status", e.target.value)} disabled={busy}>{SUPPLIER_STATUSES.map((s) => <option key={s}>{s}</option>)}</Select></label>
        <label><span>Country</span><Input name="country" value={form.country} onChange={(e) => set("country", e.target.value)} maxLength={50} disabled={busy}/></label>
        <label><span>Contact person</span><Input name="contact_person" value={form.contact_person} onChange={(e) => set("contact_person", e.target.value)} maxLength={100} disabled={busy}/></label>
        <label><span>Contact email</span><Input name="contact_email" type="email" value={form.contact_email} onChange={(e) => set("contact_email", e.target.value)} maxLength={100} disabled={busy}/></label>
        <label><span>Contact phone</span><Input name="contact_phone" value={form.contact_phone} onChange={(e) => set("contact_phone", e.target.value)} maxLength={20} disabled={busy}/></label>
        <label style={full}><span>Address</span><Input name="address" value={form.address} onChange={(e) => set("address", e.target.value)} maxLength={300} disabled={busy}/></label>
        <label style={full}><span>Notes</span><Input name="notes" value={form.notes} onChange={(e) => set("notes", e.target.value)} maxLength={500} disabled={busy}/></label>
      </div>
      {error && <div className="notice" role="alert"><Icon name="warning"/>{error}</div>}
      <div className="dialog-actions">
        <Button type="button" variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button type="submit" disabled={busy}>{busy ? "Saving…" : editing ? "Save changes" : "Add supplier"}</Button>
      </div>
    </form>
  </div>;
}

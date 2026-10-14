import { useMemo, useState, type FormEvent } from "react";
import { Button, Icon, Input, Select } from "./ui";
import {
  MATERIAL_STATUSES,
  createMaterial,
  deleteMaterial,
  updateMaterial,
  type ApiMaterial,
  type MaterialInput,
  type MaterialStatus,
  type ReferenceData,
} from "../api/materials";

type FormState = {
  id: string; name: string; category_id: string; batch: string; unit: string; status: MaterialStatus;
  quantity: string; available: string; reserved: string; yard_id: string; location_id: string; ship_id: string;
};

const fromMaterial = (m?: ApiMaterial): FormState => ({
  id: m?.id ?? "", name: m?.name ?? "", category_id: m?.category_id ?? "", batch: m?.batch ?? "",
  unit: m?.unit ?? "", status: m?.status ?? "Healthy",
  quantity: m ? String(m.quantity) : "", available: m ? String(m.available) : "", reserved: m ? String(m.reserved) : "0",
  yard_id: m?.yard_id ?? "", location_id: m?.location_id ?? "", ship_id: m?.ship_id ?? "",
});

function toInput(form: FormState): MaterialInput | string {
  for (const [key, label] of [["name", "Name"], ["category_id", "Category"], ["batch", "Batch"], ["unit", "Unit"], ["yard_id", "Yard"]] as const) {
    if (!form[key].trim()) return `${label} is required.`;
  }
  const nums = { quantity: Number(form.quantity), available: Number(form.available), reserved: Number(form.reserved) };
  for (const [key, value] of Object.entries(nums)) {
    if (form[key as keyof typeof nums].trim() === "" || !Number.isInteger(value) || value < 0) return `${key[0].toUpperCase()}${key.slice(1)} must be a whole number of 0 or more.`;
  }
  if (nums.available + nums.reserved > nums.quantity) return `Available (${nums.available}) + reserved (${nums.reserved}) cannot exceed quantity (${nums.quantity}).`;
  return {
    name: form.name.trim(), category_id: form.category_id, batch: form.batch.trim(), unit: form.unit.trim(), status: form.status,
    ...nums, yard_id: form.yard_id, location_id: form.location_id || null, ship_id: form.ship_id || null,
  };
}

export function MaterialDialog({ material, refs, refsError, onClose, onDone }: {
  material?: ApiMaterial;
  refs: ReferenceData | null;
  refsError: string;
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const editing = Boolean(material);
  const [form, setForm] = useState<FormState>(() => fromMaterial(material));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const locations = useMemo(() => refs?.locations.filter((l) => l.yard_id === form.yard_id) ?? [], [refs, form.yard_id]);
  const ships = useMemo(() => refs?.ships.filter((s) => s.yard_id === form.yard_id) ?? [], [refs, form.yard_id]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((f) => ({ ...f, [key]: value }));
  const setYard = (yardId: string) => setForm((f) => ({
    ...f,
    yard_id: yardId,
    location_id: refs?.locations.some((l) => l.id === f.location_id && l.yard_id === yardId) ? f.location_id : "",
    ship_id: refs?.ships.some((s) => s.id === f.ship_id && s.yard_id === yardId) ? f.ship_id : "",
  }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!editing && !form.id.trim()) return setError("Material ID is required.");
    const input = toInput(form);
    if (typeof input === "string") return setError(input);
    setBusy(true);
    setError("");
    try {
      if (material) {
        const original = toInput(fromMaterial(material)) as MaterialInput;
        const changes = Object.fromEntries(Object.entries(input).filter(([k, v]) => original[k as keyof MaterialInput] !== v));
        if (Object.keys(changes).length === 0) return onClose();
        await updateMaterial(material.id, changes);
        onDone(`Material ${material.id} updated`);
      } else {
        const created = await createMaterial({ id: form.id.trim(), ...input });
        onDone(`Material ${created.id} created`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "The request failed.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!material || !window.confirm(`Delete material ${material.id}? This cannot be undone.`)) return;
    setBusy(true);
    setError("");
    try {
      await deleteMaterial(material.id);
      onDone(`Material ${material.id} deleted`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The request failed.");
    } finally {
      setBusy(false);
    }
  };

  const formDisabled = busy || !refs;

  return <div className="dialog-layer" role="dialog" aria-modal="true" aria-labelledby="material-dialog-title">
    <button className="dialog-scrim" onClick={onClose} aria-label="Close dialog"/>
    <form className="dialog" onSubmit={submit} noValidate>
      <div className="dialog-header">
        <div>
          <p className="eyebrow">{editing ? `Material ${material!.id}` : "Material master"}</p>
          <h2 id="material-dialog-title">{editing ? "Edit material" : "Add material"}</h2>
          <p>{editing ? "Update stock levels, placement or status." : "Create a material record in the inventory database."}</p>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close dialog"><Icon name="close"/></button>
      </div>
      <div className="form-grid">
        {!editing && <label><span>Material ID</span><Input name="id" placeholder="e.g. STL-10084" value={form.id} onChange={(e) => set("id", e.target.value)} maxLength={50} disabled={formDisabled}/></label>}
        <label><span>Name</span><Input name="name" placeholder="e.g. AH36 Steel Plate · 12mm" value={form.name} onChange={(e) => set("name", e.target.value)} maxLength={200} disabled={formDisabled}/></label>
        <label><span>Category</span><Select name="category_id" value={form.category_id} onChange={(e) => set("category_id", e.target.value)} disabled={formDisabled}><option value="">Select category</option>{refs?.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></label>
        <label><span>Batch</span><Input name="batch" placeholder="e.g. B-2408-19" value={form.batch} onChange={(e) => set("batch", e.target.value)} maxLength={50} disabled={formDisabled}/></label>
        <label><span>Unit</span><Input name="unit" placeholder="e.g. sheets" value={form.unit} onChange={(e) => set("unit", e.target.value)} maxLength={20} disabled={formDisabled}/></label>
        <label><span>Status</span><Select name="status" value={form.status} onChange={(e) => set("status", e.target.value as MaterialStatus)} disabled={formDisabled}>{MATERIAL_STATUSES.map((s) => <option key={s}>{s}</option>)}</Select></label>
        <label><span>Total quantity</span><Input name="quantity" type="number" min={0} step={1} placeholder="0" value={form.quantity} onChange={(e) => set("quantity", e.target.value)} disabled={formDisabled}/></label>
        <label><span>Available</span><Input name="available" type="number" min={0} step={1} placeholder="0" value={form.available} onChange={(e) => set("available", e.target.value)} disabled={formDisabled}/></label>
        <label><span>Reserved</span><Input name="reserved" type="number" min={0} step={1} placeholder="0" value={form.reserved} onChange={(e) => set("reserved", e.target.value)} disabled={formDisabled}/></label>
        <label><span>Yard</span><Select name="yard_id" value={form.yard_id} onChange={(e) => setYard(e.target.value)} disabled={formDisabled}><option value="">Select yard</option>{refs?.yards.map((y) => <option key={y.id} value={y.id}>{y.name}</option>)}</Select></label>
        <label><span>Storage location</span><Select name="location_id" value={form.location_id} onChange={(e) => set("location_id", e.target.value)} disabled={formDisabled || !form.yard_id}><option value="">No location</option>{locations.map((l) => <option key={l.id} value={l.id}>Zone {l.zone} · Aisle {l.aisle}{l.bin ? ` · Bin ${l.bin}` : ""}</option>)}</Select></label>
        <label><span>Allocated ship</span><Select name="ship_id" value={form.ship_id} onChange={(e) => set("ship_id", e.target.value)} disabled={formDisabled || !form.yard_id}><option value="">Unassigned</option>{ships.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select></label>
      </div>
      {(error || refsError) && <div className="notice" role="alert"><Icon name="warning"/>{error || refsError}</div>}
      <div className="dialog-actions">
        {editing && <Button type="button" variant="danger" onClick={remove} disabled={busy}>Delete</Button>}
        <Button type="button" variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button type="submit" disabled={formDisabled}>{busy ? "Saving…" : editing ? "Save changes" : "Create material"}</Button>
      </div>
    </form>
  </div>;
}

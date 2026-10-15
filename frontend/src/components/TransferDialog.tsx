import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Button, Icon, Input, Select } from "./ui";
import { listMaterials, type ApiMaterial, type ReferenceData } from "../api/materials";
import { createTransfer, newIdempotencyKey } from "../api/transfers";

export function TransferDialog({ refs, refsError, onClose, onDone }: {
  refs: ReferenceData | null;
  refsError: string;
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  // One key per dialog: retrying after a lost response replays the same request instead of duplicating it.
  const [idempotencyKey] = useState(newIdempotencyKey);
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<ApiMaterial[]>([]);
  const [searchError, setSearchError] = useState("");
  const [source, setSource] = useState<ApiMaterial | null>(null);
  const [quantity, setQuantity] = useState("");
  const [toYard, setToYard] = useState("");
  const [toLocation, setToLocation] = useState("");
  const [expectedArrival, setExpectedArrival] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      listMaterials({ skip: 0, limit: 50, search: search.trim() }, controller.signal)
        .then(({ materials }) => { setResults(materials.filter((m) => m.available > 0)); setSearchError(""); })
        .catch((err) => { if (!controller.signal.aborted) setSearchError(err.message); });
    }, 300);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [search]);

  const options = useMemo(
    () => (source && !results.some((m) => m.id === source.id) ? [source, ...results] : results),
    [results, source],
  );
  const locations = refs?.locations.filter((l) => l.yard_id === toYard) ?? [];

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const qty = Number(quantity);
    if (!source) return setError("Select the source batch.");
    if (quantity.trim() === "" || !Number.isInteger(qty) || qty <= 0) return setError("Quantity must be a whole number greater than 0.");
    if (qty > source.available) return setError(`Only ${source.available} ${source.unit} of ${source.id} are available.`);
    if (!toYard) return setError("Select the destination yard.");
    if (toYard === source.yard_id && (toLocation || null) === source.location_id) return setError("The destination is the same yard and location as the source.");
    setBusy(true);
    setError("");
    try {
      const transfer = await createTransfer({
        material_id: source.id, quantity: qty, to_yard_id: toYard, to_location_id: toLocation || null,
        expected_arrival: expectedArrival || null, notes: notes.trim() || null,
      }, idempotencyKey);
      onDone(`Transfer ${transfer.display_id} requested`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The request failed.");
    } finally {
      setBusy(false);
    }
  };

  const full = { gridColumn: "1 / -1" } as const;
  return <div className="dialog-layer" role="dialog" aria-modal="true" aria-labelledby="transfer-dialog-title">
    <button className="dialog-scrim" onClick={onClose} aria-label="Close dialog"/>
    <form className="dialog" onSubmit={submit} noValidate>
      <div className="dialog-header">
        <div>
          <p className="eyebrow">Material logistics</p>
          <h2 id="transfer-dialog-title">Create transfer</h2>
          <p>Request a movement of available stock. Stock leaves the source only when the transfer is dispatched.</p>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close dialog"><Icon name="close"/></button>
      </div>
      <div className="form-grid">
        <label><span>Find material</span><Input name="search" icon="search" placeholder="ID, name or batch" value={search} onChange={(e) => setSearch(e.target.value)} disabled={busy}/></label>
        <label><span>Source batch</span><Select name="material_id" value={source?.id ?? ""} onChange={(e) => setSource(options.find((m) => m.id === e.target.value) ?? null)} disabled={busy}>
          <option value="">{options.length ? "Select batch" : "No batches with available stock"}</option>
          {options.map((m) => <option key={m.id} value={m.id}>{m.id} · {m.name} · {m.available} {m.unit} at {m.yard.name}</option>)}
        </Select></label>
        {source && <p className="muted-copy" style={full}>From {source.yard.name}{source.location ? ` · Zone ${source.location.zone}, aisle ${source.location.aisle}` : ""} · {source.available} {source.unit} available, {source.reserved} reserved, {source.quantity - source.available - source.reserved} blocked</p>}
        <label><span>Quantity{source ? ` (${source.unit})` : ""}</span><Input name="quantity" type="number" min={1} max={source?.available} step={1} placeholder="0" value={quantity} onChange={(e) => setQuantity(e.target.value)} disabled={busy}/></label>
        <label><span>Expected arrival</span><Input name="expected_arrival" type="date" value={expectedArrival} onChange={(e) => setExpectedArrival(e.target.value)} disabled={busy}/></label>
        <label><span>Destination yard</span><Select name="to_yard_id" value={toYard} onChange={(e) => { setToYard(e.target.value); setToLocation(""); }} disabled={busy || !refs}>
          <option value="">Select yard</option>
          {refs?.yards.map((y) => <option key={y.id} value={y.id}>{y.name}</option>)}
        </Select></label>
        <label><span>Destination location</span><Select name="to_location_id" value={toLocation} onChange={(e) => setToLocation(e.target.value)} disabled={busy || !toYard}>
          <option value="">No specific location</option>
          {locations.map((l) => <option key={l.id} value={l.id}>Zone {l.zone} · Aisle {l.aisle}{l.bin ? ` · Bin ${l.bin}` : ""}</option>)}
        </Select></label>
        <label style={full}><span>Notes</span><Input name="notes" placeholder="Optional — purpose or handling instructions" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={1000} disabled={busy}/></label>
      </div>
      {(error || searchError || refsError) && <div className="notice" role="alert"><Icon name="warning"/>{error || searchError || refsError}</div>}
      <div className="dialog-actions">
        <Button type="button" variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button type="submit" disabled={busy || !refs}>{busy ? "Requesting…" : "Request transfer"}</Button>
      </div>
    </form>
  </div>;
}

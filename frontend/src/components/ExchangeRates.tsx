import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Button, Icon, Input } from "./ui";
import { deleteRate, getRates, setRate, type ExchangeRate } from "../api/currency";

const RATE = /^\d{1,12}(\.\d{1,6})?$/;
const when = (iso: string) => new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

/** Exchange rates into rupees. Everyone sees them; admins add, change and remove them. */
export function ExchangeRates({ canEdit }: { canEdit: boolean }) {
  const [rates, setRates] = useState<ExchangeRate[] | null>(null);
  const [currency, setCurrency] = useState("");
  const [rate, setRateText] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => getRates().then((r) => setRates(r.rates)).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    const code = currency.trim().toUpperCase();
    if (!/^[A-Z]{3}$/.test(code)) return setError("Currency must be a 3-letter code such as USD.");
    if (code === "INR") return setError("INR is the base currency; its rate is always 1.");
    if (!RATE.test(rate.trim()) || Number(rate) <= 0) return setError("The rate must be a number above 0, with at most 6 decimal places.");
    setBusy(true); setError(""); setMessage("");
    try {
      const r = await setRate(code, rate.trim());
      setRates(r.rates);
      setMessage(`1 ${code} = ₹${Number(rate)} saved`);
      setCurrency(""); setRateText("");
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };

  const remove = async (code: string) => {
    if (!window.confirm(`Remove the ${code} rate? Totals in ${code} will no longer be converted to rupees.`)) return;
    setBusy(true); setError(""); setMessage("");
    try { setRates((await deleteRate(code)).rates); setMessage(`${code} rate removed`); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };

  return <div className="exchange-rates">
    <h3>Exchange rates to rupees</h3>
    <p className="muted-copy">Used to show totals in ₹. Stored costs and prices keep their own currency; a currency without a rate is shown as not converted.{canEdit ? "" : " Only admins can change rates."}</p>
    {error && <div className="notice" role="alert"><Icon name="warning"/>{error}</div>}
    {message && <div className="notice" role="status"><Icon name="check"/>{message}</div>}
    {!rates ? <p className="muted-copy">Loading rates…</p> : rates.length === 0 ? <p className="muted-copy">No rates yet: everything outside INR is shown unconverted.</p> :
      <div className="table-scroll"><table><thead><tr><th>Currency</th><th>1 unit in rupees</th><th>Set by</th>{canEdit && <th aria-label="Actions"/>}</tr></thead><tbody>
        {rates.map((r) => <tr key={r.currency}>
          <td><strong className="mono">{r.currency}</strong></td>
          <td><strong>₹{Number(r.rate).toLocaleString("en-IN", { maximumFractionDigits: 6 })}</strong></td>
          <td><small>{r.updated_by} · {when(r.updated_at)}</small></td>
          {canEdit && <td className="users-actions"><Button variant="ghost" disabled={busy} onClick={() => { setCurrency(r.currency); setRateText(String(Number(r.rate))); }}>Change</Button><Button variant="secondary" disabled={busy} onClick={() => remove(r.currency)}>Remove</Button></td>}
        </tr>)}
      </tbody></table></div>}
    {canEdit && <form className="rate-form" onSubmit={save} noValidate>
      <label><span>Currency</span><Input aria-label="Currency code" placeholder="USD" maxLength={3} value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} disabled={busy}/></label>
      <label><span>1 unit = ₹</span><Input aria-label="Rate in rupees" inputMode="decimal" placeholder="83.25" value={rate} onChange={(e) => setRateText(e.target.value)} disabled={busy}/></label>
      <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save rate"}</Button>
    </form>}
  </div>;
}

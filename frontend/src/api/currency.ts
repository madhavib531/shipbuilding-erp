import { apiRequest } from "./client";

/** Totals are shown in this currency; other currencies are converted with admin-entered rates. */
export const BASE_CURRENCY = "INR";

export type BaseTotal = {
  currency: string;
  amount: string;
  parts: { currency: string; amount: string; rate: string; in_base: string }[];
  missing_rates: { currency: string; amount: string }[];
};
export type ExchangeRate = { currency: string; rate: string; updated_by: string; updated_at: string };

type Envelope<T> = { status: string; message: string; data: T };
type Rates = { base: string; rates: ExchangeRate[] };

export const getRates = async (signal?: AbortSignal) => (await apiRequest<Envelope<Rates>>("/api/v1/exchange-rates", { signal })).data;
export const setRate = async (currency: string, rate: string) =>
  (await apiRequest<Envelope<Rates>>(`/api/v1/exchange-rates/${encodeURIComponent(currency)}`, { method: "PUT", body: JSON.stringify({ rate }) })).data;
export const deleteRate = async (currency: string) =>
  (await apiRequest<Envelope<Rates>>(`/api/v1/exchange-rates/${encodeURIComponent(currency)}`, { method: "DELETE" })).data;

/** "incl. $60.00 at ₹83.5" for converted foreign amounts; "" when everything was already in rupees. */
export function conversionNote(total: BaseTotal, format: (amount: string | number, currency: string) => string) {
  const foreign = total.parts.filter((p) => p.currency !== total.currency);
  const notes = foreign.map((p) => `${format(p.amount, p.currency)} at ${format(p.rate, total.currency)}`);
  const missing = total.missing_rates.map((m) => `${format(m.amount, m.currency)} not converted (no ${m.currency} rate)`);
  return [...(notes.length ? [`incl. ${notes.join(", ")}`] : []), ...missing].join(" · ");
}

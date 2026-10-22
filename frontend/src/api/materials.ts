import { apiRequest } from "./client";

export const MATERIAL_STATUSES = ["Healthy", "Low stock", "Inspection", "Reserved"] as const;
export type MaterialStatus = (typeof MATERIAL_STATUSES)[number];

export type ApiMaterial = {
  id: string;
  name: string;
  category_id: string;
  batch: string;
  quantity: number;
  available: number;
  reserved: number;
  unit: string;
  yard_id: string;
  location_id: string | null;
  ship_id: string | null;
  status: MaterialStatus;
  /** Cost of one unit; null when the batch is not valued. */
  unit_cost: string | number | null;
  cost_currency: string | null;
  version: number;
  /** Part of the blocked quantity (quantity − available − reserved) awaiting an inspection decision. */
  held_quantity: number;
  created_at: string;
  updated_at: string;
  category: { id: string; name: string };
  yard: { id: string; name: string };
  location: { id: string; zone: string; aisle: string } | null;
  ship: { id: string; name: string } | null;
};

export type MaterialInput = {
  name: string;
  category_id: string;
  batch: string;
  quantity: number;
  available: number;
  reserved: number;
  unit: string;
  yard_id: string;
  location_id: string | null;
  ship_id: string | null;
  status: MaterialStatus;
  unit_cost?: string | null;
  cost_currency?: string | null;
};

export type ReferenceData = {
  categories: { id: string; name: string }[];
  yards: { id: string; name: string }[];
  locations: { id: string; yard_id: string; zone: string; aisle: string; bin: string | null }[];
  ships: { id: string; name: string; yard_id: string }[];
};

export type MaterialQuery = { skip: number; limit: number; search?: string; category?: string; yard?: string; ship?: string; status?: MaterialStatus };

/** Batch counts; "Low stock" is the manually assigned status, not a computed threshold. */
export type MaterialSummary = {
  total_batches: number;
  available_batches: number;
  available_percent: number;
  reserved_batches: number;
  low_stock_batches: number;
  low_stock_ship_allocated: number;
  active_yards: number;
  /** On-hand quantity x unit cost, per currency (no exchange rates). */
  stock_value: { currency: string; amount: string }[];
  /** Batches with stock but no unit cost. */
  unvalued_batches: number;
  /** stock_value converted into rupees with the admin-entered rates. */
  stock_value_base: import("./currency").BaseTotal;
};

type Envelope<T> = { status: string; message: string; data: T };

export async function listMaterials(query: MaterialQuery, signal?: AbortSignal) {
  const params = new URLSearchParams({ skip: String(query.skip), limit: String(query.limit) });
  if (query.search) params.set("search", query.search);
  if (query.category) params.set("category", query.category);
  if (query.yard) params.set("yard", query.yard);
  if (query.ship) params.set("ship", query.ship);
  if (query.status) params.set("status_filter", query.status);
  const res = await apiRequest<Envelope<{ materials: ApiMaterial[]; total: number }>>(`/api/v1/materials?${params}`, { signal });
  return res.data;
}

export async function getMaterialSummary(signal?: AbortSignal, yard = "") {
  return (await apiRequest<Envelope<MaterialSummary>>("/api/v1/materials/summary" + (yard ? `?yard=${encodeURIComponent(yard)}` : ""), { signal })).data;
}

export async function getMaterial(id: string, signal?: AbortSignal) {
  return (await apiRequest<Envelope<ApiMaterial>>(`/api/v1/materials/${encodeURIComponent(id)}`, { signal })).data;
}

/** Who made a stock change and why; recorded on the ADJUSTMENT ledger entry. */
export type StockNote = { actor?: string; stock_reason?: string | null };

export async function createMaterial(input: MaterialInput & { id: string } & StockNote) {
  return (await apiRequest<Envelope<ApiMaterial>>("/api/v1/materials", { method: "POST", body: JSON.stringify(input) })).data;
}

export async function updateMaterial(id: string, changes: Partial<MaterialInput> & StockNote, expectedVersion: number) {
  const body = { ...changes, expected_version: expectedVersion };
  return (await apiRequest<Envelope<ApiMaterial>>(`/api/v1/materials/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(body) })).data;
}

export async function deleteMaterial(id: string) {
  await apiRequest<Envelope<{ id: string }>>(`/api/v1/materials/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function getReferenceData(signal?: AbortSignal) {
  return (await apiRequest<Envelope<ReferenceData>>("/api/v1/reference-data", { signal })).data;
}

/** One ledger row: a stock movement or status change of a batch. */
export type MaterialTransaction = {
  id: string;
  transaction_type: string;
  quantity: number;
  unit: string;
  from_location_id: string | null;
  to_location_id: string | null;
  reference_id: string | null;
  actor: string;
  reason: string | null;
  status: string | null;
  created_at: string;
};

export async function getMaterialTransactions(id: string, limit: number, signal?: AbortSignal) {
  const params = new URLSearchParams({ skip: "0", limit: String(limit) });
  return (await apiRequest<Envelope<{ transactions: MaterialTransaction[]; total: number }>>(`/api/v1/materials/${encodeURIComponent(id)}/transactions?${params}`, { signal })).data;
}

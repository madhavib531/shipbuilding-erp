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
  version: number;
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
};

export type ReferenceData = {
  categories: { id: string; name: string }[];
  yards: { id: string; name: string }[];
  locations: { id: string; yard_id: string; zone: string; aisle: string; bin: string | null }[];
  ships: { id: string; name: string; yard_id: string }[];
};

export type MaterialQuery = { skip: number; limit: number; search?: string; category?: string; yard?: string };

type Envelope<T> = { status: string; message: string; data: T };

export async function listMaterials(query: MaterialQuery, signal?: AbortSignal) {
  const params = new URLSearchParams({ skip: String(query.skip), limit: String(query.limit) });
  if (query.search) params.set("search", query.search);
  if (query.category) params.set("category", query.category);
  if (query.yard) params.set("yard", query.yard);
  const res = await apiRequest<Envelope<{ materials: ApiMaterial[]; total: number }>>(`/api/v1/materials?${params}`, { signal });
  return res.data;
}

export async function getMaterial(id: string, signal?: AbortSignal) {
  return (await apiRequest<Envelope<ApiMaterial>>(`/api/v1/materials/${encodeURIComponent(id)}`, { signal })).data;
}

export async function createMaterial(input: MaterialInput & { id: string }) {
  return (await apiRequest<Envelope<ApiMaterial>>("/api/v1/materials", { method: "POST", body: JSON.stringify(input) })).data;
}

export async function updateMaterial(id: string, changes: Partial<MaterialInput>, expectedVersion: number) {
  const body = { ...changes, expected_version: expectedVersion };
  return (await apiRequest<Envelope<ApiMaterial>>(`/api/v1/materials/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(body) })).data;
}

export async function deleteMaterial(id: string) {
  await apiRequest<Envelope<{ id: string }>>(`/api/v1/materials/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function getReferenceData(signal?: AbortSignal) {
  return (await apiRequest<Envelope<ReferenceData>>("/api/v1/reference-data", { signal })).data;
}

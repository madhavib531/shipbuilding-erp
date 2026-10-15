import { apiRequest } from "./client";

export const SUPPLIER_STATUSES = ["Approved", "Conditional", "Probation", "Inactive", "Blocked"] as const;
export type SupplierStatus = (typeof SUPPLIER_STATUSES)[number];
/** Statuses that may receive new or amended purchase orders. */
export const ORDERABLE_SUPPLIER_STATUSES: SupplierStatus[] = ["Approved", "Conditional", "Probation"];

export type Supplier = {
  id: string;
  name: string;
  contact_person: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  address: string | null;
  country: string | null;
  status: SupplierStatus;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type SupplierInput = Omit<Supplier, "id" | "created_at" | "updated_at">;

type Envelope<T> = { status: string; message: string; data: T };

export async function listSuppliers(query: { search?: string; status?: SupplierStatus; skip: number; limit: number }, signal?: AbortSignal) {
  const params = new URLSearchParams({ skip: String(query.skip), limit: String(query.limit) });
  if (query.search) params.set("search", query.search);
  if (query.status) params.set("status", query.status);
  return (await apiRequest<Envelope<{ suppliers: Supplier[]; total: number }>>(`/api/v1/suppliers?${params}`, { signal })).data;
}

export async function createSupplier(input: SupplierInput & { id: string }) {
  return (await apiRequest<Envelope<Supplier>>("/api/v1/suppliers", { method: "POST", body: JSON.stringify(input) })).data;
}

export async function updateSupplier(id: string, changes: Partial<SupplierInput>) {
  return (await apiRequest<Envelope<Supplier>>(`/api/v1/suppliers/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(changes) })).data;
}

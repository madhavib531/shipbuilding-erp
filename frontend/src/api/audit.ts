import { apiRequest } from "./client";

export type AuditSource = "stock" | "transfer" | "purchase_order" | "inspection";
export const AUDIT_SOURCES: { value: AuditSource; label: string }[] = [
  { value: "stock", label: "Stock ledger" },
  { value: "transfer", label: "Transfers" },
  { value: "purchase_order", label: "Purchase orders" },
  { value: "inspection", label: "Inspections" },
];

export type AuditEvent = {
  key: string;
  source: AuditSource;
  source_label: string;
  record: string | null;
  material_id: string | null;
  subject: string | null;
  batch: string | null;
  action: string;
  from_status: string | null;
  to_status: string | null;
  actor: string;
  reason: string | null;
  quantity: number | null;
  unit: string | null;
  detail: string | null;
  created_at: string;
};

export type AuditQuery = { skip: number; limit: number; search?: string; source?: AuditSource; dateFrom?: string; dateTo?: string };

type Envelope<T> = { status: string; message: string; data: T };

export async function listAuditEvents(query: AuditQuery, signal?: AbortSignal) {
  const params = new URLSearchParams({ skip: String(query.skip), limit: String(query.limit) });
  if (query.search) params.set("search", query.search);
  if (query.source) params.set("source", query.source);
  if (query.dateFrom) params.set("date_from", query.dateFrom);
  if (query.dateTo) params.set("date_to", query.dateTo);
  return (await apiRequest<Envelope<{ events: AuditEvent[]; total: number }>>(`/api/v1/audit-events?${params}`, { signal })).data;
}

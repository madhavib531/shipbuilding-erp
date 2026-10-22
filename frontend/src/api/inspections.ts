import { apiRequest } from "./client";

export type InspectionStatus = "Open" | "Released" | "Rejected" | "Partially released";
export const INSPECTION_STATUSES: InspectionStatus[] = ["Open", "Released", "Partially released", "Rejected"];

export type RejectionDisposition = "Return to supplier" | "Scrap";
export const REJECTION_DISPOSITIONS: RejectionDisposition[] = ["Return to supplier", "Scrap"];

type Ref = { id: string; name: string };

export type InspectionEvent = {
  id: number;
  action: string;
  from_status: string | null;
  to_status: string;
  quantity: number;
  disposition: string | null;
  actor: string;
  reason: string | null;
  version: number;
  created_at: string;
};

export type Inspection = {
  id: number;
  display_id: string;
  status: InspectionStatus;
  quantity: number;
  released_quantity: number;
  rejected_quantity: number;
  outstanding_quantity: number;
  created_by: string;
  version: number;
  created_at: string;
  updated_at: string;
  material: {
    id: string; name: string; batch: string; unit: string; status: string; quantity: number; available: number;
    yard: Ref; location: { id: string; zone: string; aisle: string } | null;
  };
  /** Null when the hold was opened by hand on stock already in the batch. */
  goods_receipt_line: {
    id: number;
    purchase_order_line: { line_no: number; description: string };
    receipt: {
      id: number; display_id: string; delivery_note: string | null; received_by: string; received_at: string;
      purchase_order: { id: number; display_id: string; supplier: Ref };
    };
  } | null;
  events?: InspectionEvent[];
};

export type InspectionSummary = { open: number; released_this_week: number; rejected_this_week: number };

type Envelope<T> = { status: string; message: string; data: T };

const path = (id: number, action?: string) => `/api/v1/inspections/${id}${action ? `/${action}` : ""}`;
const post = async (url: string, body: object) =>
  (await apiRequest<Envelope<Inspection>>(url, { method: "POST", body: JSON.stringify(body) })).data;

export async function listInspections(query: { status?: InspectionStatus; search?: string; yard?: string; skip: number; limit: number }, signal?: AbortSignal) {
  const params = new URLSearchParams({ skip: String(query.skip), limit: String(query.limit) });
  if (query.yard) params.set("yard", query.yard);
  if (query.status) params.set("status", query.status);
  if (query.search) params.set("search", query.search);
  return (await apiRequest<Envelope<{ inspections: Inspection[]; total: number }>>(`/api/v1/inspections?${params}`, { signal })).data;
}

export async function getInspectionSummary(signal?: AbortSignal, yard = "") {
  return (await apiRequest<Envelope<InspectionSummary>>("/api/v1/inspections/summary" + (yard ? `?yard=${encodeURIComponent(yard)}` : ""), { signal })).data;
}

export async function getInspection(id: number, signal?: AbortSignal) {
  return (await apiRequest<Envelope<Inspection>>(path(id), { signal })).data;
}

/** Holds part of a batch's available stock for inspection. */
export const createInspection = (materialId: string, quantity: number, reason: string) =>
  post("/api/v1/inspections", { material_id: materialId, quantity, reason });

export const releaseInspection = (id: number, expectedVersion: number, quantity: number, note: string | null) =>
  post(path(id, "release"), { expected_version: expectedVersion, quantity, note });

export const rejectInspection = (id: number, expectedVersion: number, quantity: number, reason: string, disposition: RejectionDisposition) =>
  post(path(id, "reject"), { expected_version: expectedVersion, quantity, reason, disposition });

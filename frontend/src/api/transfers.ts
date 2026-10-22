import { apiRequest } from "./client";

export type TransferStatus = "Requested" | "Approved" | "Rejected" | "Dispatched" | "Received" | "Cancelled";

export const TRANSFER_STATUS_LABEL: Record<TransferStatus, string> = {
  Requested: "Approval needed",
  Approved: "Ready to dispatch",
  Rejected: "Rejected",
  Dispatched: "In transit",
  Received: "Received",
  Cancelled: "Cancelled",
};

export type TransferEvent = {
  id: number;
  action: string;
  from_status: string | null;
  to_status: string;
  actor: string;
  reason: string | null;
  quantity: number | null;
  created_at: string;
};

type Ref = { id: string; name: string };
type LocationRef = { id: string; zone: string; aisle: string };

export type Transfer = {
  id: number;
  display_id: string;
  material_id: string;
  material: { id: string; name: string; batch: string; unit: string };
  quantity: number;
  unit: string;
  from_yard: Ref;
  from_location: LocationRef | null;
  to_yard: Ref;
  to_location: LocationRef | null;
  status: TransferStatus;
  expected_arrival: string | null;
  notes: string | null;
  requested_by: string;
  received_quantity: number | null;
  shortage_quantity: number | null;
  destination_material_id: string | null;
  created_at: string;
  updated_at: string;
  events: TransferEvent[];
};

export type TransferSummary = {
  awaiting_approval: number;
  ready_to_dispatch: number;
  in_transit: number;
  pending: number;
  due_today: number;
  overdue: number;
  received_this_week: number;
};

export type TransferRequest = {
  material_id: string;
  quantity: number;
  to_yard_id: string;
  to_location_id: string | null;
  expected_arrival: string | null;
  notes: string | null;
};

export type ReceiveInput = {
  received_quantity: number;
  destination_material_id: string | null;
  discrepancy_reason: string | null;
};

type Envelope<T> = { status: string; message: string; data: T };

const path = (id: number, action?: string) => `/api/v1/transfers/${id}${action ? `/${action}` : ""}`;
const post = async (url: string, body: object, headers?: Record<string, string>) =>
  (await apiRequest<Envelope<Transfer>>(url, { method: "POST", body: JSON.stringify(body), headers })).data;

/** `yard` matches transfers from or to that yard. */
export async function listTransfers(statuses: TransferStatus[], page: { skip: number; limit: number; yard?: string }, signal?: AbortSignal) {
  const params = new URLSearchParams({ skip: String(page.skip), limit: String(page.limit) });
  if (page.yard) params.set("yard", page.yard);
  statuses.forEach((s) => params.append("status", s));
  return (await apiRequest<Envelope<{ transfers: Transfer[]; total: number }>>(`/api/v1/transfers?${params}`, { signal })).data;
}

export async function getTransferSummary(signal?: AbortSignal, yard = "") {
  return (await apiRequest<Envelope<TransferSummary>>("/api/v1/transfers/summary" + (yard ? `?yard=${encodeURIComponent(yard)}` : ""), { signal })).data;
}

export async function getTransfer(id: number, signal?: AbortSignal) {
  return (await apiRequest<Envelope<Transfer>>(path(id), { signal })).data;
}

export const createTransfer = (request: TransferRequest, idempotencyKey: string) =>
  post("/api/v1/transfers", request, { "Idempotency-Key": idempotencyKey });
export const approveTransfer = (id: number, note: string | null) => post(path(id, "approve"), { reason: note });
export const rejectTransfer = (id: number, reason: string) => post(path(id, "reject"), { reason });
export const cancelTransfer = (id: number, reason: string) => post(path(id, "cancel"), { reason });
export const dispatchTransfer = (id: number, note: string | null) => post(path(id, "dispatch"), { reason: note });
export const receiveTransfer = (id: number, input: ReceiveInput) => post(path(id, "receive"), input);

export function newIdempotencyKey(): string {
  return typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

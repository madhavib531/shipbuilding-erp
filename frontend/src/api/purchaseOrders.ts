import { apiRequest } from "./client";
import { CURRENT_USER } from "../currentUser";
import type { SupplierStatus } from "./suppliers";

export const PURCHASE_ORDER_STATUSES = ["Draft", "Approved", "Partially received", "Received", "Cancelled", "Closed"] as const;
export type PurchaseOrderStatus = (typeof PURCHASE_ORDER_STATUSES)[number];

/** Money arrives as decimal strings so no precision is lost; convert only for display. */
export type Money = string;

export type PurchaseOrderLine = {
  id: number;
  line_no: number;
  category: { id: string; name: string };
  description: string;
  unit: string;
  supplier_part_number: string | null;
  ordered_quantity: number;
  received_quantity: number;
  rejected_quantity: number;
  cancelled_quantity: number;
  outstanding_quantity: number;
  unit_price: Money;
  currency: string;
  line_total: Money;
};

export type PurchaseOrderEvent = {
  id: number;
  action: string;
  from_status: string | null;
  to_status: string;
  actor: string;
  reason: string | null;
  version: number;
  changes: Record<string, unknown> | null;
  created_at: string;
};

export type ReceiptLine = {
  id: number;
  purchase_order_line: { id: number; line_no: number; description: string; unit: string };
  accepted_quantity: number;
  rejected_quantity: number;
  rejection_reason: string | null;
  destination_material_id: string | null;
  inspection_hold: { id: number; display_id: string; status: string; quantity: number; outstanding_quantity: number } | null;
};

export type GoodsReceipt = {
  id: number;
  display_id: string;
  purchase_order_id: number;
  yard: { id: string; name: string };
  location: { id: string; zone: string; aisle: string } | null;
  delivery_note: string | null;
  notes: string | null;
  received_by: string;
  received_at: string;
  lines: ReceiptLine[];
};

export type PurchaseOrder = {
  id: number;
  display_id: string;
  supplier: { id: string; name: string; status: SupplierStatus };
  status: PurchaseOrderStatus;
  expected_delivery_date: string | null;
  notes: string | null;
  created_by: string;
  approved_by: string | null;
  approved_at: string | null;
  version: number;
  currency: string | null;
  total_value: Money;
  outstanding_value: Money;
  ordered_quantity: number;
  received_quantity: number;
  is_overdue: boolean;
  created_at: string;
  updated_at: string;
  lines: PurchaseOrderLine[];
  events?: PurchaseOrderEvent[];
  receipts?: GoodsReceipt[];
};

export type PurchaseOrderSummary = {
  by_status: Record<PurchaseOrderStatus, number>;
  open: number;
  overdue: number;
  due_this_week: number;
  partially_received: number;
  open_value: { currency: string; amount: Money }[];
};

export type LineInput = {
  category_id: string;
  description: string;
  unit: string;
  supplier_part_number: string | null;
  ordered_quantity: number;
  unit_price: string;
  currency: string;
};

export type OrderInput = {
  supplier_id: string;
  expected_delivery_date: string | null;
  notes: string | null;
  lines: LineInput[];
};

export type ReceiptLineInput = {
  purchase_order_line_id: number;
  accepted_quantity: number;
  rejected_quantity: number;
  rejection_reason: string | null;
  destination_material_id: string | null;
  batch: string | null;
  hold_for_inspection: boolean;
};

export type ReceiptInput = {
  yard_id: string;
  location_id: string | null;
  delivery_note: string | null;
  notes: string | null;
  lines: ReceiptLineInput[];
};

type Envelope<T> = { status: string; message: string; data: T };
const BASE = "/api/v1/purchase-orders";
const send = async <T>(url: string, method: string, body: object, headers?: Record<string, string>) =>
  (await apiRequest<Envelope<T>>(url, { method, body: JSON.stringify({ actor: CURRENT_USER.name, ...body }), headers })).data;

export async function listPurchaseOrders(query: { search?: string; supplierId?: string; status?: PurchaseOrderStatus; overdue?: boolean; skip: number; limit: number }, signal?: AbortSignal) {
  const params = new URLSearchParams({ skip: String(query.skip), limit: String(query.limit) });
  if (query.search) params.set("search", query.search);
  if (query.supplierId) params.set("supplier_id", query.supplierId);
  if (query.status) params.set("status", query.status);
  if (query.overdue) params.set("overdue", "true");
  return (await apiRequest<Envelope<{ purchase_orders: PurchaseOrder[]; total: number }>>(`${BASE}?${params}`, { signal })).data;
}

export async function getPurchaseOrderSummary(signal?: AbortSignal) {
  return (await apiRequest<Envelope<PurchaseOrderSummary>>(`${BASE}/summary`, { signal })).data;
}

export async function getPurchaseOrder(id: number, signal?: AbortSignal) {
  return (await apiRequest<Envelope<PurchaseOrder>>(`${BASE}/${id}`, { signal })).data;
}

export const createPurchaseOrder = (input: OrderInput, idempotencyKey: string) =>
  send<PurchaseOrder>(BASE, "POST", input, { "Idempotency-Key": idempotencyKey });

/** Draft edit: send only what changed; `lines`, when sent, replaces every line. */
export const updatePurchaseOrder = (id: number, expectedVersion: number, changes: Partial<OrderInput>) =>
  send<PurchaseOrder>(`${BASE}/${id}`, "PATCH", { expected_version: expectedVersion, ...changes });

export type OrderAction = "approve" | "reopen" | "cancel" | "close";
export const actOnPurchaseOrder = (id: number, action: OrderAction, expectedVersion: number, reason: string | null) =>
  send<PurchaseOrder>(`${BASE}/${id}/${action}`, "POST", { expected_version: expectedVersion, reason });

export const postGoodsReceipt = (id: number, expectedVersion: number, input: ReceiptInput, idempotencyKey: string) =>
  send<{ receipt: GoodsReceipt; purchase_order: PurchaseOrder }>(
    `${BASE}/${id}/receipts`, "POST", { expected_version: expectedVersion, ...input }, { "Idempotency-Key": idempotencyKey });

export function formatMoney(amount: Money | number, currency: string | null) {
  const value = Number(amount);
  if (!currency) return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 2 }).format(value);
  } catch {
    return `${currency} ${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  }
}

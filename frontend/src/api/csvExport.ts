import { listAuditEvents, type AuditEvent, type AuditQuery } from "./audit";
import { getRates } from "./currency";
import { listInspections, type Inspection, type InspectionStatus } from "./inspections";
import { listMaterials, type ApiMaterial, type MaterialQuery } from "./materials";
import { listPurchaseOrders, type PurchaseOrder, type PurchaseOrderStatus } from "./purchaseOrders";
import { listSuppliers, type Supplier, type SupplierStatus } from "./suppliers";

type Column<T> = [string, (row: T) => string | number | null];

const INVENTORY_PAGE_SIZE = 500;   // the materials list allows up to 1000 per request
const AUDIT_PAGE_SIZE = 200;       // the audit feed allows up to 200 per request

const INVENTORY_COLUMNS: Column<ApiMaterial>[] = [
  ["Batch ID", (m) => m.id],
  ["Material", (m) => m.name],
  ["Category", (m) => m.category.name],
  ["Lot", (m) => m.batch],
  ["Unit", (m) => m.unit],
  ["Quantity", (m) => m.quantity],
  ["Available", (m) => m.available],
  ["Reserved", (m) => m.reserved],
  ["On inspection hold", (m) => m.held_quantity],
  ["Status", (m) => m.status],
  ["Yard", (m) => m.yard.name],
  ["Zone", (m) => m.location?.zone ?? ""],
  ["Aisle", (m) => m.location?.aisle ?? ""],
  ["Ship", (m) => m.ship?.name ?? ""],
  ["Unit cost", (m) => (m.unit_cost == null ? "" : Number(m.unit_cost))],
  ["Cost currency", (m) => m.cost_currency ?? ""],
  ["Value (on hand x unit cost)", (m) => (m.unit_cost == null ? "" : Math.round(Number(m.unit_cost) * m.quantity * 100) / 100)],
  ["Updated", (m) => m.updated_at],
];

const ORDER_COLUMNS: Column<PurchaseOrder>[] = [
  ["Order", (o) => o.display_id],
  ["Status", (o) => o.status],
  ["Supplier", (o) => o.supplier.name],
  ["Deliver to yard", (o) => o.delivery_yard?.name ?? ""],
  ["Expected delivery", (o) => o.expected_delivery_date],
  ["Overdue", (o) => (o.is_overdue ? "yes" : "no")],
  ["Lines", (o) => o.lines.length],
  ["Ordered quantity", (o) => o.ordered_quantity],
  ["Received quantity", (o) => o.received_quantity],
  ["Currency", (o) => o.currency],
  ["Total value", (o) => Number(o.total_value)],
  ["Outstanding value", (o) => Number(o.outstanding_value)],
  ["Created by", (o) => o.created_by],
  ["Approved by", (o) => o.approved_by],
  ["Created", (o) => o.created_at],
];

const SUPPLIER_COLUMNS: Column<Supplier>[] = [
  ["Supplier ID", (s) => s.id], ["Name", (s) => s.name], ["Status", (s) => s.status], ["Country", (s) => s.country],
  ["Contact", (s) => s.contact_person], ["Email", (s) => s.contact_email], ["Phone", (s) => s.contact_phone],
  ["Address", (s) => s.address], ["Notes", (s) => s.notes],
];

const INSPECTION_COLUMNS: Column<Inspection>[] = [
  ["Inspection", (h) => h.display_id],
  ["Status", (h) => h.status],
  ["Batch ID", (h) => h.material.id],
  ["Material", (h) => h.material.name],
  ["Lot", (h) => h.material.batch],
  ["Yard", (h) => h.material.yard.name],
  ["Unit", (h) => h.material.unit],
  ["Held", (h) => h.quantity],
  ["Awaiting decision", (h) => h.outstanding_quantity],
  ["Released", (h) => h.released_quantity],
  ["Rejected", (h) => h.rejected_quantity],
  ["Source", (h) => h.goods_receipt_line ? `${h.goods_receipt_line.receipt.purchase_order.display_id} / ${h.goods_receipt_line.receipt.display_id}` : "Held from stock"],
  ["Supplier", (h) => h.goods_receipt_line?.receipt.purchase_order.supplier.name ?? ""],
  ["Held by", (h) => h.created_by],
  ["Held at", (h) => h.created_at],
];

/** Reads every page of a list endpoint (offset paging) until `total` rows are collected. */
async function allPages<T>(pageSize: number, fetchPage: (skip: number) => Promise<{ rows: T[]; total: number }>) {
  const rows: T[] = [];
  for (let skip = 0; ; skip += pageSize) {
    const page = await fetchPage(skip);
    rows.push(...page.rows);
    if (page.rows.length < pageSize || rows.length >= page.total) break;
  }
  return rows;
}

export async function purchaseOrdersCsv(filters: { search?: string; supplierId?: string; status?: PurchaseOrderStatus; yard?: string }) {
  const rows = await allPages(200, async (skip) => {
    const r = await listPurchaseOrders({ ...filters, skip, limit: 200 });
    return { rows: r.purchase_orders, total: r.total };
  });
  return { csv: toCsv(ORDER_COLUMNS, rows), count: rows.length };
}

export async function suppliersCsv(filters: { search?: string; status?: SupplierStatus }) {
  const rows = await allPages(200, async (skip) => {
    const r = await listSuppliers({ ...filters, skip, limit: 200 });
    return { rows: r.suppliers, total: r.total };
  });
  return { csv: toCsv(SUPPLIER_COLUMNS, rows), count: rows.length };
}

export async function inspectionsCsv(filters: { search?: string; status?: InspectionStatus; yard?: string }) {
  const rows = await allPages(200, async (skip) => {
    const r = await listInspections({ ...filters, skip, limit: 200 });
    return { rows: r.inspections, total: r.total };
  });
  return { csv: toCsv(INSPECTION_COLUMNS, rows), count: rows.length };
}

const AUDIT_COLUMNS: Column<AuditEvent>[] = [
  ["Time", (e) => e.created_at],
  ["Event type", (e) => e.source_label],
  ["Action", (e) => e.action],
  ["From status", (e) => e.from_status],
  ["To status", (e) => e.to_status],
  ["Record", (e) => e.record],
  ["Material ID", (e) => e.material_id],
  ["Subject", (e) => e.subject],
  ["Lot", (e) => e.batch],
  ["Quantity", (e) => e.quantity],
  ["Unit", (e) => e.unit],
  ["Actor", (e) => e.actor],
  ["Reason", (e) => e.reason],
  ["Detail", (e) => e.detail],
  ["Event key", (e) => e.key],
];

/** Quotes a CSV cell; text starting with = + - @ is prefixed with ' so spreadsheets do not run it as a formula. */
function cell(value: string | number | null) {
  if (value === null) return "";
  if (typeof value === "number") return String(value);
  const safe = /^[=+\-@\t\r]/.test(value) ? `'${value}` : value;
  return /[",\r\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

function toCsv<T>(columns: Column<T>[], rows: T[]) {
  const lines = [columns.map(([h]) => h).join(","), ...rows.map((r) => columns.map(([, get]) => cell(get(r))).join(","))];
  return lines.join("\r\n") + "\r\n";
}

/** Every batch matching the filters (all pages), as CSV text. */
export async function inventoryCsv(filters: Omit<MaterialQuery, "skip" | "limit">) {
  const rows: ApiMaterial[] = [];
  for (let skip = 0; ; skip += INVENTORY_PAGE_SIZE) {
    const { materials, total } = await listMaterials({ ...filters, skip, limit: INVENTORY_PAGE_SIZE });
    rows.push(...materials);
    if (materials.length === 0 || rows.length >= total) break;
  }
  // Value in rupees with the admin-entered rates; blank when the batch has no cost or its currency no rate.
  const rates: Record<string, number> = { INR: 1 };
  for (const r of (await getRates()).rates) rates[r.currency] = Number(r.rate);
  const columns: Column<ApiMaterial>[] = [...INVENTORY_COLUMNS, ["Value in INR", (m) => {
    const rate = m.cost_currency ? rates[m.cost_currency] : undefined;
    return m.unit_cost == null || rate === undefined ? "" : Math.round(Number(m.unit_cost) * m.quantity * rate * 100) / 100;
  }]];
  return { csv: toCsv(columns, rows), count: rows.length };
}

/** Every audit event matching the filters (all pages, newest first), as CSV text. Events recorded while
 * exporting push older ones onto later pages; those repeats are dropped by event key. */
export async function auditCsv(filters: Omit<AuditQuery, "skip" | "limit">) {
  const rows: AuditEvent[] = [];
  const seen = new Set<string>();
  for (let skip = 0; ; skip += AUDIT_PAGE_SIZE) {
    const { events, total } = await listAuditEvents({ ...filters, skip, limit: AUDIT_PAGE_SIZE });
    for (const e of events) if (!seen.has(e.key)) { seen.add(e.key); rows.push(e); }
    if (events.length < AUDIT_PAGE_SIZE || skip + events.length >= total) break;
  }
  return { csv: toCsv(AUDIT_COLUMNS, rows), count: rows.length };
}

export function downloadCsv(csv: string, filename: string) {
  // The byte-order mark lets Excel read the file as UTF-8.
  const url = URL.createObjectURL(new Blob(["﻿", csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

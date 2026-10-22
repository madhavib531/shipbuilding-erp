import { listAuditEvents, type AuditEvent, type AuditQuery } from "./audit";
import { listMaterials, type ApiMaterial, type MaterialQuery } from "./materials";

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
  ["Updated", (m) => m.updated_at],
];

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
  return { csv: toCsv(INVENTORY_COLUMNS, rows), count: rows.length };
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

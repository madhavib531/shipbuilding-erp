export type MaterialStatus = "Healthy" | "Low stock" | "Inspection" | "Reserved";

export type Material = {
  id: string;
  name: string;
  category: string;
  batch: string;
  quantity: number;
  available: number;
  reserved: number;
  unit: string;
  yard: string;
  ship: string;
  status: MaterialStatus;
};

export const materials: Material[] = [
  { id: "STL-10084", name: "AH36 Steel Plate · 12mm", category: "Structural steel", batch: "B-2408-19", quantity: 284, available: 212, reserved: 72, unit: "sheets", yard: "Harbor North", ship: "MV Calypso", status: "Healthy" },
  { id: "PIP-20412", name: "Cu-Ni Pipe · 80mm", category: "Piping", batch: "CN-4402", quantity: 86, available: 18, reserved: 68, unit: "lengths", yard: "East Basin", ship: "NS Atlas", status: "Low stock" },
  { id: "CAB-77102", name: "Marine Power Cable", category: "Electrical", batch: "EL-0917", quantity: 1280, available: 940, reserved: 340, unit: "meters", yard: "Harbor North", ship: "MV Calypso", status: "Healthy" },
  { id: "VAL-50118", name: "DN150 Butterfly Valve", category: "Mechanical", batch: "VA-3201", quantity: 42, available: 24, reserved: 18, unit: "units", yard: "Dry Dock 4", ship: "OSV Meridian", status: "Inspection" },
  { id: "INS-99341", name: "A-60 Fire Insulation", category: "Outfitting", batch: "FI-1211", quantity: 610, available: 156, reserved: 454, unit: "panels", yard: "East Basin", ship: "NS Atlas", status: "Reserved" },
  { id: "WLD-33082", name: "E7018 Welding Electrodes", category: "Consumables", batch: "WE-8834", quantity: 144, available: 22, reserved: 122, unit: "boxes", yard: "Harbor North", ship: "MV Calypso", status: "Low stock" },
];

export const kpis = [
  { label: "Total stock value", value: "$18.42M", delta: "+2.8%", trend: "up", detail: "Across 3 active yards" },
  { label: "Available materials", value: "12,480", delta: "94.2%", trend: "up", detail: "742 currently reserved" },
  { label: "Low-stock items", value: "38", delta: "+6 today", trend: "down", detail: "11 production-critical" },
  { label: "Pending transfers", value: "17", delta: "5 overdue", trend: "down", detail: "Awaiting yard approval" },
];

export const alerts = [
  { title: "Cu-Ni Pipe · 80mm", meta: "East Basin · NS Atlas", amount: "18 lengths left", level: "critical" },
  { title: "E7018 Welding Electrodes", meta: "Harbor North · MV Calypso", amount: "22 boxes left", level: "warning" },
  { title: "Marine Epoxy Primer", meta: "Dry Dock 4 · OSV Meridian", amount: "31 drums left", level: "warning" },
];

export const transfers = [
  { id: "TR-24091", item: "AH36 Steel Plate", route: "Harbor North → East Basin", qty: "48 sheets", status: "Approval needed", date: "Today, 14:30" },
  { id: "TR-24088", item: "Marine Power Cable", route: "East Basin → Dry Dock 4", qty: "320 m", status: "In transit", date: "Today, 09:10" },
  { id: "TR-24072", item: "A-60 Fire Insulation", route: "Dry Dock 4 → Harbor North", qty: "84 panels", status: "Received", date: "Yesterday" },
  { id: "TR-24069", item: "DN150 Butterfly Valve", route: "Harbor North → Dry Dock 4", qty: "12 units", status: "Dispatched", date: "Mar 18" },
];

export const purchaseOrders = [
  { id: "PO-89142", supplier: "Nordic Marine Steel", material: "AH36 Steel Plate", value: "$284,600", delivery: "Mar 26, 2026", received: 68, status: "Partial receipt" },
  { id: "PO-89118", supplier: "BlueLine Components", material: "Cu-Ni Pipe & fittings", value: "$96,400", delivery: "Mar 20, 2026", received: 0, status: "Overdue" },
  { id: "PO-89094", supplier: "Keystone Electrical", material: "Marine Power Cable", value: "$42,180", delivery: "Apr 02, 2026", received: 0, status: "Confirmed" },
  { id: "PO-89061", supplier: "OceanShield Coatings", material: "Epoxy primer", value: "$31,800", delivery: "Mar 29, 2026", received: 35, status: "Partial receipt" },
];

export const audits = [
  { action: "Stock reservation approved", actor: "Maya Chen", target: "RSV-4831 · MV Calypso", time: "10:42", detail: "72 sheets of AH36 steel" },
  { action: "Material received", actor: "Leo Anders", target: "PO-89142 · Harbor North", time: "09:18", detail: "Batch B-2408-19 verified" },
  { action: "Transfer dispatched", actor: "Priya Nair", target: "TR-24088 · Dry Dock 4", time: "08:51", detail: "Seal ID 009442" },
  { action: "Quality hold applied", actor: "Owen Brooks", target: "VAL-50118", time: "Yesterday", detail: "Dimensional variance review" },
];

export const navItems = [
  "Dashboard",
  "Inventory",
  "Movements",
  "QR Tracking",
  "Ships & Yards",
  "Procurement",
  "AI Analytics",
  "AI Assistant",
  "Quality",
  "Audit Logs",
  "Settings",
] as const;

export type PageName = (typeof navItems)[number];

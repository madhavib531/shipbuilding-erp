export const navItems = [
  "Dashboard",
  "Inventory",
  "Movements",
  "QR Tracking",
  "Ships & Yards",
  "Procurement",
  "Analytics",
  "Assistant",
  "Quality",
  "Audit Logs",
  "Settings",
] as const;

export type PageName = (typeof navItems)[number];

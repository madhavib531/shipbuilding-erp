import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

export type IconName =
  | "dashboard" | "inventory" | "movement" | "qr" | "ship" | "procurement"
  | "analytics" | "assistant" | "quality" | "audit" | "settings" | "search"
  | "bell" | "chevron" | "menu" | "close" | "plus" | "download" | "filter"
  | "arrow" | "more" | "scan" | "check" | "clock" | "warning" | "sparkles"
  | "wifiOff" | "box" | "users" | "lock";

const paths: Record<IconName, ReactNode> = {
  dashboard: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  inventory: <><path d="m4 7 8-4 8 4-8 4-8-4Z"/><path d="m4 7 8 4 8-4v10l-8 4-8-4V7Z"/><path d="M12 11v10"/></>,
  movement: <><path d="M4 7h13"/><path d="m14 4 3 3-3 3"/><path d="M20 17H7"/><path d="m10 14-3 3 3 3"/></>,
  qr: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h4v4h-7v-7Z"/></>,
  ship: <><path d="M3 18h18l-2 3H5l-2-3Z"/><path d="M6 18V8h12v10"/><path d="M9 8V3h6v5"/><path d="M2 22c2-1 3-1 5 0s3 1 5 0 3-1 5 0 3 1 5 0"/></>,
  procurement: <><path d="M4 6h16l-2 14H6L4 6Z"/><path d="M8 6a4 4 0 0 1 8 0"/><path d="M9 11v4M15 11v4"/></>,
  analytics: <><path d="M4 19V9M10 19V5M16 19v-7M22 19V2"/><path d="M2 19h21"/></>,
  assistant: <><path d="M4 5h16v12H8l-4 4V5Z"/><path d="M8 10h8M8 13h5"/></>,
  quality: <><path d="m12 3 8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/></>,
  audit: <><path d="M6 3h12v18H6z"/><path d="M9 8h6M9 12h6M9 16h4"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1l2-1.5-2-3.4-2.4 1a7 7 0 0 0-1.7-1L14.5 3h-5l-.4 3.1a7 7 0 0 0-1.7 1L5 6.1 3 9.5 5.1 11a7 7 0 0 0 0 2L3 14.5l2 3.4 2.4-1a7 7 0 0 0 1.7 1l.4 3.1h5l.4-3.1a7 7 0 0 0 1.7-1l2.4 1 2-3.4-2.1-1.5c.1-.3.1-.7.1-1Z"/></>,
  search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9Z"/><path d="M10 21h4"/></>,
  chevron: <path d="m9 18 6-6-6-6"/>, menu: <path d="M4 7h16M4 12h16M4 17h16"/>,
  close: <path d="m6 6 12 12M18 6 6 18"/>, plus: <path d="M12 5v14M5 12h14"/>,
  download: <><path d="M12 3v12m0 0 4-4m-4 4-4-4"/><path d="M4 19h16"/></>,
  filter: <path d="M4 5h16l-6 7v5l-4 2v-7L4 5Z"/>, arrow: <path d="m5 12 14 0m-5-5 5 5-5 5"/>,
  more: <><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></>,
  scan: <path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5M8 8h8v8H8z"/>,
  check: <path d="m5 12 4 4L19 6"/>, clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  warning: <><path d="M12 3 2 21h20L12 3Z"/><path d="M12 9v5M12 17h.01"/></>,
  sparkles: <><path d="m12 3 1.4 4.6L18 9l-4.6 1.4L12 15l-1.4-4.6L6 9l4.6-1.4L12 3Z"/><path d="m19 16 .7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7L19 16Z"/></>,
  wifiOff: <><path d="m2 8 3 3M22 8a15 15 0 0 0-12-4M5 12a11 11 0 0 1 3-2M19 12a11 11 0 0 0-6-3M8 16a6 6 0 0 1 7-1M12 20h.01"/><path d="m3 3 18 18"/></>,
  box: <><path d="m4 7 8-4 8 4-8 4-8-4Z"/><path d="m4 7 8 4 8-4v10l-8 4-8-4V7Z"/></>,
  users: <><circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2"/><circle cx="18" cy="9" r="2"/><path d="M17 14a5 5 0 0 1 4 5v1"/></>,
  lock: <><rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></>,
};

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

export function Button({ variant = "primary", icon, className = "", children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger"; icon?: IconName }) {
  return <button className={`btn btn-${variant} ${className}`} {...props}>{icon && <Icon name={icon} size={16}/>}<span>{children}</span></button>;
}

export function Input({ icon, className = "", ...props }: InputHTMLAttributes<HTMLInputElement> & { icon?: IconName }) {
  return <label className={`input-wrap ${className}`}>{icon && <Icon name={icon} size={17}/>}<input {...props}/></label>;
}

export function Select({ children, className = "", ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <label className={`select-wrap ${className}`}><select {...props}>{children}</select><Icon name="chevron" size={14}/></label>;
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "success" | "warning" | "danger" | "info" | "purple" }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`card ${className}`}>{children}</section>;
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description: string; actions?: ReactNode }) {
  return <header className="page-header"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h1>{title}</h1><p className="page-description">{description}</p></div>{actions && <div className="page-actions">{actions}</div>}</header>;
}

export function Progress({ value }: { value: number }) {
  return <div className="progress" aria-label={`${value}% complete`}><span style={{ width: `${value}%` }}/></div>;
}

export function StatePanel({ type, onRetry }: { type: "loading" | "empty" | "error"; onRetry?: () => void }) {
  if (type === "loading") return <div className="state-panel"><div className="spinner"/><strong>Loading material records</strong><span>Synchronizing with the local data cache…</span></div>;
  if (type === "error") return <div className="state-panel"><span className="state-icon error"><Icon name="warning"/></span><strong>Records couldn’t be loaded</strong><span>The connection was interrupted. Your local changes are safe.</span><Button variant="secondary" onClick={onRetry}>Try again</Button></div>;
  return <div className="state-panel"><span className="state-icon"><Icon name="box"/></span><strong>No materials found</strong><span>Try adjusting your search or filters.</span></div>;
}

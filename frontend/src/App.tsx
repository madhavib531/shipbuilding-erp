import { useState, useEffect, useCallback, useRef, type FormEvent } from "react";
import {
  navItems,
  type PageName,
} from "./data/mockData";
import {
  Badge,
  Button,
  Card,
  Icon,
  Input,
  PageHeader,
  Progress,
  Select,
  StatePanel,
  Toast,
  useToast,
  type IconName,
} from "./components/ui";
import { getMaterial, getMaterialSummary, getMaterialTransactions, getReferenceData, listMaterials, type ApiMaterial, type MaterialSummary, type MaterialTransaction, type ReferenceData } from "./api/materials";
import { ApiError } from "./api/client";
import { TRANSFER_STATUS_LABEL, getTransferSummary, listTransfers, type Transfer, type TransferStatus, type TransferSummary } from "./api/transfers";
import { MaterialDialog } from "./components/MaterialDialog";
import { TransferDialog } from "./components/TransferDialog";
import { TransferActionDialog } from "./components/TransferActionDialog";
import { InspectionDialog, inspectionTone } from "./components/InspectionDialog";
import { INSPECTION_STATUSES, getInspectionSummary, listInspections, type Inspection, type InspectionStatus, type InspectionSummary } from "./api/inspections";
import { PurchaseOrderDialog } from "./components/PurchaseOrderDialog";
import { PurchaseOrderDetailDialog, orderTone } from "./components/PurchaseOrderDetailDialog";
import { SupplierDialog } from "./components/SupplierDialog";
import { PURCHASE_ORDER_STATUSES, formatMoney, getPurchaseOrderSummary, listPurchaseOrders, type PurchaseOrder, type PurchaseOrderStatus, type PurchaseOrderSummary } from "./api/purchaseOrders";
import { SUPPLIER_STATUSES, listSuppliers, type Supplier, type SupplierStatus } from "./api/suppliers";
import { getMovements, getShipPrograms, getYardOverview, type Movements, type ShipProgram, type YardOverview } from "./api/dashboard";
import { AUDIT_SOURCES, listAuditEvents, type AuditEvent, type AuditSource } from "./api/audit";
import { getHealth } from "./api/health";
import { API_BASE_URL } from "./api/client";
import { getAnalyticsOverview, type AnalyticsOverview } from "./api/analytics";
import { CURRENT_USER } from "./currentUser";

const INVENTORY_PAGE_SIZE = 25;

const MOVEMENT_PAGE_SIZE = 25;

const MOVEMENT_TABS: { label: string; statuses: TransferStatus[] }[] = [
  { label: "All movements", statuses: [] },
  { label: "Approvals", statuses: ["Requested"] },
  { label: "Dispatch", statuses: ["Approved"] },
  { label: "Receipt", statuses: ["Dispatched"] },
  { label: "History", statuses: ["Received", "Rejected", "Cancelled"] },
];

const navIcons: Record<PageName, IconName> = {
  Dashboard: "dashboard",
  Inventory: "inventory",
  Movements: "movement",
  "QR Tracking": "qr",
  "Ships & Yards": "ship",
  Procurement: "procurement",
  Analytics: "analytics",
  Assistant: "assistant",
  Quality: "quality",
  "Audit Logs": "audit",
  Settings: "settings",
};

const statusTone = (status: string) => {
  if (status === "Rejected") return "danger" as const;
  if (["Healthy", "Received", "Confirmed", "Passed", "Active"].includes(status)) return "success" as const;
  if (["Low stock", "Overdue", "Approval needed", "Inspection", "Partial receipt"].includes(status)) return status === "Overdue" ? "danger" as const : "warning" as const;
  return "info" as const;
};

type ApiStatus = { state: "checking" | "online" | "degraded" | "offline"; version?: string; checkedAt?: string };

const apiStatusLabel = (s: ApiStatus) =>
  s.state === "online" ? "API connected" : s.state === "degraded" ? "Database unavailable" : s.state === "offline" ? "API unreachable" : "Checking API…";

const checkedTime = (iso?: string) => (iso ? new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : "");

function Sidebar({ active, onNavigate, open, onClose, lowStockCount, apiStatus }: { active: PageName; onNavigate: (page: PageName) => void; open: boolean; onClose: () => void; lowStockCount: number | null; apiStatus: ApiStatus }) {
  return <>
    {open && <button className="sidebar-scrim" onClick={onClose} aria-label="Close navigation"/>}
    <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
      <div className="brand">
        <span className="brand-mark"><span/></span>
        <span><strong>Dockyard</strong><small>Materials Command</small></span>
        <button className="sidebar-close" onClick={onClose} aria-label="Close navigation"><Icon name="close"/></button>
      </div>
      <nav className="nav-list" aria-label="Primary navigation">
        <p className="nav-label">Workspace</p>
        {navItems.slice(0, 6).map((item) => <button key={item} className={active === item ? "active" : ""} onClick={() => { onNavigate(item); onClose(); }}><Icon name={navIcons[item]}/><span>{item}</span>{item === "Inventory" && !!lowStockCount && <em title={`${lowStockCount} batch${lowStockCount === 1 ? "" : "es"} flagged Low stock`}>{lowStockCount.toLocaleString()}</em>}</button>)}
        <p className="nav-label">Intelligence</p>
        {navItems.slice(6, 8).map((item) => <button key={item} className={active === item ? "active" : ""} onClick={() => { onNavigate(item); onClose(); }}><Icon name={navIcons[item]}/><span>{item}</span></button>)}
        <p className="nav-label">Administration</p>
        {navItems.slice(8).map((item) => <button key={item} className={active === item ? "active" : ""} onClick={() => { onNavigate(item); onClose(); }}><Icon name={navIcons[item]}/><span>{item}</span></button>)}
      </nav>
      <div className="sidebar-footer">
        <div className="sync-row"><span className="sync-dot" style={apiStatus.state === "online" ? undefined : { background: apiStatus.state === "checking" ? "#9aa5b8" : "#d64545" }}/><div><strong>{apiStatusLabel(apiStatus)}</strong><small>{apiStatus.checkedAt ? `Checked ${checkedTime(apiStatus.checkedAt)} · live data, no offline cache` : "Live data, no offline cache"}</small></div></div>
        <div className="version">ERP workspace · API {apiStatus.version ? `v${apiStatus.version}` : "version unknown"}</div>
      </div>
    </aside>
  </>;
}

function Topbar({ onMenu, onNavigate, onSearch, apiStatus }: { onMenu: () => void; onNavigate: (page: PageName) => void; onSearch: (text: string) => void; apiStatus: ApiStatus }) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [text, setText] = useState("");
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setSearchOpen(true); input.current?.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return <header className="topbar">
    <button className="icon-button menu-button" onClick={onMenu} aria-label="Open navigation"><Icon name="menu"/></button>
    <div className={`global-search ${searchOpen ? "search-open" : ""}`} onClick={() => setSearchOpen(true)}>
      <Icon name="search"/><input ref={input} aria-label="Search batches" placeholder="Search batches by ID, name or lot…" value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && text.trim()) { onSearch(text.trim()); setSearchOpen(false); } }}/><kbd>Ctrl K</kbd>
    </div>
    <div className="topbar-actions">
      <div className="offline-pill" title={apiStatus.checkedAt ? `Checked at ${checkedTime(apiStatus.checkedAt)}` : undefined}><Icon name={apiStatus.state === "online" ? "check" : "warning"} size={14}/><span>{apiStatusLabel(apiStatus)}</span></div>
      <Select aria-label="Select yard" disabled title="A global yard selection isn’t available yet — use the yard filters on each page" value=""><option value="">All yards</option></Select>
      <button className="icon-button notification-button" aria-label="Notifications (not available yet)" title="Notifications aren’t available yet" disabled><Icon name="bell"/></button>
      <button className="profile" onClick={() => onNavigate("Settings")}><span className="avatar">{CURRENT_USER.initials}</span><span className="profile-copy"><strong>{CURRENT_USER.name}</strong><small>{CURRENT_USER.role}</small></span><Icon name="chevron" size={14}/></button>
    </div>
  </header>;
}

type KpiView = { value: string; delta: string; tone: "success" | "danger" | "neutral"; detail: string };
type MaterialSummaryState = { data: MaterialSummary | null; error: string };

const DASHBOARD_KPIS: { label: string; icon: IconName }[] = [
  { label: "Total stock value", icon: "analytics" },
  { label: "Available materials", icon: "box" },
  { label: "Low-stock items", icon: "warning" },
  { label: "Pending transfers", icon: "movement" },
];

function materialKpi(label: string, { data: s, error }: MaterialSummaryState): KpiView {
  if (error) return { value: "—", delta: "Unavailable", tone: "neutral", detail: "Material data couldn’t be loaded" };
  if (!s) return { value: "—", delta: "Loading", tone: "neutral", detail: "Loading material counts…" };
  if (label === "Total stock value") {
    return { value: "—", delta: "No cost data", tone: "neutral", detail: `Across ${s.active_yards.toLocaleString()} active yard${s.active_yards === 1 ? "" : "s"}` };
  }
  if (label === "Available materials") {
    return {
      value: s.available_batches.toLocaleString(),
      delta: s.total_batches ? `${s.available_percent}% of batches` : "No batches",
      tone: "neutral",
      detail: `${s.reserved_batches.toLocaleString()} with reserved stock`,
    };
  }
  return {
    value: s.low_stock_batches.toLocaleString(),
    delta: "Flagged manually",
    tone: "neutral",
    detail: `${s.low_stock_ship_allocated.toLocaleString()} Ship-allocated`,
  };
}

function pendingTransfersKpi(summary: TransferSummary | null, error: string): KpiView {
  if (error) return { value: "—", delta: "Unavailable", tone: "neutral", detail: "Transfer data couldn’t be loaded" };
  if (!summary) return { value: "—", delta: "Loading", tone: "neutral", detail: "Loading the transfer queue…" };
  return {
    value: String(summary.pending),
    delta: summary.overdue ? `${summary.overdue} overdue` : "None overdue",
    tone: summary.overdue ? "danger" : "success",
    detail: `${summary.awaiting_approval} to approve · ${summary.ready_to_dispatch} to dispatch · ${summary.in_transit} in transit`,
  };
}

const LOW_STOCK_ALERT_ROWS = 3;

function Dashboard({ onNavigate, materials }: { onNavigate: (page: PageName) => void; materials: MaterialSummaryState }) {
  const [transferSummary, setTransferSummary] = useState<TransferSummary | null>(null);
  const [transferError, setTransferError] = useState("");
  const [lowStock, setLowStock] = useState<{ items: ApiMaterial[]; total: number } | null>(null);
  const [lowStockError, setLowStockError] = useState("");
  const [months, setMonths] = useState(6);
  const [movements, setMovements] = useState<Movements | null>(null);
  const [movementsError, setMovementsError] = useState("");
  const [ships, setShips] = useState<ShipProgram[] | null>(null);
  const [shipsError, setShipsError] = useState("");
  const [delayed, setDelayed] = useState<{ items: PurchaseOrder[]; total: number } | null>(null);
  const [delayedError, setDelayedError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    getTransferSummary(controller.signal)
      .then(setTransferSummary)
      .catch((err) => { if (!controller.signal.aborted) setTransferError(err instanceof Error ? err.message : String(err)); });
    listMaterials({ skip: 0, limit: LOW_STOCK_ALERT_ROWS, status: "Low stock" }, controller.signal)
      .then(({ materials: items, total }) => setLowStock({ items, total }))
      .catch((err) => { if (!controller.signal.aborted) setLowStockError(err instanceof Error ? err.message : String(err)); });
    getShipPrograms(controller.signal)
      .then(setShips)
      .catch((err) => { if (!controller.signal.aborted) setShipsError(err instanceof Error ? err.message : String(err)); });
    listPurchaseOrders({ skip: 0, limit: 200, overdue: true }, controller.signal)
      .then(({ purchase_orders: items, total }) => setDelayed({ items, total }))
      .catch((err) => { if (!controller.signal.aborted) setDelayedError(err instanceof Error ? err.message : String(err)); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setMovements(null);
    getMovements(months, controller.signal)
      .then((m) => { setMovements(m); setMovementsError(""); })
      .catch((err) => { if (!controller.signal.aborted) setMovementsError(err instanceof Error ? err.message : String(err)); });
    return () => controller.abort();
  }, [months]);

  const peak = Math.max(1, ...(movements?.months.flatMap((m) => [m.stock_in, m.stock_out]) ?? []));
  const quiet = movements?.months.every((m) => !m.stock_in && !m.stock_out);
  // Most overdue first: the earliest expected delivery among overdue open orders.
  const worst = delayed?.items.reduce<PurchaseOrder | null>((a, b) => (!a || (b.expected_delivery_date ?? "") < (a.expected_delivery_date ?? "") ? b : a), null) ?? null;
  const hour = new Date().getHours();
  const greeting = `${hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening"}, ${CURRENT_USER.name.split(" ")[0]}`;

  const view = (label: string): KpiView =>
    label === "Pending transfers" ? pendingTransfersKpi(transferSummary, transferError) : materialKpi(label, materials);
  const errorFor = (label: string) => (label === "Pending transfers" ? transferError : materials.error) || undefined;

  return <>
    <PageHeader eyebrow="Operations overview" title={greeting} description="Here’s what needs your attention across all active shipbuilding programs." actions={<><Button variant="secondary" icon="download" disabled title="Export is not available yet">Export report</Button><Button icon="plus" onClick={() => onNavigate("Procurement")}>Receive material</Button></>}/>
    <div className="kpi-grid">
      {DASHBOARD_KPIS.map((kpi, index) => { const v = view(kpi.label); return <Card className="kpi-card" key={kpi.label}><div className={`kpi-icon kpi-${index}`}><Icon name={kpi.icon}/></div><div className="kpi-label">{kpi.label}</div><div className="kpi-value-row"><strong>{v.value}</strong><Badge tone={v.tone}>{v.delta}</Badge></div><p title={errorFor(kpi.label)}>{v.detail}</p></Card>; })}
    </div>
    <div className="dashboard-grid">
      <Card className="chart-card span-2">
        <div className="card-heading"><div><h2>Inventory movement</h2><p title={movements ? `In: ${movements.stock_in_types.join(", ")} · Out: ${movements.stock_out_types.join(", ")}` : undefined}>Ledger entries per month — counted, since batches use different units</p></div><Select aria-label="Movement period" value={String(months)} onChange={(e) => setMonths(Number(e.target.value))}><option value="6">6 months</option><option value="12">12 months</option></Select></div>
        <div className="chart-legend"><span><i className="legend-received"/>Stock in</span><span><i className="legend-consumed"/>Stock out</span></div>
        <div className="bar-chart" aria-busy={!movements && !movementsError}>
          {movementsError && <p className="muted-copy" role="alert" style={{ alignSelf: "center" }}>Movement data couldn’t be loaded.</p>}
          {movements && quiet && <p className="muted-copy" style={{ alignSelf: "center" }}>No stock movements in this period.</p>}
          {movements && !quiet && movements.months.map((m) => {
            const label = new Date(`${m.month}-01T00:00:00`).toLocaleString(undefined, { month: "short" });
            return <div className="bar-group" key={m.month}><div className="bar-pair"><span className="bar received" title={`${label}: ${m.stock_in} in`} style={{ height: `${m.stock_in / peak * 100}%`, minHeight: m.stock_in ? undefined : 0 }}/><span className="bar consumed" title={`${label}: ${m.stock_out} out`} style={{ height: `${m.stock_out / peak * 100}%`, minHeight: m.stock_out ? undefined : 0 }}/></div><small>{label}</small></div>;
          })}
        </div>
      </Card>
      <Card className="alert-card">
        <div className="card-heading"><div><h2>Low-stock alerts</h2><p title={lowStockError || undefined}>{lowStockError ? "Unavailable" : !lowStock ? "Loading…" : `${lowStock.total.toLocaleString()} batch${lowStock.total === 1 ? "" : "es"} flagged Low stock`}</p></div><button className="link-button" onClick={() => onNavigate("Inventory")}>View all</button></div>
        <div className="alert-list">
          {lowStockError && <p className="muted-copy">Low-stock batches couldn’t be loaded.</p>}
          {lowStock && lowStock.items.length === 0 && <p className="muted-copy">No batches are flagged Low stock.</p>}
          {lowStock?.items.map((m) => <button className="alert-row" key={m.id} onClick={() => onNavigate("Inventory")}><span className={`severity ${m.available === 0 ? "critical" : "warning"}`}><Icon name="warning" size={16}/></span><span><strong>{m.name}</strong><small>{m.yard.name} · {m.ship ? `Ship-allocated: ${m.ship.name}` : "Not allocated"}</small></span><span className="alert-amount">{m.available.toLocaleString()} {m.unit} available<Icon name="chevron" size={14}/></span></button>)}
        </div>
      </Card>
      <Card className="consumption-card">
        <div className="card-heading"><div><h2>Ship programs</h2><p>Build progress and allocated batches · consumption isn’t tracked yet</p></div><button className="icon-button" aria-label="Open Ships & Yards" onClick={() => onNavigate("Ships & Yards")}><Icon name="more"/></button></div>
        <div className="ship-list">
          {shipsError && <p className="muted-copy" role="alert">Ship programs couldn’t be loaded.</p>}
          {ships && ships.length === 0 && <p className="muted-copy">No ships are recorded.</p>}
          {ships?.map((ship) => <div className="ship-row" key={ship.id}><div className="ship-avatar"><Icon name="ship"/></div><div className="ship-progress"><span><strong>{ship.name}</strong><b>{ship.allocated_batches} batch{ship.allocated_batches === 1 ? "" : "es"}</b></span><small>{ship.build_status} · {ship.build_progress}% complete · {ship.yard}</small><Progress value={ship.build_progress}/></div></div>)}
        </div>
      </Card>
      <Card className="recommendation-card span-2">
        <div className="recommendation-head"><span className="ai-mark"><Icon name="sparkles"/></span><div><span className="eyebrow">AI recommendation</span><h2>No recommendations available</h2></div><Badge tone="neutral">Not connected</Badge></div>
        <p>No AI model is connected, so no reallocation or purchasing suggestions are generated. Nothing on this card is computed from your data yet.</p>
        <div className="recommendation-actions"><span><Icon name="lock" size={14}/> Any future suggestion will require human approval before it changes stock</span></div>
      </Card>
      <Card className="orders-card">
        <div className="card-heading"><div><h2>Delayed orders</h2><p title={delayedError || undefined}>{delayedError ? "Unavailable" : !delayed ? "Loading…" : delayed.total ? `${delayed.total} require${delayed.total === 1 ? "s" : ""} supplier follow-up` : "No orders past their delivery date"}</p></div><button className="link-button" onClick={() => onNavigate("Procurement")}>View orders</button></div>
        {delayed && !worst && <div className="order-summary"><strong>None</strong><Badge tone="success">On time</Badge></div>}
        {worst && <>
          <div className="order-summary"><strong>{formatMoney(worst.outstanding_value, worst.currency)}</strong><Badge tone="danger">Overdue</Badge></div>
          <p className="muted-copy">{worst.supplier.name} · {worst.display_id}</p>
          <div className="date-row"><span>Expected {formatDay(worst.expected_delivery_date!)}</span><strong>{deliveryNote(worst).replace(" overdue", " late")}</strong></div>
          <Progress value={worst.ordered_quantity ? Math.round(worst.received_quantity / worst.ordered_quantity * 100) : 0}/>
        </>}
      </Card>
    </div>
  </>;
}

function Inventory({ onMaterialsChanged, searchRequest }: { onMaterialsChanged: () => void; searchRequest: { text: string; n: number } | null }) {
  const [query, setQuery] = useState(searchRequest?.text ?? "");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [yard, setYard] = useState("");
  const [skip, setSkip] = useState(0);
  const [state, setState] = useState<"ready" | "loading" | "empty" | "error">("loading");
  const [loadError, setLoadError] = useState("");
  const [dialog, setDialog] = useState<{ material?: ApiMaterial } | null>(null);
  const [toast, act] = useToast();
  const [items, setItems] = useState<ApiMaterial[]>([]);
  const [total, setTotal] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);
  const [refs, setRefs] = useState<ReferenceData | null>(null);
  const [refsError, setRefsError] = useState("");

  useEffect(() => {
    const id = window.setTimeout(() => { setSearch(query.trim()); setSkip(0); }, 300);
    return () => window.clearTimeout(id);
  }, [query]);

  // A search typed in the top bar while Inventory is already open.
  useEffect(() => { if (searchRequest) setQuery(searchRequest.text); }, [searchRequest]);

  useEffect(() => {
    const controller = new AbortController();
    getReferenceData(controller.signal)
      .then(setRefs)
      .catch((err) => { if (!controller.signal.aborted) setRefsError(`Categories, yards and ships could not be loaded: ${err.message}`); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    listMaterials({ skip, limit: INVENTORY_PAGE_SIZE, search, category, yard }, controller.signal)
      .then(({ materials: loaded, total: count }) => {
        setItems(loaded);
        setTotal(count);
        setState(loaded.length === 0 ? "empty" : "ready");
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setLoadError(err instanceof Error ? err.message : String(err));
        setState("error");
      });
    return () => controller.abort();
  }, [skip, search, category, yard, reloadKey]);

  const afterSave = (message: string) => { setDialog(null); act(message); setReloadKey((k) => k + 1); onMaterialsChanged(); };
  const firstShown = total === 0 ? 0 : skip + 1;
  return <>
    <PageHeader eyebrow="Material control" title="Inventory" description="Track, reserve and issue materials across yards and ship programs." actions={<><Button variant="secondary" icon="download" disabled title="Export is not available yet">Export</Button><Button icon="plus" onClick={() => setDialog({})}>Add material</Button></>}/>
    <Card className="table-card">
      <div className="table-toolbar">
        <Input icon="search" placeholder="Search by material ID, name or batch…" value={query} onChange={(e) => setQuery(e.target.value)}/>
        <div className="toolbar-filters"><Select aria-label="Filter by category" value={category} onChange={(e) => { setCategory(e.target.value); setSkip(0); }}><option value="">All categories</option>{refs?.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select><Select aria-label="Filter by yard" value={yard} onChange={(e) => { setYard(e.target.value); setSkip(0); }}><option value="">All yards</option>{refs?.yards.map((y) => <option key={y.id} value={y.id}>{y.name}</option>)}</Select><Button variant="secondary" icon="filter" disabled title="Additional filters are not available yet">Filters</Button></div>
      </div>
      {state === "error" && <div className="notice" role="alert"><Icon name="warning"/>{loadError}</div>}
      {state !== "ready" ? <StatePanel type={state} onRetry={() => setReloadKey((k) => k + 1)}/> : <div className="table-scroll"><table><thead><tr><th>Material</th><th>Batch</th><th>Stock</th><th>Allocation</th><th>Location</th><th>Status</th><th aria-label="Actions"/></tr></thead><tbody>{items.map(item => <tr key={item.id}><td><div className="material-name"><span className="material-icon"><Icon name="box"/></span><span><strong>{item.name}</strong><small>{item.id} · {item.category.name}</small></span></div></td><td><strong className="mono">{item.batch}</strong><small>{item.quantity} {item.unit} total</small></td><td><strong>{item.available}</strong><small>{item.reserved} reserved{item.held_quantity ? ` · ${item.held_quantity} on inspection hold` : ""}</small></td><td><strong>{item.ship?.name ?? "Unassigned"}</strong><small>{item.quantity ? Math.round(item.reserved / item.quantity * 100) : 0}% allocated</small></td><td><strong>{item.yard.name}</strong><small>{item.location ? `Zone ${item.location.zone}` : "No location"}</small></td><td><Badge tone={statusTone(item.status)}>{item.status}</Badge></td><td><button className="icon-button" aria-label={`Edit ${item.id}`} title="Edit or delete" onClick={() => setDialog({ material: item })}><Icon name="more"/></button></td></tr>)}</tbody></table></div>}
      <div className="table-footer"><span>{state === "ready" ? `Showing ${firstShown}–${skip + items.length} of ${total} materials` : `${total} materials`}</span><div><Button variant="ghost" disabled={skip === 0 || state === "loading"} onClick={() => setSkip(Math.max(0, skip - INVENTORY_PAGE_SIZE))}>Previous</Button><Button variant="secondary" disabled={skip + items.length >= total || state === "loading"} onClick={() => setSkip(skip + INVENTORY_PAGE_SIZE)}>Next</Button></div></div>
    </Card>
    {dialog && <MaterialDialog material={dialog.material} refs={refs} refsError={refsError} onClose={() => setDialog(null)} onDone={afterSave}/>}
    <Toast message={toast}/>
  </>;
}

const MOVEMENT_ACTION: Partial<Record<TransferStatus, string>> = { Requested: "Review", Approved: "Dispatch", Dispatched: "Receive" };

const formatMoment = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

/** Ledger quantity as displayed. Manual adjustments (no reference document) are signed: +5 added, −3 removed,
 * 0 when only available/reserved moved. Everything else, including transit-shortage write-offs, is shown as recorded. */
const ledgerQuantity = (type: string, quantity: number, reference: string | null) =>
  type === "Adjustment" && !reference ? (quantity > 0 ? `+${quantity}` : quantity < 0 ? `−${-quantity}` : "0") : String(quantity);

function Movements() {
  const [tab, setTab] = useState(MOVEMENT_TABS[0]);
  const [skip, setSkip] = useState(0);
  const [state, setState] = useState<"ready" | "loading" | "empty" | "error">("loading");
  const [loadError, setLoadError] = useState("");
  const [items, setItems] = useState<Transfer[]>([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<TransferSummary | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [refs, setRefs] = useState<ReferenceData | null>(null);
  const [refsError, setRefsError] = useState("");
  const [creating, setCreating] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const [toast, showToast] = useToast();

  useEffect(() => {
    const controller = new AbortController();
    getReferenceData(controller.signal)
      .then(setRefs)
      .catch((err) => { if (!controller.signal.aborted) setRefsError(`Yards and locations could not be loaded: ${err.message}`); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    getTransferSummary(controller.signal).then(setSummary).catch(() => { if (!controller.signal.aborted) setSummary(null); });
    listTransfers(tab.statuses, { skip, limit: MOVEMENT_PAGE_SIZE }, controller.signal)
      .then(({ transfers, total: count }) => {
        setItems(transfers);
        setTotal(count);
        setState(transfers.length === 0 ? "empty" : "ready");
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setLoadError(err instanceof Error ? err.message : String(err));
        setState("error");
      });
    return () => controller.abort();
  }, [tab, skip, reloadKey]);

  const done = useCallback((message: string) => {
    setCreating(false);
    setOpenId(null);
    showToast(message);
    setReloadKey((k) => k + 1);
  }, [showToast]);

  const kpi = (value: number | undefined) => (summary ? String(value) : "—");
  const cards: [string, string, "warning" | "info" | "purple" | "success"][] = [
    ["Awaiting approval", kpi(summary?.awaiting_approval), "warning"],
    ["In transit", kpi(summary?.in_transit), "info"],
    ["Due today", kpi(summary?.due_today), "purple"],
    ["Received this week", kpi(summary?.received_this_week), "success"],
  ];

  return <><PageHeader eyebrow="Material logistics" title="Movements" description="Approve, dispatch and receive transfers between yards." actions={<Button icon="plus" onClick={() => setCreating(true)}>Create transfer</Button>}/>
    <div className="mini-kpis">{cards.map(([label, value, tone]) => <Card key={label}><span>{label}</span><strong>{value}</strong><Badge tone={tone}>Live queue</Badge></Card>)}</div>
    <Card className="table-card"><div className="tabs">{MOVEMENT_TABS.map(item => <button className={tab.label === item.label ? "active" : ""} onClick={() => { setTab(item); setSkip(0); }} key={item.label}>{item.label}</button>)}</div>
      {state === "error" && <div className="notice" role="alert" style={{ marginTop: 14 }}><Icon name="warning"/>{loadError}</div>}
      {state !== "ready"
        ? <StatePanel type={state} onRetry={() => setReloadKey((k) => k + 1)} title={state === "loading" ? "Loading transfers" : state === "empty" ? "No transfers here" : "Transfers couldn’t be loaded"} message={state === "loading" ? "Fetching the movement queue…" : state === "empty" ? "Use Create transfer to move available stock between yards or locations." : undefined}/>
        : <div className="movement-list">{items.map(t => {
          const label = TRANSFER_STATUS_LABEL[t.status];
          const last = t.events[t.events.length - 1];
          const action = MOVEMENT_ACTION[t.status];
          return <div className="movement-row" key={t.id}><span className="movement-icon"><Icon name="movement"/></span><div className="movement-main"><span><strong>{t.material.name}</strong><Badge tone={statusTone(label)}>{label}</Badge></span><p>{t.from_yard.name}{t.from_location ? ` (Zone ${t.from_location.zone})` : ""} → {t.to_yard.name}{t.to_location ? ` (Zone ${t.to_location.zone})` : ""}</p></div><div><strong>{t.quantity} {t.unit}</strong><small>{t.display_id}</small></div><div><strong>{last ? formatMoment(last.created_at) : formatMoment(t.updated_at)}</strong><small>Updated by {last?.actor ?? t.requested_by}</small></div><Button variant={t.status === "Requested" ? "primary" : "secondary"} onClick={() => setOpenId(t.id)}>{action ?? "Details"}</Button></div>;
        })}</div>}
      <div className="table-footer"><span>{state === "ready" ? `Showing ${skip + 1}–${skip + items.length} of ${total} transfers` : `${total} transfers`}</span><div><Button variant="ghost" disabled={skip === 0 || state === "loading"} onClick={() => setSkip(Math.max(0, skip - MOVEMENT_PAGE_SIZE))}>Previous</Button><Button variant="secondary" disabled={skip + items.length >= total || state === "loading"} onClick={() => setSkip(skip + MOVEMENT_PAGE_SIZE)}>Next</Button></div></div>
    </Card>
    {creating && <TransferDialog refs={refs} refsError={refsError} onClose={() => setCreating(false)} onDone={done}/>}
    {openId !== null && <TransferActionDialog transferId={openId} tone={statusTone} onClose={() => setOpenId(null)} onDone={done}/>}
    <Toast message={toast}/>
  </>;
}

type Lookup =
  | { phase: "idle" | "searching" }
  | { phase: "error" | "none"; message: string }
  | { phase: "choose"; matches: ApiMaterial[]; total: number }
  | { phase: "found"; material: ApiMaterial; history: MaterialTransaction[] | null; historyTotal: number; historyError: string };

const HISTORY_ROWS = 15;

function QRTracking() {
  const [lookup, setLookup] = useState("");
  const [result, setResult] = useState<Lookup>({ phase: "idle" });

  const show = async (material: ApiMaterial) => {
    setResult({ phase: "found", material, history: null, historyTotal: 0, historyError: "" });
    try {
      const { transactions, total } = await getMaterialTransactions(material.id, HISTORY_ROWS);
      setResult({ phase: "found", material, history: transactions, historyTotal: total, historyError: "" });
    } catch (err) {
      setResult({ phase: "found", material, history: [], historyTotal: 0, historyError: err instanceof Error ? err.message : String(err) });
    }
  };

  const search = async (event: FormEvent) => {
    event.preventDefault();
    const q = lookup.trim();
    if (!q) return setResult({ phase: "none", message: "Enter a batch ID, name or lot number." });
    setResult({ phase: "searching" });
    try {
      const { materials: matches, total } = await listMaterials({ skip: 0, limit: 10, search: q });
      const exact = matches.find((c) => c.id.toLowerCase() === q.toLowerCase());
      if (exact || matches.length === 1) return await show(exact ?? matches[0]);
      if (total > matches.length) {
        // The exact ID may sit beyond the first page of partial matches.
        try { return await show(await getMaterial(q)); } catch (err) { if (!(err instanceof ApiError && err.status === 404)) throw err; }
      }
      if (!matches.length) return setResult({ phase: "none", message: `No batch matches “${q}”.` });
      setResult({ phase: "choose", matches, total });
    } catch (err) {
      setResult({ phase: "error", message: err instanceof Error ? err.message : String(err) });
    }
  };

  const m = result.phase === "found" ? result.material : null;
  const last = result.phase === "found" ? result.history?.[0] : undefined;
  return <><PageHeader eyebrow="Traceability" title="QR tracking" description="Look up material identity, custody and allocation records."/>
    <div className="two-column"><Card className="scanner-card"><span className="scanner-corners"><Icon name="scan" size={42}/></span><h2>QR scanning not available</h2><p>Camera scanning isn’t set up: it needs a QR-scanning library that hasn’t been approved yet.</p><Button variant="secondary" disabled>Camera unavailable</Button><small>Use manual lookup — a scanned label would resolve to the same batch ID.</small></Card>
    <Card><div className="card-heading"><div><h2>Manual lookup</h2><p>Enter a batch ID, or search by name or lot number</p></div></div>
      <form className="lookup-row" onSubmit={search}><Input aria-label="Batch ID, name or lot number" placeholder="e.g. PO-00001-1" value={lookup} onChange={(e) => setLookup(e.target.value)}/><Button type="submit" disabled={result.phase === "searching"}>{result.phase === "searching" ? "Looking up…" : "Look up"}</Button></form>
      {result.phase === "error" && <div className="notice" role="alert" style={{ margin: "16px 0 0" }}><Icon name="warning"/>{result.message}</div>}
      {result.phase === "choose" && <div className="material-detail"><p>{result.total > result.matches.length ? `Showing the first ${result.matches.length} of ${result.total} matches — refine the search or choose one` : `${result.total} batches match — choose one`}</p><div className="alert-list">{result.matches.map((c) => <button type="button" className="alert-row" key={c.id} onClick={() => show(c)}><span className="severity warning"><Icon name="box" size={16}/></span><span><strong>{c.name}</strong><small>{c.id} · Lot {c.batch} · {c.yard.name}</small></span><span className="alert-amount">{c.available} {c.unit} available<Icon name="chevron" size={14}/></span></button>)}</div></div>}
      {m ? <div className="material-detail">
        <Badge tone={statusTone(m.status)}>{m.status}</Badge><h3>{m.name}</h3><p>{m.id} · Batch {m.batch} · {m.category.name}</p>
        <dl>
          <div><dt>Available</dt><dd>{m.available} {m.unit}</dd></div>
          <div><dt>On hand</dt><dd>{m.quantity} {m.unit}{m.reserved ? ` · ${m.reserved} reserved` : ""}{m.held_quantity ? ` · ${m.held_quantity} on inspection hold` : ""}</dd></div>
          <div><dt>Yard</dt><dd>{m.yard.name}{m.location ? ` · Zone ${m.location.zone}, aisle ${m.location.aisle}` : ""}</dd></div>
          <div><dt>Allocated ship</dt><dd>{m.ship?.name ?? "Unassigned"}</dd></div>
          <div style={{ gridColumn: "1 / -1" }}><dt>Last movement</dt><dd>{result.phase === "found" && result.history === null ? "Loading…" : last ? `${last.transaction_type} · ${ledgerQuantity(last.transaction_type, last.quantity, last.reference_id)} ${last.unit} · ${formatMoment(last.created_at)}${last.reference_id ? ` · ${last.reference_id}` : ""}` : "No movements recorded"}</dd></div>
        </dl>
        {result.phase === "found" && result.historyError && <p role="alert">Custody history couldn’t be loaded: {result.historyError}</p>}
        {result.phase === "found" && !!result.history?.length && <><p style={{ marginTop: 16 }}>Custody history{result.historyTotal > result.history.length ? ` · latest ${result.history.length} of ${result.historyTotal}` : ""}</p>
          <div className="audit-timeline" style={{ padding: 0 }} aria-label="Custody history">{result.history.map((t) => <div className="audit-event" key={t.id}><span className="audit-dot"><Icon name="check" size={14}/></span><div><strong>{t.transaction_type} · {ledgerQuantity(t.transaction_type, t.quantity, t.reference_id)} {t.unit}</strong><p>{t.actor}{t.reference_id ? ` · ${t.reference_id}` : ""}{t.reason ? ` · ${t.reason}` : ""}</p></div><div><small>{formatMoment(t.created_at)}</small></div></div>)}</div></>}
      </div> : (result.phase === "idle" || result.phase === "searching" || result.phase === "none") && <div className="lookup-empty"><Icon name="qr" size={28}/><strong>{result.phase === "none" ? result.message : "Awaiting batch ID"}</strong><span>Material details and custody history will appear here.</span></div>}
    </Card></div>
  </>;
}

const PROCUREMENT_PAGE_SIZE = 25;

const supplierTone = (status: string) =>
  status === "Approved" ? "success" as const : status === "Blocked" ? "danger" as const : status === "Inactive" ? "neutral" as const : "warning" as const;

const formatDay = (day: string) =>
  new Date(`${day}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });

function deliveryNote(po: PurchaseOrder) {
  if (!po.expected_delivery_date) return "No date set";
  if (po.is_overdue) {
    const days = Math.floor((Date.now() - new Date(`${po.expected_delivery_date}T00:00:00`).getTime()) / 86_400_000);
    return `${days} day${days === 1 ? "" : "s"} overdue`;
  }
  return po.status === "Draft" ? "Planned date" : ["Approved", "Partially received"].includes(po.status) ? "Expected" : "Delivery date";
}

function ProcurementOrders({ suppliers, reloadKey, onOpen }: { suppliers: Supplier[]; reloadKey: number; onOpen: (id: number) => void }) {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [statusFilter, setStatusFilter] = useState<PurchaseOrderStatus | "">("");
  const [skip, setSkip] = useState(0);
  const [state, setState] = useState<"ready" | "loading" | "empty" | "error">("loading");
  const [loadError, setLoadError] = useState("");
  const [items, setItems] = useState<PurchaseOrder[]>([]);
  const [total, setTotal] = useState(0);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    const id = window.setTimeout(() => { setSearch(query.trim()); setSkip(0); }, 300);
    return () => window.clearTimeout(id);
  }, [query]);

  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    listPurchaseOrders({ skip, limit: PROCUREMENT_PAGE_SIZE, search, supplierId, status: statusFilter || undefined }, controller.signal)
      .then(({ purchase_orders, total: count }) => { setItems(purchase_orders); setTotal(count); setState(purchase_orders.length ? "ready" : "empty"); })
      .catch((err) => { if (!controller.signal.aborted) { setLoadError(err instanceof Error ? err.message : String(err)); setState("error"); } });
    return () => controller.abort();
  }, [skip, search, supplierId, statusFilter, reloadKey, retryKey]);

  const firstShown = total === 0 ? 0 : skip + 1;
  return <>
    <div className="table-toolbar">
      <Input icon="search" placeholder="Search PO number, supplier, material or part number…" value={query} onChange={(e) => setQuery(e.target.value)}/>
      <div className="toolbar-filters">
        <Select aria-label="Filter by supplier" value={supplierId} onChange={(e) => { setSupplierId(e.target.value); setSkip(0); }}><option value="">All suppliers</option>{suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select>
        <Select aria-label="Filter by status" value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value as PurchaseOrderStatus | ""); setSkip(0); }}><option value="">All statuses</option>{PURCHASE_ORDER_STATUSES.map((s) => <option key={s}>{s}</option>)}</Select>
      </div>
    </div>
    {state === "error" && <div className="notice" role="alert" style={{ marginTop: 14 }}><Icon name="warning"/>{loadError}</div>}
    {state !== "ready"
      ? <StatePanel type={state} onRetry={() => setRetryKey((k) => k + 1)} title={state === "loading" ? "Loading purchase orders" : state === "empty" ? "No purchase orders here" : "Purchase orders couldn’t be loaded"} message={state === "loading" ? "Fetching orders…" : state === "empty" ? "Use New purchase order to raise a draft for an approved supplier." : undefined}/>
      : <div className="table-scroll"><table><thead><tr><th>Purchase order</th><th>Supplier</th><th>Material</th><th>Delivery</th><th>Receipt</th><th>Status</th></tr></thead><tbody>{items.map((po) => {
        const pct = po.ordered_quantity ? Math.round(po.received_quantity / po.ordered_quantity * 100) : 0;
        return <tr key={po.id}>
          <td><button className="link-button mono" style={{ padding: 0, fontSize: 10 }} onClick={() => onOpen(po.id)}>{po.display_id}</button><small>{po.lines.length ? formatMoney(po.total_value, po.currency) : "No lines yet"}</small></td>
          <td><strong>{po.supplier.name}</strong><small>{po.supplier.status} supplier</small></td>
          <td><strong>{po.lines[0]?.description ?? "—"}</strong><small>{po.lines.length > 1 ? `+${po.lines.length - 1} more line${po.lines.length === 2 ? "" : "s"}` : po.lines[0]?.category.name ?? "Draft without lines"}</small></td>
          <td><strong>{po.expected_delivery_date ? formatDay(po.expected_delivery_date) : "—"}</strong><small>{deliveryNote(po)}</small></td>
          <td><strong>{pct}% received</strong><Progress value={pct}/></td>
          <td><Badge tone={po.is_overdue ? "danger" : orderTone(po.status)}>{po.is_overdue ? "Overdue" : po.status}</Badge></td>
        </tr>;
      })}</tbody></table></div>}
    <div className="table-footer"><span>{state === "ready" ? `Showing ${firstShown}–${skip + items.length} of ${total} purchase orders` : `${total} purchase orders`}</span><div><Button variant="ghost" disabled={skip === 0 || state === "loading"} onClick={() => setSkip(Math.max(0, skip - PROCUREMENT_PAGE_SIZE))}>Previous</Button><Button variant="secondary" disabled={skip + items.length >= total || state === "loading"} onClick={() => setSkip(skip + PROCUREMENT_PAGE_SIZE)}>Next</Button></div></div>
  </>;
}

function ProcurementSuppliers({ reloadKey, onEdit }: { reloadKey: number; onEdit: (supplier?: Supplier) => void }) {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<SupplierStatus | "">("");
  const [skip, setSkip] = useState(0);
  const [state, setState] = useState<"ready" | "loading" | "empty" | "error">("loading");
  const [loadError, setLoadError] = useState("");
  const [items, setItems] = useState<Supplier[]>([]);
  const [total, setTotal] = useState(0);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    const id = window.setTimeout(() => { setSearch(query.trim()); setSkip(0); }, 300);
    return () => window.clearTimeout(id);
  }, [query]);

  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    listSuppliers({ skip, limit: PROCUREMENT_PAGE_SIZE, search, status: statusFilter || undefined }, controller.signal)
      .then(({ suppliers, total: count }) => { setItems(suppliers); setTotal(count); setState(suppliers.length ? "ready" : "empty"); })
      .catch((err) => { if (!controller.signal.aborted) { setLoadError(err instanceof Error ? err.message : String(err)); setState("error"); } });
    return () => controller.abort();
  }, [skip, search, statusFilter, reloadKey, retryKey]);

  const firstShown = total === 0 ? 0 : skip + 1;
  return <>
    <div className="table-toolbar">
      <Input icon="search" placeholder="Search by ID, name, contact or country…" value={query} onChange={(e) => setQuery(e.target.value)}/>
      <div className="toolbar-filters">
        <Select aria-label="Filter by supplier status" value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value as SupplierStatus | ""); setSkip(0); }}><option value="">All statuses</option>{SUPPLIER_STATUSES.map((s) => <option key={s}>{s}</option>)}</Select>
        <Button variant="secondary" icon="plus" onClick={() => onEdit()}>Add supplier</Button>
      </div>
    </div>
    {state === "error" && <div className="notice" role="alert" style={{ marginTop: 14 }}><Icon name="warning"/>{loadError}</div>}
    {state !== "ready"
      ? <StatePanel type={state} onRetry={() => setRetryKey((k) => k + 1)} title={state === "loading" ? "Loading suppliers" : state === "empty" ? "No suppliers here" : "Suppliers couldn’t be loaded"} message={state === "loading" ? "Fetching the supplier directory…" : state === "empty" ? "Use Add supplier to register a vendor before raising purchase orders." : undefined}/>
      : <div className="table-scroll"><table><thead><tr><th>Supplier</th><th>Contact</th><th>Country</th><th>Status</th><th aria-label="Actions"/></tr></thead><tbody>{items.map((s) => <tr key={s.id}>
        <td><strong>{s.name}</strong><small>{s.id}</small></td>
        <td><strong>{s.contact_person ?? "—"}</strong><small>{[s.contact_email, s.contact_phone].filter(Boolean).join(" · ") || "No contact details"}</small></td>
        <td><strong>{s.country ?? "—"}</strong></td>
        <td><Badge tone={supplierTone(s.status)}>{s.status}</Badge></td>
        <td><button className="icon-button" aria-label={`Edit ${s.id}`} title="Edit supplier" onClick={() => onEdit(s)}><Icon name="more"/></button></td>
      </tr>)}</tbody></table></div>}
    <div className="table-footer"><span>{state === "ready" ? `Showing ${firstShown}–${skip + items.length} of ${total} suppliers` : `${total} suppliers`}</span><div><Button variant="ghost" disabled={skip === 0 || state === "loading"} onClick={() => setSkip(Math.max(0, skip - PROCUREMENT_PAGE_SIZE))}>Previous</Button><Button variant="secondary" disabled={skip + items.length >= total || state === "loading"} onClick={() => setSkip(skip + PROCUREMENT_PAGE_SIZE)}>Next</Button></div></div>
  </>;
}

function Procurement({ onMaterialsChanged }: { onMaterialsChanged: () => void }) {
  const [tab, setTab] = useState<"orders" | "suppliers">("orders");
  const [refs, setRefs] = useState<ReferenceData | null>(null);
  const [refsError, setRefsError] = useState("");
  const [summary, setSummary] = useState<PurchaseOrderSummary | null>(null);
  const [summaryError, setSummaryError] = useState("");
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [reloadKey, setReloadKey] = useState(0);
  const [creating, setCreating] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const [supplierDialog, setSupplierDialog] = useState<{ supplier?: Supplier } | null>(null);
  const [toast, showToast] = useToast();

  useEffect(() => {
    const controller = new AbortController();
    getReferenceData(controller.signal)
      .then(setRefs)
      .catch((err) => { if (!controller.signal.aborted) setRefsError(`Categories, yards and locations could not be loaded: ${err.message}`); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    getPurchaseOrderSummary(controller.signal)
      .then((s) => { setSummary(s); setSummaryError(""); })
      .catch((err) => { if (!controller.signal.aborted) { setSummary(null); setSummaryError(err instanceof Error ? err.message : String(err)); } });
    listSuppliers({ skip: 0, limit: 200 }, controller.signal)
      .then(({ suppliers: all }) => setSuppliers(all))
      .catch(() => { if (!controller.signal.aborted) setSuppliers([]); });
    return () => controller.abort();
  }, [reloadKey]);

  const changed = useCallback((message: string) => {
    showToast(message);
    setReloadKey((k) => k + 1);
    onMaterialsChanged();  // receipts change stock
  }, [showToast, onMaterialsChanged]);

  const live = (value: number | undefined) => (summary ? String(value) : "—");
  const badge = summaryError ? "Unavailable" : summary ? "Live" : "Loading";
  const [firstValue, ...otherValues] = summary?.open_value ?? [];
  const openValue = !summary ? "—" : firstValue ? formatMoney(firstValue.amount, firstValue.currency) : formatMoney(0, null);
  const cards: [string, string, string, "info" | "purple" | "warning" | "danger"][] = [
    ["Open PO value", openValue, otherValues.length ? `+${otherValues.length} currenc${otherValues.length === 1 ? "y" : "ies"}` : badge, "info"],
    ["Due this week", live(summary?.due_this_week), badge, "purple"],
    ["Partial receipts", live(summary?.partially_received), badge, "warning"],
    ["Overdue orders", live(summary?.overdue), badge, "danger"],
  ];

  return <><PageHeader eyebrow="Supply chain" title="Procurement" description="Monitor suppliers, purchase orders and inbound delivery performance." actions={<Button icon="plus" onClick={() => setCreating(true)}>New purchase order</Button>}/>
    <div className="mini-kpis">{cards.map(([label, value, b, tone]) => <Card key={label}><span>{label}</span><strong title={label === "Open PO value" && otherValues.length ? summary!.open_value.map((v) => formatMoney(v.amount, v.currency)).join(" · ") : undefined}>{value}</strong><Badge tone={b === "Unavailable" || b === "Loading" ? "neutral" : tone}>{b}</Badge></Card>)}</div>
    <Card className="table-card">
      <div className="tabs"><button className={tab === "orders" ? "active" : ""} onClick={() => setTab("orders")}>Purchase orders</button><button className={tab === "suppliers" ? "active" : ""} onClick={() => setTab("suppliers")}>Suppliers</button></div>
      {tab === "orders"
        ? <ProcurementOrders suppliers={suppliers} reloadKey={reloadKey} onOpen={setOpenId}/>
        : <ProcurementSuppliers reloadKey={reloadKey} onEdit={(supplier) => setSupplierDialog({ supplier })}/>}
    </Card>
    {creating && <PurchaseOrderDialog refs={refs} refsError={refsError} onClose={() => setCreating(false)} onDone={(message, id) => { setCreating(false); changed(message); setOpenId(id); }}/>}
    {openId !== null && <PurchaseOrderDetailDialog orderId={openId} refs={refs} refsError={refsError} onClose={() => setOpenId(null)} onChanged={changed}/>}
    {supplierDialog && <SupplierDialog supplier={supplierDialog.supplier} onClose={() => setSupplierDialog(null)} onDone={(message) => { setSupplierDialog(null); changed(message); }}/>}
    <Toast message={toast}/>
  </>;
}

const pct = (ratio: number | null) => (ratio === null ? "—" : `${Math.round(ratio * 1000) / 10}%`);
const leadTime = (hours: number | null) => (hours === null ? "—" : hours >= 48 ? `${(hours / 24).toFixed(1)} days` : `${hours.toFixed(1)} h`);

function Analytics({ onNavigate }: { onNavigate: (page: PageName) => void }) {
  const [data, setData] = useState<AnalyticsOverview | null>(null);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setError("");
    getAnalyticsOverview(controller.signal)
      .then(setData)
      .catch((err) => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err)); });
    return () => controller.abort();
  }, [reloadKey]);

  const header = <PageHeader eyebrow="Decision support" title="Analytics" description="Figures computed directly from your live records with fixed rules. No AI model is used and nothing is forecast." actions={<Badge tone="neutral">{data ? `Rule-based · computed ${formatMoment(data.generated_at)}` : "Rule-based"}</Badge>}/>;
  if (error) return <>{header}<Card><StatePanel type="error" title="Analytics couldn’t be loaded" message={error} onRetry={() => setReloadKey((k) => k + 1)}/></Card></>;
  if (!data) return <>{header}<Card><StatePanel type="loading" title="Computing analytics" message="Reading live records…"/></Card></>;

  const flagged = data.attention.filter((a) => a.count > 0);
  const agingTotal = data.aging.reduce((n, a) => n + a.batches, 0);
  const t = data.transfers, q = data.inspections;
  return <>{header}
    <div className="analytics-grid">
      <Card className="span-2"><div className="card-heading"><div><h2>Stock by category</h2><p>Batches per category; quantities aren’t summed because units differ</p></div></div>
        {data.categories.length === 0 ? <p className="muted-copy" style={{ marginTop: 16 }}>No batches recorded yet.</p>
          : <div className="table-scroll" style={{ marginTop: 12 }}><table><thead><tr><th>Category</th><th>Batches</th><th>With available stock</th><th>With reserved stock</th><th>Stock, none available</th></tr></thead>
            <tbody>{data.categories.map((c) => <tr key={c.category}><td><strong>{c.category}</strong></td><td>{c.batches}</td><td>{c.with_available}</td><td>{c.with_reserved}</td><td>{c.stock_but_none_available}</td></tr>)}</tbody></table></div>}
      </Card>
      <Card><div className="card-heading"><div><h2>Needs attention</h2><p>Records flagged by fixed rules</p></div><Badge tone={flagged.length ? "warning" : "success"}>{flagged.length ? `${flagged.reduce((n, a) => n + a.count, 0)} flagged` : "None"}</Badge></div>
        {flagged.length === 0 && <p className="muted-copy" style={{ marginTop: 16 }}>Nothing is flagged. Rules checked: {data.attention.map((a) => a.title.toLowerCase()).join("; ")}.</p>}
        {flagged.map((a) => <button type="button" className="anomaly" style={{ width: "100%", border: 0, background: "transparent", textAlign: "left", cursor: "pointer" }} key={a.key} onClick={() => onNavigate(a.page as PageName)} title={a.rule}>
          <span><Icon name="warning"/></span><div><strong>{a.count} · {a.title}</strong><p>{a.examples[0]}{a.count > 1 ? ` and ${a.count - 1} more` : ""}</p></div><Icon name="chevron"/></button>)}
      </Card>
      <Card><div className="card-heading"><div><h2>Batch record age</h2><p>Batches holding stock, by when their record was created</p></div></div>
        <div className="big-stat">{agingTotal}</div><p className="muted-copy">batches with stock on hand</p>
        <div className="aging-bars">{data.aging.map((a) => <div key={a.label}><span><small>{a.label}</small><strong>{a.batches}</strong></span><Progress value={agingTotal ? Math.round(a.batches / agingTotal * 100) : 0}/></div>)}</div>
      </Card>
      <Card className="span-2"><div className="card-heading"><div><h2>Supplier performance</h2><p>Approved orders; on time means the first delivery arrived by the expected date</p></div></div>
        {data.suppliers.length === 0 ? <p className="muted-copy" style={{ marginTop: 16 }}>No approved purchase orders yet.</p>
          : <div className="table-scroll" style={{ marginTop: 12 }}><table><thead><tr><th>Supplier</th><th>Orders</th><th>Delivered orders</th><th>First delivery on time</th><th>Deliveries</th><th>Rejected share</th></tr></thead>
            <tbody>{data.suppliers.map((sp) => <tr key={sp.supplier_id}><td><strong>{sp.supplier}</strong></td><td>{sp.orders}</td><td>{sp.orders_delivered}</td><td><strong>{pct(sp.on_time_rate)}</strong><small>{sp.first_delivery_on_time} of {sp.orders_delivered}</small></td><td>{sp.deliveries}</td><td><strong>{pct(sp.rejection_rate)}</strong><small>{sp.rejected_quantity} of {sp.received_quantity + sp.rejected_quantity} delivered</small></td></tr>)}</tbody></table></div>}
      </Card>
      <Card><div className="card-heading"><div><h2>Transfers</h2><p>Received in the last {t.window_days} days</p></div></div>
        <div className="big-stat">{t.received}</div><p className="muted-copy">transfers received</p>
        <div className="role-list" style={{ marginTop: 12 }}>
          <div><span className="role-icon"><Icon name="clock"/></span><span><strong>{leadTime(t.average_lead_time_hours)}</strong><small>Average dispatch-to-receipt time</small></span><span/><span/></div>
          <div><span className="role-icon"><Icon name="warning"/></span><span><strong>{t.with_shortage}</strong><small>Received short</small></span><span/><span/></div>
          <div><span className="role-icon"><Icon name="movement"/></span><span><strong>{t.in_transit} in transit</strong><small>{t.in_transit_overdue} past expected arrival</small></span><span/><span/></div>
        </div>
      </Card>
      <Card><div className="card-heading"><div><h2>Inspections</h2><p>Holds opened in the last {q.window_days} days</p></div></div>
        <div className="big-stat">{q.holds_opened}</div><p className="muted-copy">holds opened · {q.open} open now</p>
        <div className="role-list" style={{ marginTop: 12 }}>
          <div><span className="role-icon"><Icon name="quality"/></span><span><strong>{q.quantity_released} released · {q.quantity_rejected} rejected</strong><small>of {q.quantity_held} held</small></span><span/><span/></div>
          <div><span className="role-icon"><Icon name="warning"/></span><span><strong>{pct(q.rejection_rate)}</strong><small>Rejected share of decided quantity</small></span><span/><span/></div>
        </div>
      </Card>
    </div>
  </>;
}

type AssistantAnswer = { title: string; summary: string; columns?: string[]; rows?: string[][]; source: string; page?: PageName };
type AssistantTurn = { id: number; question: string; answer?: AssistantAnswer; error?: string };

const ASSISTANT_QUESTIONS = [
  "Which batches are flagged Low stock?",
  "Which purchase orders are overdue?",
  "Which transfers are awaiting approval?",
  "What is in transit right now?",
  "Which inspections are open?",
  "What needs attention?",
  "How are suppliers performing?",
];

// An identifier with at least one hyphen and one digit, e.g. PO-00001-1, E2E-PG-001 or TR-00001.
const ID_TOKEN = /\b(?=[A-Za-z0-9-]*\d)[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+\b/;
const RECORD_NUMBER = /^(TR|PO|QI)-?\d{1,9}$/i;

/** Matches a question to one fixed rule and answers it from live API data. Nothing is generated or guessed. */
async function answerQuestion(question: string): Promise<AssistantAnswer> {
  const q = question.toLowerCase();
  const token = question.match(ID_TOKEN)?.[0];
  if (token && RECORD_NUMBER.test(token)) {
    const { events, total } = await listAuditEvents({ skip: 0, limit: 10, search: token });
    const label = token.toUpperCase();
    return { title: `History of ${label}`, summary: total ? `${total} recorded event${total === 1 ? " mentions" : "s mention"} ${label}${total > events.length ? `; showing the latest ${events.length}` : ""}.` : `No recorded events mention ${label}.`,
      columns: ["When", "Event", "Record", "Actor"], rows: events.map((e) => [formatMoment(e.created_at), `${e.source_label} · ${e.action}`, e.record ?? "—", e.actor]), source: "Audit log · stock, transfer, purchase-order and inspection events", page: "Audit Logs" };
  }
  if (/low.?stock|running low/.test(q)) {
    const { materials: items, total } = await listMaterials({ skip: 0, limit: 10, status: "Low stock" });
    return { title: "Batches flagged Low stock", summary: total ? `${total} batch${total === 1 ? " is" : "es are"} flagged Low stock${total > items.length ? `; showing ${items.length}` : ""}.` : "No batches are flagged Low stock.",
      columns: ["Batch", "Available", "Yard", "Ship"], rows: items.map((m) => [`${m.name} (${m.id})`, `${m.available} ${m.unit}`, m.yard.name, m.ship?.name ?? "Unassigned"]), source: "Inventory · status = Low stock", page: "Inventory" };
  }
  if (/overdue|late|delayed/.test(q) && /order|po\b|purchase|deliver|supplier/.test(q)) {
    const { purchase_orders: items, total } = await listPurchaseOrders({ skip: 0, limit: 10, overdue: true });
    return { title: "Overdue purchase orders", summary: total ? `${total} open order${total === 1 ? " is" : "s are"} past the expected delivery date.` : "No open purchase orders are overdue.",
      columns: ["Order", "Supplier", "Expected", "Received", "Outstanding value"], rows: items.map((o) => [o.display_id, o.supplier.name, o.expected_delivery_date ?? "—", `${o.received_quantity} of ${o.ordered_quantity}`, formatMoney(o.outstanding_value, o.currency)]), source: "Procurement · open orders past expected delivery", page: "Procurement" };
  }
  if (/approv/.test(q) && /transfer|movement/.test(q)) {
    const { transfers: items, total } = await listTransfers(["Requested"], { skip: 0, limit: 10 });
    return { title: "Transfers awaiting approval", summary: total ? `${total} transfer request${total === 1 ? " is" : "s are"} waiting for approval.` : "No transfer requests are waiting for approval.",
      columns: ["Transfer", "Batch", "Quantity", "Route", "Requested by"], rows: items.map((x) => [x.display_id, x.material.id, `${x.quantity} ${x.unit}`, `${x.from_yard.name} → ${x.to_yard.name}`, x.requested_by]), source: "Movements · status = Requested", page: "Movements" };
  }
  if (/transit|on the way|dispatched|shipping/.test(q)) {
    const { transfers: items, total } = await listTransfers(["Dispatched"], { skip: 0, limit: 10 });
    return { title: "Transfers in transit", summary: total ? `${total} transfer${total === 1 ? " is" : "s are"} in transit.` : "Nothing is in transit.",
      columns: ["Transfer", "Batch", "Quantity", "Route", "Expected"], rows: items.map((x) => [x.display_id, x.material.id, `${x.quantity} ${x.unit}`, `${x.from_yard.name} → ${x.to_yard.name}`, x.expected_arrival ?? "Not set"]), source: "Movements · status = Dispatched", page: "Movements" };
  }
  if (/inspect|quality|hold\b|holds\b|qi-/.test(q)) {
    const { inspections: items, total } = await listInspections({ skip: 0, limit: 10, status: "Open" });
    return { title: "Open inspections", summary: total ? `${total} inspection hold${total === 1 ? " is" : "s are"} awaiting a decision.` : "No inspection holds are open.",
      columns: ["Inspection", "Batch", "Awaiting", "Order"], rows: items.map((h) => [h.display_id, `${h.material.name} (${h.material.id})`, `${h.outstanding_quantity} ${h.material.unit}`, h.goods_receipt_line.receipt.purchase_order.display_id]), source: "Quality · status = Open", page: "Quality" };
  }
  if (/supplier/.test(q)) {
    const { suppliers } = await getAnalyticsOverview();
    return { title: "Supplier performance", summary: suppliers.length ? `${suppliers.length} supplier${suppliers.length === 1 ? " has" : "s have"} approved orders.` : "No supplier has approved orders yet.",
      columns: ["Supplier", "Orders", "First delivery on time", "Rejected share"], rows: suppliers.map((sp) => [sp.supplier, String(sp.orders), `${pct(sp.on_time_rate)} (${sp.first_delivery_on_time} of ${sp.orders_delivered})`, pct(sp.rejection_rate)]), source: "Analytics · approved purchase orders and receipts", page: "Analytics" };
  }
  if (/attention|risk|problem|issue|flag|wrong/.test(q)) {
    const { attention } = await getAnalyticsOverview();
    const flagged = attention.filter((a) => a.count > 0);
    return { title: "Needs attention", summary: flagged.length ? `${flagged.length} rule${flagged.length === 1 ? "" : "s"} flagged records.` : "Nothing is flagged by the current rules.",
      columns: ["Rule", "Count", "Example"], rows: attention.map((a) => [a.title, String(a.count), a.examples[0] ?? "—"]), source: "Analytics · fixed attention rules", page: "Analytics" };
  }
  if (token || /batch|material|lot\b/.test(q)) {
    const term = token ?? question.replace(/\?/g, "").split(/\s+/).filter((w) => w.length > 2 && !/^(which|what|where|batch|batches|material|materials|show|find|about|the|for|lot)$/i.test(w)).join(" ");
    if (term) {
      const { materials: items, total } = await listMaterials({ skip: 0, limit: 10, search: term });
      return { title: `Batches matching “${term}”`, summary: total ? `${total} batch${total === 1 ? " matches" : "es match"}.` : `No batch matches “${term}”.`,
        columns: ["Batch", "Lot", "Available", "On hand", "Yard", "Status"], rows: items.map((m) => [`${m.name} (${m.id})`, m.batch, `${m.available} ${m.unit}`, `${m.quantity} ${m.unit}`, m.yard.name, m.status]), source: "Inventory · search by ID, name or lot", page: "QR Tracking" };
    }
  }
  return { title: "I can’t answer that yet", summary: "I only answer a fixed set of questions from live data: low stock, overdue purchase orders, transfers awaiting approval or in transit, open inspections, supplier performance, what needs attention, or a batch ID such as PO-00001-1.", source: "No data was read" };
}

function Assistant({ onNavigate }: { onNavigate: (page: PageName) => void }) {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<AssistantTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const counter = useRef(0);

  const ask = async (text: string) => {
    const asked = text.trim();
    if (!asked || busy) return;
    const id = ++counter.current;
    setTurns((t) => [...t, { id, question: asked }]);
    setQuestion("");
    setBusy(true);
    try {
      const answer = await answerQuestion(asked);
      setTurns((t) => t.map((x) => (x.id === id ? { ...x, answer } : x)));
    } catch (err) {
      setTurns((t) => t.map((x) => (x.id === id ? { ...x, error: err instanceof Error ? err.message : String(err) } : x)));
    } finally {
      setBusy(false);
    }
  };

  return <><PageHeader eyebrow="Operations assistant" title="Assistant" description="Answers a fixed set of operational questions from live data. It is not an AI model." actions={<Badge tone="neutral">Rule-based</Badge>}/>
    <div className="assistant-layout"><Card className="assistant-main">
      {turns.length === 0 && <div className="chat-intro"><span className="ai-mark large"><Icon name="assistant" size={26}/></span><h2>Materials operations assistant</h2><p>Ask about low stock, overdue orders, transfers, inspections, supplier performance or a batch ID. Questions are matched to fixed rules and answered straight from live records; anything else gets a list of what I can answer.</p></div>}
      {turns.length > 0 && <div className="chat-thread">{turns.map((turn) => <div key={turn.id} style={{ marginBottom: 18 }}>
        <div className="user-message">{turn.question}</div>
        <div className="assistant-message">
          {!turn.answer && !turn.error && <p>Reading live data…</p>}
          {turn.error && <><div className="answer-heading"><Icon name="warning"/><strong>Couldn’t read the data</strong></div><p>{turn.error}</p></>}
          {turn.answer && <><div className="answer-heading"><Icon name="assistant"/><strong>{turn.answer.title}</strong><Badge tone="neutral">Live data</Badge></div>
            <p>{turn.answer.summary}</p>
            {!!turn.answer.rows?.length && <div className="table-scroll"><table><thead><tr>{turn.answer.columns!.map((c) => <th key={c}>{c}</th>)}</tr></thead><tbody>{turn.answer.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody></table></div>}
            <small className="answer-note">Source: {turn.answer.source}{turn.answer.page ? <> · <button type="button" className="link-button" onClick={() => onNavigate(turn.answer!.page!)}>Open {turn.answer.page}</button></> : null}</small></>}
        </div>
      </div>)}</div>}
      <form className="composer" onSubmit={(e) => { e.preventDefault(); ask(question); }}><Input aria-label="Ask a question" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask about stock, orders, transfers or inspections…" disabled={busy}/><Button type="submit" icon="arrow" disabled={busy || !question.trim()}>Ask</Button></form>
    </Card>
    <Card className="suggested-card"><h2>Questions I can answer</h2><p>Each one reads live records</p>{ASSISTANT_QUESTIONS.map((q) => <button key={q} onClick={() => ask(q)} disabled={busy}><span>{q}</span><Icon name="arrow"/></button>)}<div className="privacy-note"><Icon name="lock"/><span><strong>No AI model</strong><small>Questions are matched to fixed rules in your browser; answers come from the Dockyard API.</small></span></div></Card></div>
  </>;
}

const buildTone = (status: string) =>
  ["Launched", "Commissioned", "Launch ready"].includes(status) ? "success" as const : status === "Planning" ? "neutral" as const : "info" as const;

function ShipAllocationDialog({ ship, onClose, onNavigate }: { ship: ShipProgram; onClose: () => void; onNavigate: (page: PageName) => void }) {
  const [result, setResult] = useState<{ items: ApiMaterial[]; total: number } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    listMaterials({ skip: 0, limit: 100, ship: ship.id }, controller.signal)
      .then(({ materials: items, total }) => setResult({ items, total }))
      .catch((err) => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err)); });
    return () => controller.abort();
  }, [ship.id]);

  return <div className="dialog-layer" role="dialog" aria-modal="true" aria-labelledby="ship-allocation-title">
    <button className="dialog-scrim" onClick={onClose} aria-label="Close dialog"/>
    <div className="dialog" style={{ width: "min(820px, 100%)" }}>
      <div className="dialog-header">
        <div>
          <p className="eyebrow">Ship allocation</p>
          <h2 id="ship-allocation-title">{ship.name}</h2>
          <p>{ship.build_status} · {ship.build_progress}% complete · {ship.yard}</p>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close dialog"><Icon name="close"/></button>
      </div>
      {error && <div className="notice" role="alert" style={{ marginTop: 18 }}><Icon name="warning"/>{error}</div>}
      {!error && !result && <StatePanel type="loading" title="Loading allocated batches" message="Fetching batches allocated to this ship…"/>}
      {result && result.items.length === 0 && <StatePanel type="empty" title="No batches allocated" message="Allocate a batch by editing it in Inventory and choosing this ship."/>}
      {result && result.items.length > 0 && <div className="table-scroll" style={{ padding: "0 22px" }}><table>
        <thead><tr><th>Batch</th><th>Stock</th><th>Location</th><th>Status</th></tr></thead>
        <tbody>{result.items.map((m) => <tr key={m.id}>
          <td><strong>{m.name}</strong><small>{m.id} · Lot {m.batch}</small></td>
          <td><strong>{m.available} {m.unit} available</strong><small>{m.reserved} reserved · {m.quantity} on hand</small></td>
          <td><strong>{m.yard.name}</strong><small>{m.location ? `Zone ${m.location.zone}, aisle ${m.location.aisle}` : "No location"}</small></td>
          <td><Badge tone={statusTone(m.status)}>{m.status}</Badge></td>
        </tr>)}</tbody>
      </table></div>}
      {result && result.total > result.items.length && <p className="muted-copy" style={{ padding: "8px 22px 0" }}>Showing {result.items.length} of {result.total} batches; filter Inventory by this ship's yard to see the rest.</p>}
      <div className="dialog-actions">
        <Button type="button" variant="ghost" onClick={() => { onClose(); onNavigate("Inventory"); }}>Open Inventory</Button>
        <Button type="button" variant="secondary" onClick={onClose}>Close</Button>
      </div>
    </div>
  </div>;
}

function ShipsYards({ onNavigate }: { onNavigate: (page: PageName) => void }) {
  const [ships, setShips] = useState<ShipProgram[] | null>(null);
  const [shipsError, setShipsError] = useState("");
  const [yards, setYards] = useState<YardOverview[] | null>(null);
  const [yardsError, setYardsError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [openShip, setOpenShip] = useState<ShipProgram | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setShipsError("");
    setYardsError("");
    getShipPrograms(controller.signal)
      .then(setShips)
      .catch((err) => { if (!controller.signal.aborted) setShipsError(err instanceof Error ? err.message : String(err)); });
    getYardOverview(controller.signal)
      .then(setYards)
      .catch((err) => { if (!controller.signal.aborted) setYardsError(err instanceof Error ? err.message : String(err)); });
    return () => controller.abort();
  }, [reloadKey]);

  const retry = () => { setShips(null); setYards(null); setReloadKey((k) => k + 1); };
  return <><PageHeader eyebrow="Program allocation" title="Ships & yards" description="Review material commitments by build program and operating yard." actions={<Button icon="plus" title="Batches are allocated to a ship by editing them in Inventory" onClick={() => onNavigate("Inventory")}>New allocation</Button>}/>
    {shipsError ? <Card><StatePanel type="error" title="Ship programs couldn’t be loaded" message={shipsError} onRetry={retry}/></Card>
      : !ships ? <Card><StatePanel type="loading" title="Loading ship programs" message="Fetching build programs…"/></Card>
      : ships.length === 0 ? <Card><StatePanel type="empty" title="No ships recorded" message="Ship programs appear here once they are added to the database."/></Card>
      : <div className="entity-grid">{ships.map((ship) => <Card className="entity-card" key={ship.id}>
        <div className="entity-top"><span className="ship-avatar large"><Icon name="ship" size={24}/></span><Badge tone={buildTone(ship.build_status)}>{ship.build_status}</Badge></div>
        <h2>{ship.name}</h2><p>{ship.yard}</p>
        <Progress value={ship.build_progress}/>
        <div className="entity-stats"><span><strong>{ship.build_progress}%</strong><small>Build progress</small></span><span><strong>{ship.allocated_batches}</strong><small>Allocated batches</small></span><span><strong>{ship.reserved_batches}</strong><small>With reserved stock</small></span></div>
        <Button variant="secondary" onClick={() => setOpenShip(ship)}>View allocation</Button>
      </Card>)}</div>}
    <div style={{ marginTop: 14 }}><Card className="table-card">
      <div className="table-toolbar"><div><strong>Yards</strong><p className="muted-copy">Storage locations, batches and ships per operating yard</p></div></div>
      {yardsError ? <StatePanel type="error" title="Yards couldn’t be loaded" message={yardsError} onRetry={retry}/>
        : !yards ? <StatePanel type="loading" title="Loading yards" message="Fetching yard data…"/>
        : yards.length === 0 ? <StatePanel type="empty" title="No yards recorded" message="Yards appear here once they are added to the database."/>
        : <div className="table-scroll"><table><thead><tr><th>Yard</th><th>Status</th><th>Storage locations</th><th>Batches</th><th>Ships</th><th>Capacity</th></tr></thead><tbody>{yards.map((y) => <tr key={y.id}>
          <td><strong>{y.name}</strong><small>{y.location}</small></td>
          <td><Badge tone={y.status === "Active" ? "success" : y.status === "Closed" ? "danger" : "warning"}>{y.status}</Badge></td>
          <td><strong>{y.storage_locations}</strong></td><td><strong>{y.batches}</strong></td><td><strong>{y.ships}</strong></td>
          <td><strong>{y.capacity.toLocaleString()}</strong><small>as recorded</small></td>
        </tr>)}</tbody></table></div>}
    </Card></div>
    {openShip && <ShipAllocationDialog ship={openShip} onClose={() => setOpenShip(null)} onNavigate={onNavigate}/>}
  </>;
}

const QUALITY_PAGE_SIZE = 25;

function Quality({ onMaterialsChanged }: { onMaterialsChanged: () => void }) {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<InspectionStatus | "">("Open");
  const [skip, setSkip] = useState(0);
  const [state, setState] = useState<"ready" | "loading" | "empty" | "error">("loading");
  const [loadError, setLoadError] = useState("");
  const [items, setItems] = useState<Inspection[]>([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<InspectionSummary | null>(null);
  const [summaryError, setSummaryError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [openId, setOpenId] = useState<number | null>(null);
  const [toast, showToast] = useToast();

  useEffect(() => {
    const id = window.setTimeout(() => { setSearch(query.trim()); setSkip(0); }, 300);
    return () => window.clearTimeout(id);
  }, [query]);

  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    getInspectionSummary(controller.signal)
      .then((s) => { setSummary(s); setSummaryError(""); })
      .catch((err) => { if (!controller.signal.aborted) { setSummary(null); setSummaryError(err instanceof Error ? err.message : String(err)); } });
    listInspections({ skip, limit: QUALITY_PAGE_SIZE, search, status: statusFilter || undefined }, controller.signal)
      .then(({ inspections, total: count }) => {
        setItems(inspections);
        setTotal(count);
        setState(inspections.length === 0 ? "empty" : "ready");
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setLoadError(err instanceof Error ? err.message : String(err));
        setState("error");
      });
    return () => controller.abort();
  }, [skip, search, statusFilter, reloadKey]);

  const done = useCallback((message: string) => {
    setOpenId(null);
    showToast(message);
    setReloadKey((k) => k + 1);
    onMaterialsChanged();
  }, [showToast, onMaterialsChanged]);

  const live = (value: number | undefined) => (summary ? String(value) : "—");
  const liveBadge = summaryError ? "Unavailable" : summary ? "Live" : "Loading";
  const cards: [string, string, string, "warning" | "success" | "danger" | "purple"][] = [
    ["Awaiting inspection", live(summary?.open), liveBadge, "warning"],
    ["Passed this week", live(summary?.released_this_week), liveBadge, "success"],
    ["Rejected this week", live(summary?.rejected_this_week), liveBadge, "danger"],
    ["Certificate gaps", "—", "Not tracked", "purple"],
  ];
  const firstShown = total === 0 ? 0 : skip + 1;

  return <><PageHeader eyebrow="Material assurance" title="Quality inspections" description="Release or reject goods held for inspection on receipt." actions={<Button icon="plus" disabled title="Inspections start when goods are received with Hold for inspection">New inspection</Button>}/>
    <div className="mini-kpis">{cards.map(([l, v, badge, t]) => <Card key={l}><span>{l}</span><strong>{v}</strong><Badge tone={badge === "Live" ? t : "neutral"}>{badge}</Badge></Card>)}</div>
    <Card className="table-card">
      <div className="table-toolbar">
        <Input icon="search" placeholder="Search by inspection number, material or batch…" value={query} onChange={(e) => setQuery(e.target.value)}/>
        <div className="toolbar-filters"><Select aria-label="Filter by status" value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value as InspectionStatus | ""); setSkip(0); }}><option value="">All statuses</option>{INSPECTION_STATUSES.map((s) => <option key={s} value={s}>{s === "Open" ? "Awaiting decision" : s}</option>)}</Select></div>
      </div>
      {state === "error" && <div className="notice" role="alert" style={{ marginTop: 14 }}><Icon name="warning"/>{loadError}</div>}
      {state !== "ready"
        ? <StatePanel type={state} onRetry={() => setReloadKey((k) => k + 1)} title={state === "loading" ? "Loading inspections" : state === "empty" ? "No inspections here" : "Inspections couldn’t be loaded"} message={state === "loading" ? "Fetching inspection holds…" : state === "empty" ? "Goods received with Hold for inspection appear here until they are released or rejected." : undefined}/>
        : <div className="table-scroll"><table><thead><tr><th>Inspection</th><th>Material</th><th>Source</th><th>Quantity</th><th>Status</th><th aria-label="Actions"/></tr></thead><tbody>{items.map((h) => {
          const receipt = h.goods_receipt_line.receipt;
          return <tr key={h.id}>
            <td><strong className="mono">{h.display_id}</strong><small>Held {formatMoment(h.created_at)} by {h.created_by}</small></td>
            <td><strong>{h.material.name}</strong><small>{h.material.id} · Lot {h.material.batch} · {h.material.yard.name}</small></td>
            <td><strong className="mono">{receipt.purchase_order.display_id}</strong><small>{receipt.display_id} · {receipt.purchase_order.supplier.name}</small></td>
            <td><strong>{h.outstanding_quantity} {h.material.unit} awaiting</strong><small>{h.released_quantity} released · {h.rejected_quantity} rejected of {h.quantity}</small></td>
            <td><Badge tone={inspectionTone(h.status)}>{h.status}</Badge></td>
            <td><Button variant={h.status === "Open" ? "primary" : "secondary"} onClick={() => setOpenId(h.id)}>{h.status === "Open" ? "Review" : "Details"}</Button></td>
          </tr>;
        })}</tbody></table></div>}
      <div className="table-footer"><span>{state === "ready" ? `Showing ${firstShown}–${skip + items.length} of ${total} inspections` : `${total} inspections`}</span><div><Button variant="ghost" disabled={skip === 0 || state === "loading"} onClick={() => setSkip(Math.max(0, skip - QUALITY_PAGE_SIZE))}>Previous</Button><Button variant="secondary" disabled={skip + items.length >= total || state === "loading"} onClick={() => setSkip(skip + QUALITY_PAGE_SIZE)}>Next</Button></div></div>
    </Card>
    {openId !== null && <InspectionDialog inspectionId={openId} onClose={() => setOpenId(null)} onDone={done}/>}
    <Toast message={toast}/>
  </>;
}

const AUDIT_PAGE_SIZE = 25;

/** Stock-ledger rows use the shared ledger rule; other sources show the event's quantity. */
function auditQuantity(e: AuditEvent) {
  if (e.quantity === null) return "";
  const n = e.source === "stock" ? ledgerQuantity(e.action, e.quantity, e.detail) : String(e.quantity);
  return ` · ${n}${e.unit ? ` ${e.unit}` : ""}`;
}

function AuditLogs() {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [source, setSource] = useState<AuditSource | "">("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [skip, setSkip] = useState(0);
  const [state, setState] = useState<"ready" | "loading" | "empty" | "error">("loading");
  const [loadError, setLoadError] = useState("");
  const [items, setItems] = useState<AuditEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    const id = window.setTimeout(() => { setSearch(query.trim()); setSkip(0); }, 300);
    return () => window.clearTimeout(id);
  }, [query]);

  const rangeError = dateFrom && dateTo && dateFrom > dateTo ? "The start date must be on or before the end date." : "";

  useEffect(() => {
    if (rangeError) return;
    const controller = new AbortController();
    setState("loading");
    listAuditEvents({ skip, limit: AUDIT_PAGE_SIZE, search, source: source || undefined, dateFrom, dateTo }, controller.signal)
      .then(({ events, total: count }) => { setItems(events); setTotal(count); setState(events.length ? "ready" : "empty"); })
      .catch((err) => { if (!controller.signal.aborted) { setLoadError(err instanceof Error ? err.message : String(err)); setState("error"); } });
    return () => controller.abort();
  }, [skip, search, source, dateFrom, dateTo, retryKey, rangeError]);

  const filtered = Boolean(search || source || dateFrom || dateTo);
  const firstShown = total === 0 ? 0 : skip + 1;
  return <><PageHeader eyebrow="Traceable operations" title="Audit logs" description="Recorded stock, transfer, purchase-order and inspection activity, newest first." actions={<Button variant="secondary" icon="download" disabled title="Export is not available yet">Export log</Button>}/>
    <Card className="audit-card">
      <div className="table-toolbar">
        <Input icon="search" aria-label="Search audit events" placeholder="Search batch, material, PO-/TR-/QI-/GR- number, actor or reason…" value={query} onChange={(e) => setQuery(e.target.value)}/>
        <div className="toolbar-filters">
          <Select aria-label="Filter by event type" value={source} onChange={(e) => { setSource(e.target.value as AuditSource | ""); setSkip(0); }}><option value="">All event types</option>{AUDIT_SOURCES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</Select>
          <Input type="date" aria-label="From date" title="From date" value={dateFrom} max={dateTo || undefined} onChange={(e) => { setDateFrom(e.target.value); setSkip(0); }}/>
          <Input type="date" aria-label="To date" title="To date" value={dateTo} min={dateFrom || undefined} onChange={(e) => { setDateTo(e.target.value); setSkip(0); }}/>
          {filtered && <Button variant="ghost" onClick={() => { setQuery(""); setSearch(""); setSource(""); setDateFrom(""); setDateTo(""); setSkip(0); }}>Clear</Button>}
        </div>
      </div>
      {rangeError && <div className="notice" role="alert" style={{ marginTop: 14 }}><Icon name="warning"/>{rangeError}</div>}
      {!rangeError && state === "error" && <div className="notice" role="alert" style={{ marginTop: 14 }}><Icon name="warning"/>{loadError}</div>}
      {!rangeError && (state !== "ready"
        ? <StatePanel type={state} onRetry={() => setRetryKey((k) => k + 1)} title={state === "loading" ? "Loading audit events" : state === "empty" ? (filtered ? "No events match" : "No recorded events yet") : "Audit events couldn’t be loaded"} message={state === "loading" ? "Fetching recorded activity…" : state === "empty" ? (filtered ? "Try a different search, event type or date range." : "Stock movements, transfers, purchase orders and inspections appear here as they happen.") : undefined}/>
        : <div className="audit-timeline">{items.map((e) => <div className="audit-event" key={e.key}>
          <span className="audit-dot"><Icon name="check" size={14}/></span>
          <div><strong>{e.source_label} · {e.action}{e.from_status && e.to_status && e.from_status !== e.to_status ? ` · ${e.from_status} → ${e.to_status}` : ""}{auditQuantity(e)}</strong>
            <p>{[e.actor, e.subject && (e.batch ? `${e.subject} (lot ${e.batch})` : e.subject), e.reason, e.detail].filter(Boolean).join(" · ")}</p></div>
          <div><strong className="mono">{e.record ?? "—"}</strong><small>{formatMoment(e.created_at)}</small></div>
        </div>)}</div>)}
      <div className="table-footer"><span>{state === "ready" && !rangeError ? `Showing ${firstShown}–${skip + items.length} of ${total} events` : `${rangeError ? 0 : total} events`}</span><div><Button variant="ghost" disabled={skip === 0 || state === "loading"} onClick={() => setSkip(Math.max(0, skip - AUDIT_PAGE_SIZE))}>Previous</Button><Button variant="secondary" disabled={skip + items.length >= total || state === "loading" || Boolean(rangeError)} onClick={() => setSkip(skip + AUDIT_PAGE_SIZE)}>Next</Button></div></div>
    </Card>
    <p className="muted-copy" style={{ marginTop: 10 }}>Supplier changes are not recorded, and inventory edits made before stock adjustments were logged do not appear. Actor names are supplied by the app and are not verified — there is no sign-in yet.</p>
  </>;
}

const SETTINGS_TABS = ["General", "Roles & access", "Notifications", "Integrations", "Offline sync"] as const;

function SettingsRow({ icon, title, detail, badge, tone = "neutral" }: { icon: IconName; title: string; detail: string; badge: string; tone?: "neutral" | "success" | "warning" | "danger" }) {
  return <div><span className="role-icon"><Icon name={icon}/></span><span><strong>{title}</strong><small>{detail}</small></span><Badge tone={tone}>{badge}</Badge><span/></div>;
}

function Settings({ apiStatus }: { apiStatus: ApiStatus }) {
  const [tab, setTab] = useState<(typeof SETTINGS_TABS)[number]>("General");
  const apiTone = apiStatus.state === "online" ? "success" as const : apiStatus.state === "checking" ? "neutral" as const : "danger" as const;
  return <><PageHeader eyebrow="Workspace administration" title="Settings" description="What this workspace is running with. Settings can’t be changed from here yet."/>
    <div className="settings-layout">
      <Card className="settings-nav">{SETTINGS_TABS.map((t) => <button className={tab === t ? "active" : ""} onClick={() => setTab(t)} key={t}><Icon name={t === "Roles & access" ? "users" : t === "Offline sync" ? "wifiOff" : "settings"}/>{t}</button>)}</Card>
      <Card className="settings-panel"><h2>{tab}</h2>
        {tab === "General" && <><p>Read from the running system. There is no settings storage yet, so nothing here can be saved.</p><div className="role-list">
          <SettingsRow icon="users" title={`${CURRENT_USER.name} · ${CURRENT_USER.role}`} detail="Prototype identity used as the actor on every change — there is no sign-in yet" badge="Not verified" tone="warning"/>
          <SettingsRow icon="settings" title="API address" detail={API_BASE_URL} badge={apiStatusLabel(apiStatus)} tone={apiTone}/>
          <SettingsRow icon="settings" title="API version" detail={apiStatus.version ? `v${apiStatus.version}` : "Unknown until the API responds"} badge={apiStatus.checkedAt ? `Checked ${checkedTime(apiStatus.checkedAt)}` : "Checking"}/>
        </div></>}
        {tab === "Roles & access" && <><p>Access control isn’t implemented yet.</p><div className="role-list">
          <SettingsRow icon="lock" title="No sign-in or roles" detail={`Everyone can use every page. Changes are recorded under the name ${CURRENT_USER.name}; names are not verified.`} badge="Not available" tone="warning"/>
        </div></>}
        {tab === "Notifications" && <><p>Notifications aren’t implemented yet. Pending work is shown on the Dashboard, Movements, Procurement and Quality pages instead.</p><div className="role-list">
          <SettingsRow icon="warning" title="Email and in-app notifications" detail="Nothing is sent or queued" badge="Not available" tone="warning"/>
        </div></>}
        {tab === "Integrations" && <><p>Connections this workspace uses.</p><div className="role-list">
          <SettingsRow icon="settings" title="Dockyard REST API" detail={API_BASE_URL} badge={apiStatusLabel(apiStatus)} tone={apiTone}/>
          <SettingsRow icon="sparkles" title="AI model" detail="None connected — the Assistant and Analytics pages use fixed rules over live data" badge="Not connected"/>
          <SettingsRow icon="scan" title="QR scanner and label printer" detail="Not connected — QR Tracking supports manual lookup only" badge="Not connected"/>
        </div></>}
        {tab === "Offline sync" && <><p>Offline use isn’t available.</p><div className="role-list">
          <SettingsRow icon="wifiOff" title="Offline cache and sync" detail="The app needs a live connection to the API; nothing is cached locally or synced later" badge="Not available" tone="warning"/>
        </div></>}
      </Card>
    </div>
  </>;
}

function CurrentPage({ page, onNavigate, materials, onMaterialsChanged, apiStatus, searchRequest }: { page: PageName; onNavigate: (p: PageName) => void; materials: MaterialSummaryState; onMaterialsChanged: () => void; apiStatus: ApiStatus; searchRequest: { text: string; n: number } | null }) {
  switch (page) {
    case "Dashboard": return <Dashboard onNavigate={onNavigate} materials={materials}/>;
    case "Inventory": return <Inventory onMaterialsChanged={onMaterialsChanged} searchRequest={searchRequest}/>;
    case "Movements": return <Movements/>;
    case "QR Tracking": return <QRTracking/>;
    case "Ships & Yards": return <ShipsYards onNavigate={onNavigate}/>;
    case "Procurement": return <Procurement onMaterialsChanged={onMaterialsChanged}/>;
    case "Analytics": return <Analytics onNavigate={onNavigate}/>;
    case "Assistant": return <Assistant onNavigate={onNavigate}/>;
    case "Quality": return <Quality onMaterialsChanged={onMaterialsChanged}/>;
    case "Audit Logs": return <AuditLogs/>;
    case "Settings": return <Settings apiStatus={apiStatus}/>;
  }
}

export default function App() {
  const [page, setPage] = useState<PageName>("Dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [materials, setMaterials] = useState<MaterialSummaryState>({ data: null, error: "" });
  const [materialsVersion, setMaterialsVersion] = useState(0);
  const onMaterialsChanged = useCallback(() => setMaterialsVersion((v) => v + 1), []);
  const [apiStatus, setApiStatus] = useState<ApiStatus>({ state: "checking" });
  const [searchRequest, setSearchRequest] = useState<{ text: string; n: number } | null>(null);
  const onSearch = useCallback((text: string) => { setSearchRequest((r) => ({ text, n: (r?.n ?? 0) + 1 })); setPage("Inventory"); }, []);

  // A real connection check every minute, shown in the top bar, sidebar and Settings.
  useEffect(() => {
    let alive = true;
    const check = () => getHealth()
      .then((h) => { if (alive) setApiStatus({ state: h.database === "connected" ? "online" : "degraded", version: h.version, checkedAt: new Date().toISOString() }); })
      .catch(() => { if (alive) setApiStatus((prev) => ({ state: "offline", version: prev.version, checkedAt: new Date().toISOString() })); });
    check();
    const id = window.setInterval(check, 60_000);
    return () => { alive = false; window.clearInterval(id); };
  }, []);

  // One summary feeds the Dashboard cards and the sidebar badge; refreshed on navigation and after Inventory changes.
  useEffect(() => {
    const controller = new AbortController();
    getMaterialSummary(controller.signal)
      .then((data) => setMaterials({ data, error: "" }))
      .catch((err) => { if (!controller.signal.aborted) setMaterials({ data: null, error: err instanceof Error ? err.message : String(err) }); });
    return () => controller.abort();
  }, [page, materialsVersion]);

  return <div className="app-shell"><Sidebar active={page} onNavigate={setPage} open={sidebarOpen} onClose={() => setSidebarOpen(false)} lowStockCount={materials.data?.low_stock_batches ?? null} apiStatus={apiStatus}/><div className="app-main"><Topbar onMenu={() => setSidebarOpen(true)} onNavigate={setPage} onSearch={onSearch} apiStatus={apiStatus}/><main className="content"><CurrentPage page={page} onNavigate={setPage} materials={materials} onMaterialsChanged={onMaterialsChanged} apiStatus={apiStatus} searchRequest={searchRequest}/></main></div></div>;
}

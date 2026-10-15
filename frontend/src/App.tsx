import { useState, useEffect, useCallback } from "react";
import {
  audits,
  materials,
  navItems,
  purchaseOrders,
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
import { getMaterialSummary, getReferenceData, listMaterials, type ApiMaterial, type MaterialSummary, type ReferenceData } from "./api/materials";
import { TRANSFER_STATUS_LABEL, getTransferSummary, listTransfers, type Transfer, type TransferStatus, type TransferSummary } from "./api/transfers";
import { MaterialDialog } from "./components/MaterialDialog";
import { TransferDialog } from "./components/TransferDialog";
import { TransferActionDialog } from "./components/TransferActionDialog";
import { CURRENT_USER } from "./currentUser";

const INVENTORY_PAGE_SIZE = 25;

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
  "AI Analytics": "analytics",
  "AI Assistant": "assistant",
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

function Sidebar({ active, onNavigate, open, onClose, lowStockCount }: { active: PageName; onNavigate: (page: PageName) => void; open: boolean; onClose: () => void; lowStockCount: number | null }) {
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
        {navItems.slice(6, 8).map((item) => <button key={item} className={active === item ? "active" : ""} onClick={() => { onNavigate(item); onClose(); }}><Icon name={navIcons[item]}/><span>{item}</span><i>AI</i></button>)}
        <p className="nav-label">Administration</p>
        {navItems.slice(8).map((item) => <button key={item} className={active === item ? "active" : ""} onClick={() => { onNavigate(item); onClose(); }}><Icon name={navIcons[item]}/><span>{item}</span></button>)}
      </nav>
      <div className="sidebar-footer">
        <div className="sync-row"><span className="sync-dot"/><div><strong>Local cache ready</strong><small>Synced 2 min ago</small></div></div>
        <div className="version">ERP workspace · v2.4</div>
      </div>
    </aside>
  </>;
}

function Topbar({ onMenu, onNavigate }: { onMenu: () => void; onNavigate: (page: PageName) => void }) {
  const [searchOpen, setSearchOpen] = useState(false);
  return <header className="topbar">
    <button className="icon-button menu-button" onClick={onMenu} aria-label="Open navigation"><Icon name="menu"/></button>
    <div className={`global-search ${searchOpen ? "search-open" : ""}`} onClick={() => setSearchOpen(true)}>
      <Icon name="search"/><input aria-label="Search everything" placeholder="Search materials, POs, ships…"/><kbd>⌘ K</kbd>
    </div>
    <div className="topbar-actions">
      <div className="offline-pill"><Icon name="wifiOff" size={14}/><span>Offline-ready</span></div>
      <Select aria-label="Select yard" defaultValue="Harbor North"><option>Harbor North</option><option>East Basin</option><option>Dry Dock 4</option></Select>
      <button className="icon-button notification-button" aria-label="Notifications"><Icon name="bell"/><span/></button>
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

  useEffect(() => {
    const controller = new AbortController();
    getTransferSummary(controller.signal)
      .then(setTransferSummary)
      .catch((err) => { if (!controller.signal.aborted) setTransferError(err instanceof Error ? err.message : String(err)); });
    listMaterials({ skip: 0, limit: LOW_STOCK_ALERT_ROWS, status: "Low stock" }, controller.signal)
      .then(({ materials: items, total }) => setLowStock({ items, total }))
      .catch((err) => { if (!controller.signal.aborted) setLowStockError(err instanceof Error ? err.message : String(err)); });
    return () => controller.abort();
  }, []);

  const view = (label: string): KpiView =>
    label === "Pending transfers" ? pendingTransfersKpi(transferSummary, transferError) : materialKpi(label, materials);
  const errorFor = (label: string) => (label === "Pending transfers" ? transferError : materials.error) || undefined;

  return <>
    <PageHeader eyebrow="Operations overview" title="Good morning, Maya" description="Here’s what needs your attention across all active shipbuilding programs." actions={<><Button variant="secondary" icon="download">Export report</Button><Button icon="plus" onClick={() => onNavigate("Inventory")}>Receive material</Button></>}/>
    <div className="kpi-grid">
      {DASHBOARD_KPIS.map((kpi, index) => { const v = view(kpi.label); return <Card className="kpi-card" key={kpi.label}><div className={`kpi-icon kpi-${index}`}><Icon name={kpi.icon}/></div><div className="kpi-label">{kpi.label}</div><div className="kpi-value-row"><strong>{v.value}</strong><Badge tone={v.tone}>{v.delta}</Badge></div><p title={errorFor(kpi.label)}>{v.detail}</p></Card>; })}
    </div>
    <div className="dashboard-grid">
      <Card className="chart-card span-2">
        <div className="card-heading"><div><h2>Inventory movement</h2><p>Received and consumed material value</p></div><Select defaultValue="6 months"><option>6 months</option><option>12 months</option></Select></div>
        <div className="chart-legend"><span><i className="legend-received"/>Received</span><span><i className="legend-consumed"/>Consumed</span></div>
        <div className="bar-chart">
          {[["Oct",48,34],["Nov",64,47],["Dec",56,52],["Jan",78,61],["Feb",70,56],["Mar",88,66]].map(([month,a,b]) => <div className="bar-group" key={month}><div className="bar-pair"><span className="bar received" style={{height:`${a}%`}}/><span className="bar consumed" style={{height:`${b}%`}}/></div><small>{month}</small></div>)}
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
        <div className="card-heading"><div><h2>Ship-wise consumption</h2><p>Month-to-date by project</p></div><button className="icon-button"><Icon name="more"/></button></div>
        <div className="ship-list">
          {[
            ["MV Calypso","Hull 72% complete","$1.84M",72],
            ["NS Atlas","Outfitting in progress","$1.28M",54],
            ["OSV Meridian","Systems integration","$846K",38],
          ].map(([name,meta,value,progress]) => <div className="ship-row" key={name as string}><div className="ship-avatar"><Icon name="ship"/></div><div className="ship-progress"><span><strong>{name}</strong><b>{value}</b></span><small>{meta}</small><Progress value={progress as number}/></div></div>)}
        </div>
      </Card>
      <Card className="recommendation-card span-2">
        <div className="recommendation-head"><span className="ai-mark"><Icon name="sparkles"/></span><div><span className="eyebrow">AI recommendation</span><h2>Reallocate 40 Cu-Ni pipe lengths to East Basin</h2></div><Badge tone="purple">87% confidence</Badge></div>
        <p>NS Atlas demand is projected to exceed available stock in 9 days. Dry Dock 4 has 62 surplus lengths with no planned consumption for 6 weeks.</p>
        <div className="recommendation-meta"><span><strong>$12.4K</strong><small>Expedite cost avoided</small></span><span><strong>2.5 days</strong><small>Schedule risk reduced</small></span><span><strong>TR-AI-1032</strong><small>Draft transfer</small></span></div>
        <div className="recommendation-actions"><span><Icon name="warning" size={14}/> Requires human approval — suggestion only</span><div><Button variant="ghost">Review rationale</Button><Button onClick={() => onNavigate("Movements")}>Review & approve</Button></div></div>
      </Card>
      <Card className="orders-card">
        <div className="card-heading"><div><h2>Delayed orders</h2><p>2 require supplier follow-up</p></div><button className="link-button" onClick={() => onNavigate("Procurement")}>View orders</button></div>
        <div className="order-summary"><strong>$128.2K</strong><Badge tone="danger">Overdue</Badge></div>
        <p className="muted-copy">BlueLine Components · PO-89118</p>
        <div className="date-row"><span>Expected Mar 20</span><strong>6 days late</strong></div>
        <Progress value={28}/>
      </Card>
    </div>
  </>;
}

function Inventory() {
  const [query, setQuery] = useState("");
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

  const afterSave = (message: string) => { setDialog(null); act(message); setReloadKey((k) => k + 1); };
  const firstShown = total === 0 ? 0 : skip + 1;
  return <>
    <PageHeader eyebrow="Material control" title="Inventory" description="Track, reserve and issue materials across yards and ship programs." actions={<><Button variant="secondary" icon="download" disabled title="Export is not available yet">Export</Button><Button icon="plus" onClick={() => setDialog({})}>Add material</Button></>}/>
    <Card className="table-card">
      <div className="table-toolbar">
        <Input icon="search" placeholder="Search by material ID, name or batch…" value={query} onChange={(e) => setQuery(e.target.value)}/>
        <div className="toolbar-filters"><Select aria-label="Filter by category" value={category} onChange={(e) => { setCategory(e.target.value); setSkip(0); }}><option value="">All categories</option>{refs?.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select><Select aria-label="Filter by yard" value={yard} onChange={(e) => { setYard(e.target.value); setSkip(0); }}><option value="">All yards</option>{refs?.yards.map((y) => <option key={y.id} value={y.id}>{y.name}</option>)}</Select><Button variant="secondary" icon="filter" disabled title="Additional filters are not available yet">Filters</Button></div>
      </div>
      {state === "error" && <div className="notice" role="alert"><Icon name="warning"/>{loadError}</div>}
      {state !== "ready" ? <StatePanel type={state} onRetry={() => setReloadKey((k) => k + 1)}/> : <div className="table-scroll"><table><thead><tr><th>Material</th><th>Batch</th><th>Stock</th><th>Allocation</th><th>Location</th><th>Status</th><th aria-label="Actions"/></tr></thead><tbody>{items.map(item => <tr key={item.id}><td><div className="material-name"><span className="material-icon"><Icon name="box"/></span><span><strong>{item.name}</strong><small>{item.id} · {item.category.name}</small></span></div></td><td><strong className="mono">{item.batch}</strong><small>{item.quantity} {item.unit} total</small></td><td><strong>{item.available}</strong><small>{item.reserved} reserved</small></td><td><strong>{item.ship?.name ?? "Unassigned"}</strong><small>{item.quantity ? Math.round(item.reserved / item.quantity * 100) : 0}% allocated</small></td><td><strong>{item.yard.name}</strong><small>{item.location ? `Zone ${item.location.zone}` : "No location"}</small></td><td><Badge tone={statusTone(item.status)}>{item.status}</Badge></td><td><button className="icon-button" aria-label={`Edit ${item.id}`} title="Edit or delete" onClick={() => setDialog({ material: item })}><Icon name="more"/></button></td></tr>)}</tbody></table></div>}
      <div className="table-footer"><span>{state === "ready" ? `Showing ${firstShown}–${skip + items.length} of ${total} materials` : `${total} materials`}</span><div><Button variant="ghost" disabled={skip === 0 || state === "loading"} onClick={() => setSkip(Math.max(0, skip - INVENTORY_PAGE_SIZE))}>Previous</Button><Button variant="secondary" disabled={skip + items.length >= total || state === "loading"} onClick={() => setSkip(skip + INVENTORY_PAGE_SIZE)}>Next</Button></div></div>
    </Card>
    {dialog && <MaterialDialog material={dialog.material} refs={refs} refsError={refsError} onClose={() => setDialog(null)} onDone={afterSave}/>}
    <Toast message={toast}/>
  </>;
}

const MOVEMENT_ACTION: Partial<Record<TransferStatus, string>> = { Requested: "Review", Approved: "Dispatch", Dispatched: "Receive" };

const formatMoment = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

function Movements() {
  const [tab, setTab] = useState(MOVEMENT_TABS[0]);
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
    listTransfers(tab.statuses, controller.signal)
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
  }, [tab, reloadKey]);

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
    <Card className="table-card"><div className="tabs">{MOVEMENT_TABS.map(item => <button className={tab.label === item.label ? "active" : ""} onClick={() => setTab(item)} key={item.label}>{item.label}</button>)}</div>
      {state === "error" && <div className="notice" role="alert" style={{ marginTop: 14 }}><Icon name="warning"/>{loadError}</div>}
      {state !== "ready"
        ? <StatePanel type={state} onRetry={() => setReloadKey((k) => k + 1)} title={state === "loading" ? "Loading transfers" : state === "empty" ? "No transfers here" : "Transfers couldn’t be loaded"} message={state === "loading" ? "Fetching the movement queue…" : state === "empty" ? "Use Create transfer to move available stock between yards or locations." : undefined}/>
        : <div className="movement-list">{items.map(t => {
          const label = TRANSFER_STATUS_LABEL[t.status];
          const last = t.events[t.events.length - 1];
          const action = MOVEMENT_ACTION[t.status];
          return <div className="movement-row" key={t.id}><span className="movement-icon"><Icon name="movement"/></span><div className="movement-main"><span><strong>{t.material.name}</strong><Badge tone={statusTone(label)}>{label}</Badge></span><p>{t.from_yard.name}{t.from_location ? ` (Zone ${t.from_location.zone})` : ""} → {t.to_yard.name}{t.to_location ? ` (Zone ${t.to_location.zone})` : ""}</p></div><div><strong>{t.quantity} {t.unit}</strong><small>{t.display_id}</small></div><div><strong>{last ? formatMoment(last.created_at) : formatMoment(t.updated_at)}</strong><small>Updated by {last?.actor ?? t.requested_by}</small></div><Button variant={t.status === "Requested" ? "primary" : "secondary"} onClick={() => setOpenId(t.id)}>{action ?? "Details"}</Button></div>;
        })}</div>}
      {state === "ready" && total > items.length && <div className="table-footer"><span>Showing the {items.length} most recently updated of {total} transfers</span></div>}
    </Card>
    {creating && <TransferDialog refs={refs} refsError={refsError} onClose={() => setCreating(false)} onDone={done}/>}
    {openId !== null && <TransferActionDialog transferId={openId} tone={statusTone} onClose={() => setOpenId(null)} onDone={done}/>}
    <Toast message={toast}/>
  </>;
}

function QRTracking() {
  const [lookup, setLookup] = useState("");
  const found = materials.find(m => m.id.toLowerCase() === lookup.toLowerCase());
  return <><PageHeader eyebrow="Traceability" title="QR tracking" description="Look up material identity, custody and allocation records."/>
    <div className="two-column"><Card className="scanner-card"><span className="scanner-corners"><Icon name="scan" size={42}/></span><h2>QR scanner placeholder</h2><p>Camera scanning is not connected in this prototype.</p><Button variant="secondary" disabled>Camera unavailable</Button><small>Connect a supported scanner through your device integration layer.</small></Card>
    <Card><div className="card-heading"><div><h2>Manual lookup</h2><p>Enter a material or batch identifier</p></div></div><div className="lookup-row"><Input placeholder="Try STL-10084" value={lookup} onChange={e => setLookup(e.target.value)}/><Button>Look up</Button></div>{found ? <div className="material-detail"><Badge tone={statusTone(found.status)}>{found.status}</Badge><h3>{found.name}</h3><p>{found.id} · Batch {found.batch}</p><dl><div><dt>Available</dt><dd>{found.available} {found.unit}</dd></div><div><dt>Yard</dt><dd>{found.yard}</dd></div><div><dt>Allocated ship</dt><dd>{found.ship}</dd></div><div><dt>Last movement</dt><dd>Today, 09:18</dd></div></dl></div> : <div className="lookup-empty"><Icon name="qr" size={28}/><strong>Awaiting material ID</strong><span>Material details and custody history will appear here.</span></div>}</Card></div>
  </>;
}

function Procurement() {
  return <><PageHeader eyebrow="Supply chain" title="Procurement" description="Monitor suppliers, purchase orders and inbound delivery performance." actions={<Button icon="plus">New purchase order</Button>}/>
    <div className="mini-kpis">{[["Open PO value","$2.18M","info"],["Due this week","14","purple"],["Partial receipts","6","warning"],["Overdue orders","3","danger"]].map(([label,value,tone]) => <Card key={label}><span>{label}</span><strong>{value}</strong><Badge tone={tone as "warning"}>Updated today</Badge></Card>)}</div>
    <Card className="table-card"><div className="table-toolbar"><Input icon="search" placeholder="Search suppliers or purchase orders…"/><div className="toolbar-filters"><Select><option>All suppliers</option><option>Nordic Marine Steel</option></Select><Button variant="secondary" icon="filter">Filters</Button></div></div><div className="table-scroll"><table><thead><tr><th>Purchase order</th><th>Supplier</th><th>Material</th><th>Delivery</th><th>Receipt</th><th>Status</th></tr></thead><tbody>{purchaseOrders.map(po => <tr key={po.id}><td><strong className="mono">{po.id}</strong><small>{po.value}</small></td><td><strong>{po.supplier}</strong><small>Approved supplier</small></td><td><strong>{po.material}</strong><small>Production material</small></td><td><strong>{po.delivery}</strong><small>{po.status === "Overdue" ? "6 days overdue" : "Confirmed date"}</small></td><td><strong>{po.received}% received</strong><Progress value={po.received}/></td><td><Badge tone={statusTone(po.status)}>{po.status}</Badge></td></tr>)}</tbody></table></div></Card>
  </>;
}

function Analytics() {
  return <><PageHeader eyebrow="Decision intelligence" title="AI analytics" description="Forecast and anomaly insights based on cached planning data." actions={<Badge tone="purple"><Icon name="sparkles" size={13}/> Advisory only</Badge>}/>
    <div className="ai-disclaimer"><Icon name="warning"/><div><strong>AI features are represented with static mock outputs.</strong><span>No model is running, and recommendations require review before execution.</span></div></div>
    <div className="analytics-grid"><Card className="span-2"><div className="card-heading"><div><h2>90-day demand forecast</h2><p>Projected material demand by category</p></div><Select><option>All ship programs</option></Select></div><div className="forecast-chart"><svg viewBox="0 0 700 220" preserveAspectRatio="none" aria-label="Demand forecast line chart"><defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#315ce9" stopOpacity=".22"/><stop offset="1" stopColor="#315ce9" stopOpacity="0"/></linearGradient></defs><path className="gridline" d="M0 35H700M0 90H700M0 145H700M0 200H700"/><path className="area" d="M0 170 C80 160 100 120 180 135 S280 75 355 100 S455 125 520 60 S620 75 700 25 V220 H0Z"/><path className="forecast-line" d="M0 170 C80 160 100 120 180 135 S280 75 355 100 S455 125 520 60 S620 75 700 25"/></svg><div><span>Apr</span><span>May</span><span>Jun</span></div></div></Card>
      <Card><div className="card-heading"><div><h2>Anomaly detection</h2><p>Unusual activity in 24 hours</p></div><Badge tone="warning">3 found</Badge></div>{[["High cable consumption","2.4× baseline","MV Calypso"],["Duplicate receipt quantity","PO-89142","Harbor North"],["Unusual stock adjustment","-84 panels","East Basin"]].map(a => <div className="anomaly" key={a[0]}><span><Icon name="warning"/></span><div><strong>{a[0]}</strong><p>{a[1]} · {a[2]}</p></div><Icon name="chevron"/></div>)}</Card>
      <Card><div className="card-heading"><div><h2>Aging stock</h2><p>Value held over 180 days</p></div></div><div className="big-stat">$486K</div><p className="muted-copy">4.8% of current inventory value</p><div className="aging-bars">{[["181–270 days",58],["271–365 days",31],["365+ days",18]].map(([l,v]) => <div key={l as string}><span><small>{l}</small><strong>{v}%</strong></span><Progress value={v as number}/></div>)}</div></Card>
      <Card className="span-2 suggestion-panel"><div className="card-heading"><div><span className="eyebrow">Explainable suggestion</span><h2>Reallocate surplus structural steel</h2></div><Badge tone="purple">91% confidence</Badge></div><p>Move 36 AH36 sheets from OSV Meridian reserve at Dry Dock 4 to MV Calypso at Harbor North.</p><div className="reason-grid"><div><strong>Why this suggestion</strong><ul><li>OSV Meridian demand decreased after design revision 14B</li><li>MV Calypso burn rate is 18% above plan</li><li>Transfer costs less than expedited procurement</li></ul></div><div><strong>Expected impact</strong><dl><div><dt>Schedule protection</dt><dd>4 days</dd></div><div><dt>Cost avoided</dt><dd>$18,600</dd></div><div><dt>Confidence</dt><dd>91%</dd></div></dl></div></div><div className="recommendation-actions"><span><Icon name="lock"/>No action occurs without approval</span><Button>Send for approval</Button></div></Card>
    </div>
  </>;
}

function Assistant() {
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState(false);
  return <><PageHeader eyebrow="Offline workspace" title="AI assistant" description="Explore cached operational data using structured, reviewable answers." actions={<Badge tone="neutral"><Icon name="wifiOff" size={13}/> Offline demo</Badge>}/>
    <div className="assistant-layout"><Card className="assistant-main"><div className="chat-intro"><span className="ai-mark large"><Icon name="sparkles" size={26}/></span><h2>Materials operations assistant</h2><p>This interface uses static example responses. It is not connected to an AI model or backend.</p></div>{asked && <div className="chat-thread"><div className="user-message">{question}</div><div className="assistant-message"><div className="answer-heading"><Icon name="sparkles"/><strong>Structured demo answer</strong><Badge tone="neutral">Cached data</Badge></div><p>Three production-critical materials are below their planning threshold. Cu-Ni Pipe has the highest schedule exposure.</p><table><thead><tr><th>Material</th><th>Available</th><th>Coverage</th><th>Action</th></tr></thead><tbody><tr><td>Cu-Ni Pipe · 80mm</td><td>18 lengths</td><td>9 days</td><td>Review reallocation</td></tr><tr><td>Welding Electrodes</td><td>22 boxes</td><td>12 days</td><td>Expedite PO</td></tr></tbody></table><small className="answer-note">Sources: Inventory snapshot 09:40 · Production plan v18. Verify before acting.</small></div></div>}<div className="composer"><Input value={question} onChange={e => setQuestion(e.target.value)} placeholder="Ask about stock, transfers or ship demand…"/><Button onClick={() => question.trim() && setAsked(true)} icon="arrow">Ask</Button></div></Card>
    <Card className="suggested-card"><h2>Suggested questions</h2><p>Start from an operational workflow</p>{["Which materials are at risk this week?","Summarize overdue purchase orders","Show transfers awaiting my approval","Where can stock be safely reallocated?"].map(q => <button key={q} onClick={() => { setQuestion(q); setAsked(true); }}><span>{q}</span><Icon name="arrow"/></button>)}<div className="privacy-note"><Icon name="lock"/><span><strong>Local by design</strong><small>Demo answers use only static data in this app.</small></span></div></Card></div>
  </>;
}

function ShipsYards() {
  return <><PageHeader eyebrow="Program allocation" title="Ships & yards" description="Review material commitments by build program and operating yard." actions={<Button icon="plus">New allocation</Button>}/><div className="entity-grid">{[
    ["MV Calypso","Harbor North","Hull assembly","72","$6.4M","1,842"],
    ["NS Atlas","East Basin","Outfitting","54","$4.8M","1,204"],
    ["OSV Meridian","Dry Dock 4","Systems integration","38","$3.1M","884"],
  ].map(s => <Card className="entity-card" key={s[0]}><div className="entity-top"><span className="ship-avatar large"><Icon name="ship" size={24}/></span><Badge tone="success">Active</Badge></div><h2>{s[0]}</h2><p>{s[1]} · {s[2]}</p><Progress value={Number(s[3])}/><div className="entity-stats"><span><strong>{s[3]}%</strong><small>Build progress</small></span><span><strong>{s[4]}</strong><small>Allocated value</small></span><span><strong>{s[5]}</strong><small>Material lines</small></span></div><Button variant="secondary">View allocation</Button></Card>)}</div></>;
}

function Quality() {
  return <><PageHeader eyebrow="Material assurance" title="Quality inspections" description="Manage inbound inspections, certificates and quarantined material." actions={<Button icon="plus">New inspection</Button>}/><div className="mini-kpis">{[["Awaiting inspection","12","warning"],["Passed this week","86","success"],["In quarantine","4","danger"],["Certificate gaps","7","purple"]].map(([l,v,t]) => <Card key={l}><span>{l}</span><strong>{v}</strong><Badge tone={t as "warning"}>Current</Badge></Card>)}</div><Card className="table-card"><div className="table-toolbar"><Input icon="search" placeholder="Search inspections…"/><Button variant="secondary" icon="filter">Filters</Button></div><div className="table-scroll"><table><thead><tr><th>Inspection</th><th>Material</th><th>Standard</th><th>Inspector</th><th>Due</th><th>Status</th></tr></thead><tbody>{[["QI-10882","DN150 Butterfly Valve","ISO 5208","Owen Brooks","Today","Inspection"],["QI-10879","AH36 Steel Plate","ASTM A131","Nadia King","Mar 28","Passed"],["QI-10871","Marine Power Cable","IEC 60092","Owen Brooks","Mar 29","Pending"],["QI-10868","A-60 Fire Insulation","IMO FTP Code","Sam Rivera","Yesterday","Quarantine"]].map(r => <tr key={r[0]}>{r.slice(0,5).map((c,i) => <td key={c}><strong className={i===0?"mono":""}>{c}</strong>{i===1 && <small>Batch verified</small>}</td>)}<td><Badge tone={r[5]==="Passed"?"success":r[5]==="Quarantine"?"danger":"warning"}>{r[5]}</Badge></td></tr>)}</tbody></table></div></Card></>;
}

function AuditLogs() {
  return <><PageHeader eyebrow="Traceable operations" title="Audit logs" description="Immutable activity history for material, user and approval events." actions={<Button variant="secondary" icon="download">Export log</Button>}/><Card className="audit-card"><div className="table-toolbar"><Input icon="search" placeholder="Search users, actions or records…"/><div className="toolbar-filters"><Select><option>All event types</option></Select><Button variant="secondary" icon="filter">Date range</Button></div></div><div className="audit-timeline">{audits.map(a => <div className="audit-event" key={a.action}><span className="audit-dot"><Icon name="check" size={14}/></span><div><strong>{a.action}</strong><p>{a.actor} · {a.detail}</p></div><div><strong>{a.target}</strong><small>{a.time}</small></div></div>)}</div></Card></>;
}

function Settings() {
  const [tab, setTab] = useState("General");
  return <><PageHeader eyebrow="Workspace administration" title="Settings" description="Manage organization preferences, roles and integrations."/><div className="settings-layout"><Card className="settings-nav">{["General","Roles & access","Notifications","Integrations","Offline sync"].map(t => <button className={tab===t?"active":""} onClick={() => setTab(t)} key={t}><Icon name={t==="Roles & access"?"users":t==="Offline sync"?"wifiOff":"settings"}/>{t}</button>)}</Card><Card className="settings-panel"><h2>{tab}</h2><p>Configure {tab.toLowerCase()} preferences for the materials workspace.</p>{tab === "Roles & access" ? <div className="role-list">{[["Materials Admin","8 members","Full inventory and approval access"],["Yard Manager","14 members","Yard-scoped receiving and transfers"],["Quality Inspector","6 members","Inspection and certificate workflows"],["Viewer","22 members","Read-only operational access"]].map(r => <div key={r[0]}><span className="role-icon"><Icon name="users"/></span><span><strong>{r[0]}</strong><small>{r[2]}</small></span><Badge>{r[1]}</Badge><Button variant="ghost">Edit</Button></div>)}</div> : <div className="settings-form"><label><span>Organization name</span><Input defaultValue="Northstar Marine Works"/></label><label><span>Default yard</span><Select><option>Harbor North</option><option>East Basin</option></Select></label><label><span>Inventory valuation</span><Select><option>Weighted average cost</option><option>FIFO</option></Select></label><label className="toggle-row"><span><strong>Require transfer approval</strong><small>Transfers over $5,000 require a yard manager.</small></span><input type="checkbox" defaultChecked/></label><div className="notice"><Icon name="warning"/>Settings are displayed for demonstration and are not persisted.</div><Button>Save changes</Button></div>}</Card></div></>;
}

function CurrentPage({ page, onNavigate, materials }: { page: PageName; onNavigate: (p: PageName) => void; materials: MaterialSummaryState }) {
  switch (page) {
    case "Dashboard": return <Dashboard onNavigate={onNavigate} materials={materials}/>;
    case "Inventory": return <Inventory/>;
    case "Movements": return <Movements/>;
    case "QR Tracking": return <QRTracking/>;
    case "Ships & Yards": return <ShipsYards/>;
    case "Procurement": return <Procurement/>;
    case "AI Analytics": return <Analytics/>;
    case "AI Assistant": return <Assistant/>;
    case "Quality": return <Quality/>;
    case "Audit Logs": return <AuditLogs/>;
    case "Settings": return <Settings/>;
  }
}

export default function App() {
  const [page, setPage] = useState<PageName>("Dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [materials, setMaterials] = useState<MaterialSummaryState>({ data: null, error: "" });

  // One summary feeds the Dashboard cards and the sidebar badge; refreshed on navigation so edits made elsewhere show up.
  useEffect(() => {
    const controller = new AbortController();
    getMaterialSummary(controller.signal)
      .then((data) => setMaterials({ data, error: "" }))
      .catch((err) => { if (!controller.signal.aborted) setMaterials({ data: null, error: err instanceof Error ? err.message : String(err) }); });
    return () => controller.abort();
  }, [page]);

  return <div className="app-shell"><Sidebar active={page} onNavigate={setPage} open={sidebarOpen} onClose={() => setSidebarOpen(false)} lowStockCount={materials.data?.low_stock_batches ?? null}/><div className="app-main"><Topbar onMenu={() => setSidebarOpen(true)} onNavigate={setPage}/><main className="content"><CurrentPage page={page} onNavigate={setPage} materials={materials}/></main></div></div>;
}

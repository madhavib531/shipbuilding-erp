"""AI assistant: Claude answers questions about the yard using read-only tools over live data.

Enabled only when ANTHROPIC_API_KEY is set. The model never sees the database directly: it calls the tools
below, each a bounded read through the existing services, and nothing it does can change stock or records.
The question and the data the tools return are sent to Anthropic's API.
"""

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.inspection import InspectionStatus
from app.models.material import Material, MaterialStatusEnum
from app.models.purchase_order import PurchaseOrderStatus
from app.models.supplier import Supplier
from app.models.transaction import MaterialTransaction
from app.models.transfer import TransferStatus
from app.services import analytics_service, audit_service, inspection_service, material_service
from app.services import purchase_order_service, transfer_service

MAX_ROUNDS = 8
MAX_ROWS = 25

SYSTEM = """You are the assistant inside Dockyard Materials Command, a shipbuilding materials ERP. Answer questions
about stock batches, transfers between yards, purchase orders, suppliers, inspection holds and the audit trail.

Rules:
- Use the tools to look things up; never invent IDs, quantities, dates or names. If the tools do not hold the
  answer, say so plainly.
- Quantities are per batch and use different units; never add up quantities with different units.
- Money is shown in Indian rupees (INR, ₹). Totals in other currencies are converted with the exchange rates an
  admin entered (stock_summary gives both); if a currency has no rate, say its amount was not converted.
- You can only read. If asked to change something, explain which page and action the user should use
  (Inventory, Movements, Procurement, Quality) — you cannot do it yourself.
- Be brief: a short answer first, then a compact list or table if it helps. Mention record numbers
  (TR-, PO-, QI-, batch IDs) so the user can find them."""


def enabled() -> bool:
    return bool(settings.anthropic_api_key)


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(timespec="minutes")
    if hasattr(value, "value") and not isinstance(value, (str, int, float)):
        return value.value
    return value


def _batch(m: Material) -> dict:
    return {"id": m.id, "name": m.name, "lot": m.batch, "category": m.category.name, "unit": m.unit,
            "on_hand": m.quantity, "available": m.available, "reserved": m.reserved, "status": m.status.value,
            "yard": m.yard.name, "zone": m.location.zone if m.location else None,
            "ship": m.ship.name if m.ship else None,
            "unit_cost": _plain(m.unit_cost), "currency": m.cost_currency}


def _limit(n: Any) -> int:
    try:
        return max(1, min(int(n), MAX_ROWS))
    except (TypeError, ValueError):
        return 10


# ---- tools -------------------------------------------------------------------------------------------
def t_search_batches(db: Session, query: str = "", status: str = "", yard: str = "", limit: int = 10) -> dict:
    q = select(Material)
    if query:
        term = f"%{query}%"
        q = q.where(Material.id.ilike(term) | Material.name.ilike(term) | Material.batch.ilike(term))
    if status:
        q = q.where(Material.status == MaterialStatusEnum(status))
    if yard:
        q = q.where(Material.yard_id == yard)
    rows = db.scalars(q.order_by(Material.id).limit(_limit(limit))).all()
    return {"batches": [_batch(m) for m in rows]}


def t_batch_history(db: Session, batch_id: str, limit: int = 15) -> dict:
    rows = db.scalars(select(MaterialTransaction).where(MaterialTransaction.material_id == batch_id)
                      .order_by(MaterialTransaction.created_at.desc()).limit(_limit(limit))).all()
    return {"batch_id": batch_id, "entries": [
        {"type": _plain(t.transaction_type), "quantity": t.quantity, "unit": t.unit, "reference": t.reference_id,
         "actor": t.actor, "reason": t.reason, "at": _plain(t.created_at)} for t in rows]}


def t_stock_summary(db: Session, yard: str = "") -> dict:
    return material_service.summary(db, yard)


def t_list_transfers(db: Session, status: str = "", yard: str = "", limit: int = 10) -> dict:
    statuses = [TransferStatus(status)] if status else []
    total, rows = transfer_service.list_transfers(db, statuses, "", yard, 0, _limit(limit))
    return {"total": total, "transfers": [
        {"id": t.display_id, "status": t.status.value, "batch": t.material_id, "material": t.material.name,
         "quantity": t.quantity, "unit": t.unit, "from": t.from_yard.name, "to": t.to_yard.name,
         "expected_arrival": _plain(t.expected_arrival), "requested_by": t.requested_by} for t in rows],
        "queue": transfer_service.summary(db, yard)}


def t_list_purchase_orders(db: Session, status: str = "", overdue: bool = False, search: str = "", limit: int = 10) -> dict:
    statuses = [PurchaseOrderStatus(status)] if status else []
    total, rows = purchase_order_service.list_orders(db, statuses, "", search, bool(overdue), 0, _limit(limit))
    return {"total": total, "orders": [
        {"id": o.display_id, "status": o.status.value, "supplier": o.supplier.name,
         "expected_delivery": _plain(o.expected_delivery_date), "overdue": o.is_overdue,
         "currency": o.currency, "total_value": _plain(o.total_value), "outstanding_value": _plain(o.outstanding_value),
         "lines": [{"description": l.description, "ordered": l.ordered_quantity, "received": l.received_quantity, "unit": l.unit}
                   for l in o.lines]} for o in rows],
        "summary": purchase_order_service.summary(db)}


def t_list_inspections(db: Session, status: str = "Open", limit: int = 10) -> dict:
    statuses = [InspectionStatus(status)] if status else []
    total, rows = inspection_service.list_holds(db, statuses, "", 0, _limit(limit))
    return {"total": total, "inspections": [
        {"id": h.display_id, "status": h.status.value, "batch": h.material_id, "material": h.material.name,
         "held": h.quantity, "awaiting": h.outstanding_quantity, "released": h.released_quantity,
         "rejected": h.rejected_quantity, "unit": h.material.unit, "opened_by": h.created_by,
         "source": h.goods_receipt_line.receipt.purchase_order.display_id if h.goods_receipt_line else "held from stock",
         "opened": _plain(h.created_at)} for h in rows]}


def t_audit_events(db: Session, search: str = "", source: str = "", limit: int = 15) -> dict:
    sources = [audit_service.AuditSource(source)] if source else []
    total, rows = audit_service.list_events(db, sources, search, "", None, None, 0, _limit(limit))
    return {"total": total, "events": [{k: _plain(v) for k, v in e.items() if k in
            ("source_label", "record", "subject", "batch", "action", "from_status", "to_status", "actor", "reason",
             "quantity", "unit", "created_at")} for e in rows]}


def t_analytics(db: Session) -> dict:
    return analytics_service.overview(db)


def t_suppliers(db: Session, search: str = "") -> dict:
    q = select(Supplier)
    if search:
        q = q.where(Supplier.name.ilike(f"%{search}%") | Supplier.id.ilike(f"%{search}%"))
    rows = db.scalars(q.order_by(Supplier.name).limit(MAX_ROWS)).all()
    return {"suppliers": [{"id": s.id, "name": s.name, "status": _plain(s.status), "country": s.country} for s in rows]}


def _schema(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


S, I, B = {"type": "string"}, {"type": "integer", "minimum": 1, "maximum": MAX_ROWS}, {"type": "boolean"}
TOOLS: dict[str, tuple[Callable, dict]] = {
    "search_batches": (t_search_batches, {"description": "Find stock batches by ID, name or lot, optionally by status (Healthy, Low stock, Inspection, Reserved) or yard ID.",
                                          "input_schema": _schema({"query": S, "status": S, "yard": S, "limit": I})}),
    "batch_history": (t_batch_history, {"description": "Stock ledger entries of one batch, newest first.",
                                        "input_schema": _schema({"batch_id": S, "limit": I}, ["batch_id"])}),
    "stock_summary": (t_stock_summary, {"description": "Batch counts, Low-stock count and stock value per currency, optionally for one yard ID.",
                                        "input_schema": _schema({"yard": S})}),
    "list_transfers": (t_list_transfers, {"description": "Transfers between yards (status Requested, Approved, Dispatched, Received, Rejected, Cancelled) plus queue counts.",
                                          "input_schema": _schema({"status": S, "yard": S, "limit": I})}),
    "list_purchase_orders": (t_list_purchase_orders, {"description": "Purchase orders (status Draft, Approved, Partially received, Received, Closed, Cancelled; overdue=true for late ones) plus a summary.",
                                                      "input_schema": _schema({"status": S, "overdue": B, "search": S, "limit": I})}),
    "list_inspections": (t_list_inspections, {"description": "Inspection holds (status Open, Released, Partially released, Rejected; empty for all).",
                                              "input_schema": _schema({"status": S, "limit": I})}),
    "audit_events": (t_audit_events, {"description": "The audit trail, newest first. source: stock, transfer, purchase_order or inspection.",
                                      "input_schema": _schema({"search": S, "source": S, "limit": I})}),
    "analytics": (t_analytics, {"description": "Rule-based analytics: stock by category, batch age, supplier delivery performance, transfer lead times, inspection outcomes and attention flags.",
                                "input_schema": _schema({})}),
    "suppliers": (t_suppliers, {"description": "Suppliers by name or ID.", "input_schema": _schema({"search": S})}),
}


def run_tool(db: Session, name: str, args: dict) -> Any:
    fn, _ = TOOLS[name]
    try:
        return fn(db, **{k: v for k, v in args.items() if v not in (None, "")})
    except (ValueError, TypeError) as exc:  # e.g. an unknown status name
        return {"error": f"Invalid input: {exc}"}


class AssistantUnavailable(Exception):
    pass


def ask(db: Session, question: str, history: list[dict], client=None) -> dict:
    """Runs the tool loop. `client` is injectable for tests; by default an Anthropic client."""
    if client is None:
        if not enabled():
            raise AssistantUnavailable("The AI assistant is not configured (no ANTHROPIC_API_KEY)")
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=60)
    messages = [{"role": h["role"], "content": h["content"]} for h in history[-10:]] + [{"role": "user", "content": question}]
    tools = [{"name": name, **spec} for name, (_, spec) in TOOLS.items()]
    used = []
    for _ in range(MAX_ROUNDS):
        response = client.messages.create(model=settings.assistant_model, max_tokens=1500, system=SYSTEM,
                                          tools=tools, messages=messages)
        if response.stop_reason != "tool_use":
            text = "".join(getattr(b, "text", "") for b in response.content if getattr(b, "type", "") == "text").strip()
            return {"answer": text or "I could not produce an answer.", "tools_used": used, "model": settings.assistant_model}
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if getattr(block, "type", "") != "tool_use":
                continue
            args = dict(block.input or {})
            used.append({"tool": block.name, "input": args})
            output = run_tool(db, block.name, args) if block.name in TOOLS else {"error": f"Unknown tool {block.name}"}
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(output, default=_plain)[:20000]})
        messages.append({"role": "user", "content": results})
    return {"answer": "I needed too many lookups to answer that; try a narrower question.", "tools_used": used,
            "model": settings.assistant_model}

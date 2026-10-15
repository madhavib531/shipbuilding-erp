"""Purchase-order endpoints: drafts, lifecycle and goods receipts. Only posting a receipt changes stock."""

from typing import Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.purchase_order import PurchaseOrderStatus
from app.schemas.common import SuccessResponse
from app.schemas.purchase_order import (
    PurchaseOrderAction, PurchaseOrderCreate, PurchaseOrderDetail, PurchaseOrderRead, PurchaseOrderReasonAction,
    PurchaseOrderUpdate,
)
from app.schemas.goods_receipt import GoodsReceiptCreate, GoodsReceiptRead
from app.services import goods_receipt_service as receipt_service
from app.services import purchase_order_service as service

router = APIRouter(prefix="/api/v1/purchase-orders", tags=["purchase orders"])


def _run(db: Session, action: Callable[[], object]):
    try:
        return action()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The change conflicted with a concurrent update. Reload and try again.",
        )
    except Exception:
        db.rollback()
        raise


def _detail(db: Session, order_id: int, message: str) -> SuccessResponse:
    order = service.get_order(db, order_id)
    return SuccessResponse(message=message, data=PurchaseOrderDetail.model_validate(order).model_dump(mode="json"))


@router.get("", response_model=SuccessResponse)
def list_purchase_orders(
    statuses: list[PurchaseOrderStatus] = Query(default=[], alias="status", description="Repeat to match several"),
    supplier_id: str = Query(""),
    search: str = Query("", description="PO number, supplier name, line description or supplier part number"),
    overdue: bool = Query(False, description="Only open orders past their expected delivery date"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    total, items = service.list_orders(db, statuses, supplier_id, search, overdue, skip, limit)
    return SuccessResponse(
        message="Purchase orders retrieved successfully",
        data={
            "purchase_orders": [PurchaseOrderRead.model_validate(o).model_dump(mode="json") for o in items],
            "total": total, "skip": skip, "limit": limit,
        },
    )


@router.get("/summary", response_model=SuccessResponse)
def purchase_order_summary(db: Session = Depends(get_db)):
    return SuccessResponse(message="Purchase-order summary retrieved successfully", data=service.summary(db))


@router.get("/{order_id}", response_model=SuccessResponse)
def get_purchase_order(order_id: int, db: Session = Depends(get_db)):
    return _detail(db, order_id, "Purchase order retrieved successfully")


@router.post("", response_model=SuccessResponse, status_code=status.HTTP_201_CREATED)
def create_purchase_order(
    data: PurchaseOrderCreate,
    response: Response,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=100),
    db: Session = Depends(get_db),
):
    order_id, created = _run(db, lambda: service.create_order(db, data, idempotency_key))
    if not created:
        response.status_code = status.HTTP_200_OK
    return _detail(db, order_id, "Purchase order created" if created else "Purchase order already exists for this Idempotency-Key")


@router.patch("/{order_id}", response_model=SuccessResponse)
def update_purchase_order(order_id: int, data: PurchaseOrderUpdate, db: Session = Depends(get_db)):
    _run(db, lambda: service.update_draft(db, order_id, data))
    return _detail(db, order_id, "Purchase order updated")


@router.post("/{order_id}/approve", response_model=SuccessResponse)
def approve_purchase_order(order_id: int, data: PurchaseOrderAction, db: Session = Depends(get_db)):
    _run(db, lambda: service.approve(db, order_id, data))
    return _detail(db, order_id, "Purchase order approved")


@router.post("/{order_id}/reopen", response_model=SuccessResponse)
def reopen_purchase_order(order_id: int, data: PurchaseOrderReasonAction, db: Session = Depends(get_db)):
    _run(db, lambda: service.reopen(db, order_id, data))
    return _detail(db, order_id, "Purchase order reopened as a draft")


@router.post("/{order_id}/cancel", response_model=SuccessResponse)
def cancel_purchase_order(order_id: int, data: PurchaseOrderReasonAction, db: Session = Depends(get_db)):
    _run(db, lambda: service.cancel(db, order_id, data))
    return _detail(db, order_id, "Purchase order cancelled")


@router.post("/{order_id}/close", response_model=SuccessResponse)
def close_purchase_order(order_id: int, data: PurchaseOrderReasonAction, db: Session = Depends(get_db)):
    _run(db, lambda: service.close(db, order_id, data))
    return _detail(db, order_id, "Purchase order closed")


@router.get("/{order_id}/receipts", response_model=SuccessResponse)
def list_goods_receipts(order_id: int, db: Session = Depends(get_db)):
    receipts = receipt_service.list_receipts(db, order_id)
    return SuccessResponse(message="Goods receipts retrieved successfully",
                           data={"receipts": [GoodsReceiptRead.model_validate(r).model_dump(mode="json") for r in receipts]})


@router.post("/{order_id}/receipts", response_model=SuccessResponse, status_code=status.HTTP_201_CREATED)
def post_goods_receipt(
    order_id: int,
    data: GoodsReceiptCreate,
    response: Response,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=100),
    db: Session = Depends(get_db),
):
    """Receive goods: accepted quantities go into stock with a RECEIPT ledger row; rejected ones never do."""
    receipt_id, created = _run(db, lambda: receipt_service.post_receipt(db, order_id, data, idempotency_key))
    if not created:
        response.status_code = status.HTTP_200_OK
    receipt = receipt_service.get_receipt(db, receipt_id)
    order = service.get_order(db, receipt.purchase_order_id)
    return SuccessResponse(
        message="Goods receipt posted" if created else "Goods receipt already exists for this Idempotency-Key",
        data={"receipt": GoodsReceiptRead.model_validate(receipt).model_dump(mode="json"),
              "purchase_order": PurchaseOrderDetail.model_validate(order).model_dump(mode="json")},
    )

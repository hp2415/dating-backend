"""Admin commerce: orders / refunds / wallet ledger / credentials."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminUser, Order, Payment, Refund, WalletLedger, WalletLedgerKind
from app.modules.admin.deps import require_perm
from app.modules.commerce.schemas import AdminRefundAction, AdminWalletGrantRequest
from app.modules.commerce.service import CommerceService
from app.modules.commerce.wallet import WalletService
from app.shared.deps import get_db, get_request_id
from app.shared.errors import AppError
from app.shared.pagination import legacy_admin_page
from app.shared.response import ErrorCodes, ok

router = APIRouter(prefix="/admin/v1", tags=["admin-commerce"])


@router.get("/orders")
async def admin_list_orders(
    request: Request,
    q: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("order:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    filters = []
    if kind:
        filters.append(Order.kind == kind)
    if status:
        filters.append(Order.status == status)
    if q:
        filters.append(Order.order_no.ilike(f"%{q}%"))
    count_q = select(func.count()).select_from(Order)
    list_q = select(Order).order_by(Order.created_at.desc())
    for f in filters:
        count_q = count_q.where(f)
        list_q = list_q.where(f)
    total = int((await db.execute(count_q)).scalar_one())
    rows = list((await db.execute(list_q.limit(limit).offset(offset))).scalars().all())
    svc = CommerceService(db)
    return ok(
        legacy_admin_page([svc.order_brief(o) for o in rows], total=total, limit=limit, offset=offset),
        request_id=get_request_id(request),
    )


@router.get("/orders/{order_id}")
async def admin_get_order(
    order_id: UUID,
    request: Request,
    admin: AdminUser = Depends(require_perm("order:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    order = await db.get(Order, order_id)
    if order is None:
        raise AppError(ErrorCodes.ORDER_NOT_FOUND, "订单不存在", status_code=404)
    svc = CommerceService(db)
    pays = list(
        (
            await db.execute(select(Payment).where(Payment.order_id == order_id).order_by(Payment.created_at.desc()))
        ).scalars().all()
    )
    refunds = list(
        (
            await db.execute(select(Refund).where(Refund.order_id == order_id).order_by(Refund.created_at.desc()))
        ).scalars().all()
    )
    return ok(
        {
            "order": svc.order_brief(order),
            "payments": [svc.payment_brief(p) for p in pays],
            "refunds": [svc.refund_brief(r) for r in refunds],
        },
        request_id=get_request_id(request),
    )


@router.post("/orders/{order_id}/close")
async def admin_close_order(
    order_id: UUID,
    request: Request,
    admin: AdminUser = Depends(require_perm("order:write")),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone

    from app.models import OrderStatus

    order = await db.get(Order, order_id)
    if order is None:
        raise AppError(ErrorCodes.ORDER_NOT_FOUND, "订单不存在", status_code=404)
    order.status = OrderStatus.CLOSED.value
    order.closed_at = datetime.now(timezone.utc)
    await db.commit()
    return ok(CommerceService(db).order_brief(order), request_id=get_request_id(request))


@router.get("/refunds")
async def admin_list_refunds(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("order:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    filters = []
    if status:
        filters.append(Refund.status == status)
    count_q = select(func.count()).select_from(Refund)
    list_q = select(Refund).order_by(Refund.created_at.desc())
    for f in filters:
        count_q = count_q.where(f)
        list_q = list_q.where(f)
    total = int((await db.execute(count_q)).scalar_one())
    rows = list((await db.execute(list_q.limit(limit).offset(offset))).scalars().all())
    svc = CommerceService(db)
    return ok(
        legacy_admin_page([svc.refund_brief(r) for r in rows], total=total, limit=limit, offset=offset),
        request_id=get_request_id(request),
    )


@router.post("/refunds/{refund_id}/process")
async def admin_process_refund(
    refund_id: UUID,
    body: AdminRefundAction,
    request: Request,
    admin: AdminUser = Depends(require_perm("order:refund")),
    db: AsyncSession = Depends(get_db),
):
    svc = CommerceService(db)
    if body.action == "reject":
        refund = await svc.complete_refund(refund_id, admin_id=admin.id, reject=True, note=body.admin_note)
    elif body.action == "complete":
        refund = await svc.complete_refund(refund_id, admin_id=admin.id, note=body.admin_note)
    else:
        raise AppError(ErrorCodes.REFUND_INVALID, "无效动作，使用 complete|reject")
    await db.commit()
    return ok(svc.refund_brief(refund), request_id=get_request_id(request))


@router.get("/wallet/ledger")
async def admin_wallet_ledger(
    request: Request,
    user_id: UUID = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    admin: AdminUser = Depends(require_perm("order:read")),
    db: AsyncSession = Depends(get_db),
):
    _ = admin
    wallet = WalletService(db)
    brief = await wallet.brief(user_id)
    items, total = await wallet.list_ledger(user_id, limit=limit, offset=offset)
    recon = await wallet.reconcile_user(user_id)
    return ok(
        {
            "wallet": brief,
            "reconciliation": recon,
            **legacy_admin_page(items, total=total, limit=limit, offset=offset),
        },
        request_id=get_request_id(request),
    )


# Ops/demo wallet credit (not client top-up stub). Body: user_id, amount_cents, title.
@router.post("/wallet/grant")
async def admin_wallet_grant(
    body: AdminWalletGrantRequest,
    request: Request,
    admin: AdminUser = Depends(require_perm("order:write")),
    db: AsyncSession = Depends(get_db),
):
    wallet = WalletService(db)
    entry = await wallet.credit(
        body.user_id,
        amount_cents=body.amount_cents,
        kind=WalletLedgerKind.TOP_UP.value,
        title=body.title.strip() or "运营发放",
        related_order_id=None,
        method="admin",
        subtitle=f"admin:{admin.username}",
    )
    await db.commit()
    brief = await wallet.brief(body.user_id)
    return ok(
        {"wallet": brief, "ledger_id": str(entry.id)},
        request_id=get_request_id(request),
    )


@router.get("/finance/reconciliation")
async def admin_reconciliation(
    request: Request,
    admin: AdminUser = Depends(require_perm("order:read")),
    db: AsyncSession = Depends(get_db),
):
    """Lightweight stub report — full channel bill match later."""
    _ = admin
    orders_paid = int(
        (
            await db.execute(select(func.count()).select_from(Order).where(Order.status == "paid"))
        ).scalar_one()
    )
    refunds_done = int(
        (
            await db.execute(select(func.count()).select_from(Refund).where(Refund.status == "completed"))
        ).scalar_one()
    )
    ledger_count = int((await db.execute(select(func.count()).select_from(WalletLedger))).scalar_one())
    return ok(
        {
            "orders_paid": orders_paid,
            "refunds_completed": refunds_done,
            "wallet_ledger_entries": ledger_count,
            "message": "演示对账摘要；渠道账单三方核对待接真实支付后启用",
            "stub": True,
        },
        request_id=get_request_id(request),
    )

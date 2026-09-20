"""Client commerce APIs: orders / wallet / refunds / membership / credentials."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.modules.commerce.providers import list_pay_methods
from app.modules.commerce.schemas import (
    CreateOrderRequest,
    PayOrderRequest,
    RefundRequest,
    StubNotifyRequest,
    SubscribeRequest,
    TopUpRequest,
)
from app.modules.commerce.service import CommerceService
from app.modules.commerce.wallet import WalletService
from app.shared.deps import get_current_user, get_db, get_request_id
from app.shared.pagination import page_offset
from app.shared.response import ok

router = APIRouter(tags=["commerce"])
internal_router = APIRouter(prefix="/internal/pay", tags=["internal-pay"])


@router.get("/api/v1/pay/methods")
async def pay_methods(request: Request):
    return ok(
        {"items": list_pay_methods(), "stub": True, "message": "微信/支付宝/Apple Pay 为演示通道"},
        request_id=get_request_id(request),
    )


@router.post("/api/v1/orders")
async def create_order(
    body: CreateOrderRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    svc = CommerceService(db)
    order = await svc.create_order(
        user,
        kind=body.kind,
        subject_id=body.subject_id,
        amount_cents=body.amount_cents,
        subject_title=body.subject_title,
        discount_cents=body.discount_cents,
        meta=body.meta,
        idempotency_key=idempotency_key,
    )
    await db.commit()
    return ok(svc.order_brief(order), request_id=get_request_id(request))


@router.get("/api/v1/orders")
async def list_orders(
    request: Request,
    kind: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await CommerceService(db).list_orders(
        user.id, kind=kind, status=status, limit=limit, offset=offset
    )
    return ok(
        page_offset(items, total=total, limit=limit, offset=offset),
        request_id=get_request_id(request),
    )


@router.get("/api/v1/orders/{order_id}")
async def get_order(
    order_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = CommerceService(db)
    order = await svc.get_order(user.id, order_id)
    return ok(svc.order_brief(order), request_id=get_request_id(request))


@router.post("/api/v1/orders/{order_id}/pay")
async def pay_order(
    order_id: UUID,
    body: PayOrderRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CommerceService(db).pay_order(user, order_id, method=body.method)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.post("/api/v1/orders/{order_id}/cancel")
async def cancel_order(
    order_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = CommerceService(db)
    order = await svc.cancel_order(user, order_id)
    await db.commit()
    return ok(svc.order_brief(order), request_id=get_request_id(request))


@router.get("/api/v1/me/wallet")
async def my_wallet(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await WalletService(db).brief(user.id)
    await db.commit()
    return ok(data, request_id=get_request_id(request))


@router.get("/api/v1/me/wallet/ledger")
async def my_wallet_ledger(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await WalletService(db).list_ledger(user.id, limit=limit, offset=offset)
    await db.commit()
    return ok(
        page_offset(items, total=total, limit=limit, offset=offset),
        request_id=get_request_id(request),
    )


@router.post("/api/v1/me/wallet/topup")
async def wallet_topup(
    body: TopUpRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    svc = CommerceService(db)
    order = await svc.create_order(
        user,
        kind="wallet_topup",
        subject_id=None,
        amount_cents=body.amount_cents,
        subject_title=None,
        idempotency_key=idempotency_key,
    )
    pay = await svc.pay_order(user, order.id, method=body.method)
    await db.commit()
    return ok(pay, request_id=get_request_id(request))


@router.post("/api/v1/refunds")
async def create_refund(
    body: RefundRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = CommerceService(db)
    refund = await svc.submit_refund(
        user,
        order_id=body.order_id,
        reason=body.reason,
        detail=body.detail,
        amount_cents=body.amount_cents,
    )
    await db.commit()
    return ok(svc.refund_brief(refund), request_id=get_request_id(request))


@router.get("/api/v1/me/refunds")
async def my_refunds(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await CommerceService(db).list_refunds(user.id, limit=limit, offset=offset)
    return ok(
        page_offset(items, total=total, limit=limit, offset=offset),
        request_id=get_request_id(request),
    )


@router.get("/api/v1/refunds/{refund_id}")
async def get_refund(
    refund_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models import Refund
    from app.shared.errors import AppError
    from app.shared.response import ErrorCodes

    refund = await db.get(Refund, refund_id)
    if refund is None or refund.user_id != user.id:
        raise AppError(ErrorCodes.REFUND_NOT_FOUND, "退款单不存在", status_code=404)
    return ok(CommerceService(db).refund_brief(refund), request_id=get_request_id(request))


@router.get("/api/v1/membership/plans")
async def membership_plans(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    items = await CommerceService(db).list_plans()
    return ok({"items": items}, request_id=get_request_id(request))


@router.get("/api/v1/me/membership")
async def my_membership(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await CommerceService(db).my_membership(user.id)
    return ok({"membership": data}, request_id=get_request_id(request))


@router.post("/api/v1/membership/subscribe")
async def subscribe_membership(
    body: SubscribeRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    svc = CommerceService(db)
    order = await svc.create_order(
        user,
        kind="membership",
        subject_id=body.plan_id,
        amount_cents=None,
        subject_title=None,
        meta={"plan_code": body.plan_code},
        idempotency_key=idempotency_key,
    )
    pay = await svc.pay_order(user, order.id, method=body.method)
    await db.commit()
    membership = await svc.my_membership(user.id)
    pay["membership"] = membership
    return ok(pay, request_id=get_request_id(request))


@router.get("/api/v1/me/credentials")
async def my_credentials(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await CommerceService(db).list_credentials(user.id, limit=limit, offset=offset)
    return ok(
        page_offset(items, total=total, limit=limit, offset=offset),
        request_id=get_request_id(request),
    )


@router.get("/api/v1/credentials/{credential_id}")
async def get_credential(
    credential_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = CommerceService(db)
    cred = await svc.get_credential(user.id, credential_id)
    return ok(svc.credential_brief(cred), request_id=get_request_id(request))


@router.get("/api/v1/credentials/{credential_id}/pkpass")
async def get_credential_pkpass(
    credential_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = CommerceService(db)
    cred = await svc.get_credential(user.id, credential_id)
    brief = svc.credential_brief(cred)
    brief.update(
        {
            "pkpass_ready": False,
            "download_url": None,
            "message": "PassKit 包生成预留，当前返回票面 JSON",
        }
    )
    return ok(brief, request_id=get_request_id(request))


@internal_router.post("/notify/{provider}")
async def payment_notify(
    provider: str,
    body: StubNotifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Stub / future real callback. No auth — signature check inside provider."""
    data = await CommerceService(db).handle_notify(
        provider,
        {
            "provider_txn_id": body.provider_txn_id,
            "amount_cents": body.amount_cents,
            "success": body.success,
        },
    )
    await db.commit()
    return ok(data, request_id=get_request_id(request))

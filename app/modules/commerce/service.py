"""Order / payment / refund / membership / credential orchestration."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Activity,
    ActivityStatus,
    Credential,
    CredentialStatus,
    CredentialStyle,
    Membership,
    MembershipPlan,
    MembershipStatus,
    Order,
    OrderKind,
    OrderStatus,
    PayMethod,
    Payment,
    PaymentStatus,
    Refund,
    RefundInitiator,
    RefundStatus,
    User,
    WalletLedgerKind,
)
from app.modules.commerce.providers import get_payment_provider, list_pay_methods
from app.modules.commerce.wallet import WalletService
from app.modules.events.service import DomainEventName, DomainEventService
from app.shared.config import settings
from app.shared.errors import AppError
from app.shared.response import ErrorCodes

PAYABLE_STATUSES = {OrderStatus.CREATED.value, OrderStatus.PENDING_PAYMENT.value}
REFUNDABLE = {OrderStatus.PAID.value}


def _order_no() -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"SP{now}{secrets.token_hex(3).upper()}"


def _serial_no(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(8).upper()}"


class CommerceService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.wallet = WalletService(db)
        self.events = DomainEventService(db)

    # ── Orders ─────────────────────────────────────────────

    async def create_order(
        self,
        user: User,
        *,
        kind: str,
        subject_id: UUID | None,
        amount_cents: int | None,
        subject_title: str | None,
        discount_cents: int = 0,
        meta: dict | None = None,
        idempotency_key: str | None = None,
    ) -> Order:
        if kind not in {k.value for k in OrderKind}:
            raise AppError(ErrorCodes.ORDER_INVALID, "无效的订单类型")

        if idempotency_key:
            existing = await self.db.execute(
                select(Order).where(
                    Order.user_id == user.id,
                    Order.idempotency_key == idempotency_key,
                )
            )
            hit = existing.scalar_one_or_none()
            if hit is not None:
                return hit

        title = subject_title or ""
        cents = amount_cents
        resolved_subject = subject_id

        if kind == OrderKind.ACTIVITY.value:
            if subject_id is None:
                raise AppError(ErrorCodes.ORDER_INVALID, "缺少活动 ID")
            activity = await self.db.get(Activity, subject_id)
            if activity is None or activity.status == ActivityStatus.CANCELLED.value:
                raise AppError(ErrorCodes.ACTIVITY_NOT_FOUND, "活动不存在", status_code=404)
            if activity.status != ActivityStatus.PUBLISHED.value:
                raise AppError(ErrorCodes.ORDER_INVALID, "活动未公开，无法下单")
            title = title or activity.title
            # Demo fee: use meta.fee_cents or default 0 (free join still creates ¥0 paid order)
            if cents is None:
                cents = int((meta or {}).get("fee_cents") or 0)

        elif kind == OrderKind.MEMBERSHIP.value:
            plan = await self._resolve_plan(subject_id, meta)
            resolved_subject = plan.id
            title = title or plan.title
            cents = plan.price_cents if cents is None else cents

        elif kind == OrderKind.WALLET_TOPUP.value:
            if cents is None or cents < 100:
                raise AppError(ErrorCodes.ORDER_INVALID, "充值金额至少 ¥1")
            title = title or f"钱包充值 {_fmt(cents)}"

        elif kind == OrderKind.COMPANION_BOOKING.value:
            if cents is None or cents <= 0:
                raise AppError(ErrorCodes.ORDER_INVALID, "预约金额无效")
            if subject_id is not None:
                from app.models import CompanionBooking

                booking = await self.db.get(CompanionBooking, subject_id)
                if booking is None:
                    raise AppError(ErrorCodes.BOOKING_NOT_FOUND, "预约不存在", status_code=404)
                title = title or "陪玩预约"
                cents = booking.amount_cents if amount_cents is None else cents
            else:
                title = title or "陪玩预约"

        if cents is None or cents < 0:
            raise AppError(ErrorCodes.ORDER_INVALID, "订单金额无效")
        discount = max(0, discount_cents)
        payable = max(0, cents - discount)

        now = datetime.now(timezone.utc)
        order = Order(
            id=uuid4(),
            order_no=_order_no(),
            user_id=user.id,
            kind=kind,
            subject_id=resolved_subject,
            subject_title=title,
            amount_cents=cents,
            discount_cents=discount,
            payable_cents=payable,
            status=OrderStatus.PENDING_PAYMENT.value if payable > 0 else OrderStatus.CREATED.value,
            expire_at=now + timedelta(minutes=settings.order_expire_minutes),
            idempotency_key=idempotency_key,
            meta=meta or {},
        )
        self.db.add(order)
        await self.db.flush()

        if payable == 0:
            order.pay_method = PayMethod.WALLET.value
            await self._on_paid(order, provider="wallet", provider_txn_id=f"free_{order.order_no}")
        return order

    async def list_orders(
        self,
        user_id: UUID,
        *,
        kind: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict], int]:
        filters = [Order.user_id == user_id]
        if kind:
            filters.append(Order.kind == kind)
        if status:
            filters.append(Order.status == status)
        count_q = select(func.count()).select_from(Order)
        list_q = select(Order).order_by(Order.created_at.desc())
        for f in filters:
            count_q = count_q.where(f)
            list_q = list_q.where(f)
        total = int((await self.db.execute(count_q)).scalar_one())
        rows = list((await self.db.execute(list_q.limit(limit).offset(offset))).scalars().all())
        return [self.order_brief(o) for o in rows], total

    async def get_order(self, user_id: UUID, order_id: UUID) -> Order:
        order = await self.db.get(Order, order_id)
        if order is None or order.user_id != user_id:
            raise AppError(ErrorCodes.ORDER_NOT_FOUND, "订单不存在", status_code=404)
        return order

    async def cancel_order(self, user: User, order_id: UUID) -> Order:
        order = await self.get_order(user.id, order_id)
        if order.status not in PAYABLE_STATUSES:
            raise AppError(ErrorCodes.ORDER_INVALID, "当前状态不可取消", status_code=409)
        order.status = OrderStatus.CANCELLED.value
        order.closed_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.events.enqueue(
            name=DomainEventName.ORDER_CANCELLED,
            aggregate_kind="order",
            aggregate_id=order.id,
            payload={"order_no": order.order_no, "user_id": str(user.id)},
        )
        return order

    async def pay_order(self, user: User, order_id: UUID, *, method: str) -> dict[str, Any]:
        order = await self.get_order(user.id, order_id)
        await self._expire_if_needed(order)
        if order.status == OrderStatus.PAID.value:
            return {"order": self.order_brief(order), "already_paid": True}
        if order.status not in PAYABLE_STATUSES:
            raise AppError(ErrorCodes.ORDER_INVALID, "订单不可支付", status_code=409)
        if method not in {m.value for m in PayMethod}:
            raise AppError(ErrorCodes.ORDER_INVALID, "不支持的支付方式")
        if order.kind == OrderKind.WALLET_TOPUP.value and method == PayMethod.WALLET.value:
            raise AppError(ErrorCodes.ORDER_INVALID, "充值不能使用钱包余额")

        provider = get_payment_provider(method)
        intent = await provider.create_charge(
            order_id=order.id,
            order_no=order.order_no,
            amount_cents=order.payable_cents,
            description=order.subject_title,
            user_id=user.id,
        )
        payment = Payment(
            id=uuid4(),
            order_id=order.id,
            provider=intent.provider,
            provider_txn_id=intent.provider_txn_id,
            amount_cents=order.payable_cents,
            status=PaymentStatus.PENDING.value,
            client_params=intent.client_params,
        )
        self.db.add(payment)
        order.pay_method = method
        order.status = OrderStatus.PENDING_PAYMENT.value
        await self.db.flush()

        if intent.immediate:
            if method == PayMethod.WALLET.value:
                ledger_kind = self._wallet_debit_kind(order.kind)
                await self.wallet.charge(
                    user.id,
                    amount_cents=order.payable_cents,
                    kind=ledger_kind,
                    title=order.subject_title,
                    related_order_id=order.id,
                    method=method,
                )
            await self._settle_payment(payment, order, success=True, raw={"mode": "immediate"})

        return {
            "order": self.order_brief(order),
            "payment": self.payment_brief(payment),
            "client_params": payment.client_params,
            "pay_methods": list_pay_methods(),
        }

    async def handle_notify(self, provider: str, payload: dict[str, Any]) -> dict[str, Any]:
        channel = get_payment_provider(provider)
        verified = await channel.verify_notify(payload)
        txn = verified.get("provider_txn_id") or ""
        if not txn:
            raise AppError(ErrorCodes.PAYMENT_INVALID, "缺少支付流水号")
        result = await self.db.execute(select(Payment).where(Payment.provider_txn_id == txn))
        payment = result.scalar_one_or_none()
        if payment is None:
            raise AppError(ErrorCodes.PAYMENT_NOT_FOUND, "支付单不存在", status_code=404)
        order = await self.db.get(Order, payment.order_id)
        if order is None:
            raise AppError(ErrorCodes.ORDER_NOT_FOUND, "订单不存在", status_code=404)
        if payment.status == PaymentStatus.SUCCEEDED.value:
            return {"ok": True, "duplicate": True, "order": self.order_brief(order)}
        if not verified.get("success"):
            payment.status = PaymentStatus.FAILED.value
            payment.raw_notify = payload
            await self.db.flush()
            return {"ok": False, "order": self.order_brief(order)}
        await self._settle_payment(payment, order, success=True, raw=payload)
        return {"ok": True, "order": self.order_brief(order)}

    async def _settle_payment(
        self, payment: Payment, order: Order, *, success: bool, raw: dict | None
    ) -> None:
        if not success:
            payment.status = PaymentStatus.FAILED.value
            payment.raw_notify = raw
            await self.db.flush()
            return
        payment.status = PaymentStatus.SUCCEEDED.value
        payment.raw_notify = raw
        payment.notified_at = datetime.now(timezone.utc)
        await self._on_paid(order, provider=payment.provider, provider_txn_id=payment.provider_txn_id or "")

    async def _on_paid(self, order: Order, *, provider: str, provider_txn_id: str) -> None:
        if order.status == OrderStatus.PAID.value:
            return
        now = datetime.now(timezone.utc)
        order.status = OrderStatus.PAID.value
        order.paid_at = now
        order.pay_method = order.pay_method or provider

        if order.kind == OrderKind.WALLET_TOPUP.value:
            await self.wallet.credit(
                order.user_id,
                amount_cents=order.payable_cents,
                kind=WalletLedgerKind.TOP_UP.value,
                title="钱包充值",
                related_order_id=order.id,
                method=provider,
            )
        elif order.kind == OrderKind.MEMBERSHIP.value:
            await self._activate_membership(order)
        elif order.kind == OrderKind.ACTIVITY.value:
            await self._issue_activity_credential(order)
        elif order.kind == OrderKind.COMPANION_BOOKING.value:
            await self._issue_booking_credential(order)
            if order.subject_id:
                from app.modules.companion.service import CompanionServiceLayer

                await CompanionServiceLayer(self.db).mark_booking_paid(order.subject_id)

        await self.events.enqueue(
            name=DomainEventName.ORDER_PAID,
            aggregate_kind="order",
            aggregate_id=order.id,
            payload={
                "order_no": order.order_no,
                "kind": order.kind,
                "user_id": str(order.user_id),
                "amount_cents": order.payable_cents,
                "provider": provider,
                "provider_txn_id": provider_txn_id,
            },
        )
        await self.db.flush()

    # ── Refunds ────────────────────────────────────────────

    async def submit_refund(
        self,
        user: User,
        *,
        order_id: UUID,
        reason: str,
        detail: str = "",
        amount_cents: int | None = None,
    ) -> Refund:
        order = await self.get_order(user.id, order_id)
        if order.status not in REFUNDABLE:
            raise AppError(ErrorCodes.REFUND_INVALID, "订单当前不可退款", status_code=409)
        cents = amount_cents if amount_cents is not None else order.payable_cents
        if cents <= 0 or cents > order.payable_cents:
            raise AppError(ErrorCodes.REFUND_INVALID, "退款金额无效")

        refund = Refund(
            id=uuid4(),
            order_id=order.id,
            user_id=user.id,
            amount_cents=cents,
            reason=reason[:120],
            detail=(detail or "")[:500],
            initiator=RefundInitiator.USER.value,
            status=RefundStatus.SUBMITTED.value,
        )
        order.status = OrderStatus.REFUNDING.value
        self.db.add(refund)
        await self.db.flush()

        # Stub / wallet: auto-process for demo effect
        if settings.payment_stub_auto_complete or order.pay_method == PayMethod.WALLET.value:
            await self.complete_refund(refund.id, admin_id=None, auto=True)
            refund = await self.db.get(Refund, refund.id)
        return refund  # type: ignore[return-value]

    async def complete_refund(
        self,
        refund_id: UUID,
        *,
        admin_id: UUID | None,
        auto: bool = False,
        reject: bool = False,
        note: str | None = None,
    ) -> Refund:
        refund = await self.db.get(Refund, refund_id)
        if refund is None:
            raise AppError(ErrorCodes.REFUND_NOT_FOUND, "退款单不存在", status_code=404)
        if refund.status in {RefundStatus.COMPLETED.value, RefundStatus.REJECTED.value}:
            return refund
        order = await self.db.get(Order, refund.order_id)
        if order is None:
            raise AppError(ErrorCodes.ORDER_NOT_FOUND, "订单不存在", status_code=404)

        now = datetime.now(timezone.utc)
        refund.processing_started_at = refund.processing_started_at or now
        refund.admin_id = admin_id
        refund.admin_note = note

        if reject:
            refund.status = RefundStatus.REJECTED.value
            refund.rejection_message = note or "已驳回"
            refund.completed_at = now
            order.status = OrderStatus.PAID.value
            await self.db.flush()
            return refund

        method = order.pay_method or PayMethod.WALLET.value
        provider = get_payment_provider(method)
        # Find succeeded payment txn
        pay_row = await self.db.execute(
            select(Payment)
            .where(Payment.order_id == order.id, Payment.status == PaymentStatus.SUCCEEDED.value)
            .order_by(Payment.created_at.desc())
            .limit(1)
        )
        payment = pay_row.scalar_one_or_none()
        txn = payment.provider_txn_id if payment else f"manual_{order.order_no}"
        result = await provider.create_refund(
            provider_txn_id=txn or "",
            amount_cents=refund.amount_cents,
            reason=refund.reason,
        )
        refund.provider_refund_id = result.get("provider_refund_id")
        refund.status = RefundStatus.COMPLETED.value
        refund.completed_at = now
        order.status = OrderStatus.REFUNDED.value
        order.closed_at = now

        # Credit wallet for wallet payments or always credit wallet for stub demo? 
        # Design: refund to original channel; for stub we credit wallet so user sees effect.
        credit_kind = (
            WalletLedgerKind.ACTIVITY_REFUND.value
            if order.kind == OrderKind.ACTIVITY.value
            else WalletLedgerKind.BOOKING_REFUND.value
            if order.kind == OrderKind.COMPANION_BOOKING.value
            else WalletLedgerKind.TOP_UP.value
        )
        if method == PayMethod.WALLET.value or settings.payment_refund_to_wallet:
            await self.wallet.credit(
                order.user_id,
                amount_cents=refund.amount_cents,
                kind=credit_kind,
                title=f"退款 · {order.subject_title}",
                related_order_id=order.id,
                method=method,
                subtitle=refund.reason,
            )

        if order.kind == OrderKind.MEMBERSHIP.value:
            await self._revoke_membership_for_order(order)

        await self.events.enqueue(
            name=DomainEventName.ORDER_REFUNDED,
            aggregate_kind="order",
            aggregate_id=order.id,
            payload={
                "refund_id": str(refund.id),
                "amount_cents": refund.amount_cents,
                "auto": auto,
            },
        )
        await self.db.flush()
        return refund

    async def list_refunds(self, user_id: UUID, *, limit: int, offset: int) -> tuple[list[dict], int]:
        count_q = select(func.count()).select_from(Refund).where(Refund.user_id == user_id)
        total = int((await self.db.execute(count_q)).scalar_one())
        result = await self.db.execute(
            select(Refund)
            .where(Refund.user_id == user_id)
            .order_by(Refund.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [self.refund_brief(r) for r in result.scalars().all()], total

    # ── Membership / credentials ───────────────────────────

    async def list_plans(self) -> list[dict]:
        result = await self.db.execute(
            select(MembershipPlan)
            .where(MembershipPlan.active.is_(True))
            .order_by(MembershipPlan.sort_order.asc())
        )
        return [self.plan_brief(p) for p in result.scalars().all()]

    async def my_membership(self, user_id: UUID) -> dict | None:
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(Membership)
            .where(
                Membership.user_id == user_id,
                Membership.status == MembershipStatus.ACTIVE.value,
                Membership.expires_at > now,
            )
            .order_by(Membership.expires_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return self.membership_brief(row) if row else None

    async def list_credentials(self, user_id: UUID, *, limit: int, offset: int) -> tuple[list[dict], int]:
        count_q = select(func.count()).select_from(Credential).where(Credential.user_id == user_id)
        total = int((await self.db.execute(count_q)).scalar_one())
        result = await self.db.execute(
            select(Credential)
            .where(Credential.user_id == user_id)
            .order_by(Credential.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [self.credential_brief(c) for c in result.scalars().all()], total

    async def get_credential(self, user_id: UUID, credential_id: UUID) -> Credential:
        cred = await self.db.get(Credential, credential_id)
        if cred is None or cred.user_id != user_id:
            raise AppError(ErrorCodes.CREDENTIAL_NOT_FOUND, "凭证不存在", status_code=404)
        return cred

    async def expire_unpaid_orders(self, *, limit: int = 100) -> int:
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(Order)
            .where(
                Order.status.in_(list(PAYABLE_STATUSES)),
                Order.expire_at.is_not(None),
                Order.expire_at < now,
            )
            .limit(limit)
        )
        rows = list(result.scalars().all())
        for order in rows:
            order.status = OrderStatus.CANCELLED.value
            order.closed_at = now
        await self.db.flush()
        return len(rows)

    # ── internals ──────────────────────────────────────────

    async def _resolve_plan(self, subject_id: UUID | None, meta: dict | None) -> MembershipPlan:
        if subject_id is not None:
            plan = await self.db.get(MembershipPlan, subject_id)
            if plan and plan.active:
                return plan
        code = (meta or {}).get("plan_code") or "monthly"
        result = await self.db.execute(select(MembershipPlan).where(MembershipPlan.code == code))
        plan = result.scalar_one_or_none()
        if plan is None or not plan.active:
            raise AppError(ErrorCodes.ORDER_INVALID, "会员套餐不存在")
        return plan

    async def _activate_membership(self, order: Order) -> Membership:
        plan = await self._resolve_plan(order.subject_id, order.meta)
        now = datetime.now(timezone.utc)
        existing = await self.my_membership(order.user_id)
        start = now
        if existing:
            # Extend from current expiry
            exp = datetime.fromisoformat(existing["expires_at"].replace("Z", "+00:00"))
            if exp > now:
                start = exp
        membership = Membership(
            id=uuid4(),
            user_id=order.user_id,
            plan_code=plan.code,
            status=MembershipStatus.ACTIVE.value,
            started_at=now,
            expires_at=start + timedelta(days=plan.duration_days),
            auto_renew=False,
            source_order_id=order.id,
        )
        self.db.add(membership)
        await self.db.flush()
        await self._issue_membership_credential(order, membership, plan)
        return membership

    async def _revoke_membership_for_order(self, order: Order) -> None:
        result = await self.db.execute(
            select(Membership).where(Membership.source_order_id == order.id)
        )
        for m in result.scalars().all():
            m.status = MembershipStatus.CANCELLED.value

    async def _issue_activity_credential(self, order: Order) -> Credential:
        cred = Credential(
            id=uuid4(),
            user_id=order.user_id,
            style=CredentialStyle.EVENT_TICKET.value,
            serial_no=_serial_no("ACT"),
            related_kind="order",
            related_id=order.id,
            fields={
                "primary": [{"key": "event", "label": "活动", "value": order.subject_title}],
                "secondary": [{"key": "order", "label": "订单号", "value": order.order_no}],
            },
            barcode_message=order.order_no,
            relevant_at=order.paid_at,
            status=CredentialStatus.VALID.value,
        )
        self.db.add(cred)
        await self.db.flush()
        return cred

    async def _issue_booking_credential(self, order: Order) -> Credential:
        cred = Credential(
            id=uuid4(),
            user_id=order.user_id,
            style=CredentialStyle.EVENT_TICKET.value,
            serial_no=_serial_no("BKG"),
            related_kind="order",
            related_id=order.id,
            fields={
                "primary": [{"key": "booking", "label": "预约", "value": order.subject_title}],
                "secondary": [{"key": "order", "label": "订单号", "value": order.order_no}],
            },
            barcode_message=order.order_no,
            relevant_at=order.paid_at,
            status=CredentialStatus.VALID.value,
        )
        self.db.add(cred)
        await self.db.flush()
        return cred

    async def _issue_membership_credential(
        self, order: Order, membership: Membership, plan: MembershipPlan
    ) -> Credential:
        cred = Credential(
            id=uuid4(),
            user_id=order.user_id,
            style=CredentialStyle.STORE_CARD.value,
            serial_no=_serial_no("VIP"),
            related_kind="membership",
            related_id=membership.id,
            fields={
                "primary": [{"key": "plan", "label": "会员", "value": plan.title}],
                "secondary": [
                    {
                        "key": "expires",
                        "label": "有效期至",
                        "value": membership.expires_at.strftime("%Y-%m-%d"),
                    }
                ],
            },
            barcode_message=membership.id.hex[:16].upper(),
            expires_at=membership.expires_at,
            status=CredentialStatus.VALID.value,
        )
        self.db.add(cred)
        await self.db.flush()
        return cred

    async def _expire_if_needed(self, order: Order) -> None:
        if (
            order.status in PAYABLE_STATUSES
            and order.expire_at
            and order.expire_at < datetime.now(timezone.utc)
        ):
            order.status = OrderStatus.CANCELLED.value
            order.closed_at = datetime.now(timezone.utc)
            await self.db.flush()
            raise AppError(ErrorCodes.ORDER_EXPIRED, "订单已超时关闭", status_code=409)

    @staticmethod
    def _wallet_debit_kind(order_kind: str) -> str:
        if order_kind == OrderKind.ACTIVITY.value:
            return WalletLedgerKind.ACTIVITY_PAYMENT.value
        if order_kind == OrderKind.COMPANION_BOOKING.value:
            return WalletLedgerKind.BOOKING_PAYMENT.value
        if order_kind == OrderKind.MEMBERSHIP.value:
            return WalletLedgerKind.MEMBERSHIP.value
        return WalletLedgerKind.ACTIVITY_PAYMENT.value

    def order_brief(self, order: Order) -> dict:
        return {
            "id": str(order.id),
            "order_no": order.order_no,
            "kind": order.kind,
            "subject_id": str(order.subject_id) if order.subject_id else None,
            "subject_title": order.subject_title,
            "amount_cents": order.amount_cents,
            "discount_cents": order.discount_cents,
            "payable_cents": order.payable_cents,
            "payable_display": _fmt(order.payable_cents),
            "status": order.status,
            "pay_method": order.pay_method,
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            "expire_at": order.expire_at.isoformat() if order.expire_at else None,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "meta": order.meta or {},
        }

    def payment_brief(self, payment: Payment) -> dict:
        return {
            "id": str(payment.id),
            "order_id": str(payment.order_id),
            "provider": payment.provider,
            "provider_txn_id": payment.provider_txn_id,
            "amount_cents": payment.amount_cents,
            "status": payment.status,
            "created_at": payment.created_at.isoformat() if payment.created_at else None,
        }

    def refund_brief(self, refund: Refund) -> dict:
        return {
            "id": str(refund.id),
            "order_id": str(refund.order_id),
            "amount_cents": refund.amount_cents,
            "amount_display": _fmt(refund.amount_cents),
            "reason": refund.reason,
            "detail": refund.detail,
            "initiator": refund.initiator,
            "status": refund.status,
            "rejection_message": refund.rejection_message,
            "completed_at": refund.completed_at.isoformat() if refund.completed_at else None,
            "created_at": refund.created_at.isoformat() if refund.created_at else None,
        }

    def plan_brief(self, plan: MembershipPlan) -> dict:
        return {
            "id": str(plan.id),
            "code": plan.code,
            "title": plan.title,
            "price_cents": plan.price_cents,
            "price_display": _fmt(plan.price_cents),
            "duration_days": plan.duration_days,
            "benefits": plan.benefits or [],
        }

    def membership_brief(self, m: Membership) -> dict:
        return {
            "id": str(m.id),
            "plan_code": m.plan_code,
            "status": m.status,
            "started_at": m.started_at.isoformat(),
            "expires_at": m.expires_at.isoformat(),
            "auto_renew": m.auto_renew,
            "source_order_id": str(m.source_order_id) if m.source_order_id else None,
        }

    def credential_brief(self, c: Credential) -> dict:
        return {
            "id": str(c.id),
            "style": c.style,
            "serial_no": c.serial_no,
            "related_kind": c.related_kind,
            "related_id": str(c.related_id) if c.related_id else None,
            "fields": c.fields or {},
            "barcode_message": c.barcode_message,
            "relevant_at": c.relevant_at.isoformat() if c.relevant_at else None,
            "expires_at": c.expires_at.isoformat() if c.expires_at else None,
            "status": c.status,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "pkpass_ready": False,
            "message": "PassKit 包生成预留；当前返回结构化票面字段",
        }


def _fmt(cents: int) -> str:
    return f"¥{cents / 100:.2f}"

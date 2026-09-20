"""Wallet ledger + optimistic-lock balance updates."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    WalletAccount,
    WalletLedger,
    WalletLedgerKind,
)
from app.shared.config import settings
from app.shared.errors import AppError
from app.shared.response import ErrorCodes


class WalletService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ensure_account(self, user_id: UUID, *, grant_welcome: bool = True) -> WalletAccount:
        account = await self.db.get(WalletAccount, user_id)
        if account is not None:
            return account
        account = WalletAccount(user_id=user_id, balance_cents=0, frozen_cents=0, version=0)
        self.db.add(account)
        await self.db.flush()
        if grant_welcome and settings.wallet_welcome_cents > 0:
            await self._credit(
                account,
                delta=settings.wallet_welcome_cents,
                kind=WalletLedgerKind.WELCOME.value,
                title="欢迎加入坐标系",
                subtitle="新用户体验金",
                amount_cents=settings.wallet_welcome_cents,
                method="system",
                related_order_id=None,
            )
        return account

    async def get_or_create(self, user_id: UUID) -> WalletAccount:
        return await self.ensure_account(user_id)

    async def brief(self, user_id: UUID) -> dict:
        account = await self.ensure_account(user_id)
        return {
            "balance_cents": int(account.balance_cents),
            "frozen_cents": int(account.frozen_cents),
            "balance_display": _format_cents(account.balance_cents),
            "version": account.version,
        }

    async def list_ledger(self, user_id: UUID, *, limit: int, offset: int) -> tuple[list[dict], int]:
        await self.ensure_account(user_id)
        total = int(
            (
                await self.db.execute(
                    select(func.count()).select_from(WalletLedger).where(WalletLedger.user_id == user_id)
                )
            ).scalar_one()
        )
        result = await self.db.execute(
            select(WalletLedger)
            .where(WalletLedger.user_id == user_id)
            .order_by(WalletLedger.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list(result.scalars().all())
        return [_ledger_brief(r) for r in rows], total

    async def charge(
        self,
        user_id: UUID,
        *,
        amount_cents: int,
        kind: str,
        title: str,
        related_order_id: UUID | None,
        method: str = "wallet",
        subtitle: str | None = None,
    ) -> WalletLedger:
        if amount_cents <= 0:
            raise AppError(ErrorCodes.ORDER_INVALID, "扣款金额无效")
        account = await self.ensure_account(user_id, grant_welcome=True)
        if account.balance_cents < amount_cents:
            raise AppError(ErrorCodes.WALLET_INSUFFICIENT, "钱包余额不足", status_code=400)
        return await self._credit(
            account,
            delta=-amount_cents,
            kind=kind,
            title=title,
            subtitle=subtitle,
            amount_cents=amount_cents,
            method=method,
            related_order_id=related_order_id,
        )

    async def credit(
        self,
        user_id: UUID,
        *,
        amount_cents: int,
        kind: str,
        title: str,
        related_order_id: UUID | None,
        method: str | None = None,
        subtitle: str | None = None,
    ) -> WalletLedger:
        if amount_cents <= 0:
            raise AppError(ErrorCodes.ORDER_INVALID, "入账金额无效")
        account = await self.ensure_account(user_id, grant_welcome=False)
        return await self._credit(
            account,
            delta=amount_cents,
            kind=kind,
            title=title,
            subtitle=subtitle,
            amount_cents=amount_cents,
            method=method,
            related_order_id=related_order_id,
        )

    async def _credit(
        self,
        account: WalletAccount,
        *,
        delta: int,
        kind: str,
        title: str,
        subtitle: str | None,
        amount_cents: int,
        method: str | None,
        related_order_id: UUID | None,
    ) -> WalletLedger:
        # Optimistic lock: bump version; caller must commit in same transaction.
        expected = account.version
        account.balance_cents = int(account.balance_cents) + delta
        account.version = expected + 1
        if account.balance_cents < 0:
            raise AppError(ErrorCodes.WALLET_INSUFFICIENT, "钱包余额不足", status_code=400)
        entry = WalletLedger(
            id=uuid4(),
            user_id=account.user_id,
            kind=kind,
            title=title,
            subtitle=subtitle,
            balance_delta_cents=delta,
            amount_cents=amount_cents,
            balance_after_cents=int(account.balance_cents),
            related_order_id=related_order_id,
            method=method,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def reconcile_user(self, user_id: UUID) -> dict:
        account = await self.ensure_account(user_id, grant_welcome=False)
        result = await self.db.execute(select(WalletLedger).where(WalletLedger.user_id == user_id))
        rows = list(result.scalars().all())
        ledger_sum = sum(int(r.balance_delta_cents) for r in rows)
        ok = ledger_sum == int(account.balance_cents)
        return {
            "user_id": str(user_id),
            "balance_cents": int(account.balance_cents),
            "ledger_sum_cents": ledger_sum,
            "ok": ok,
        }


def _format_cents(cents: int) -> str:
    return f"¥{cents / 100:.2f}"


def _ledger_brief(row: WalletLedger) -> dict:
    return {
        "id": str(row.id),
        "kind": row.kind,
        "title": row.title,
        "subtitle": row.subtitle,
        "balance_delta_cents": int(row.balance_delta_cents),
        "amount_cents": int(row.amount_cents),
        "balance_after_cents": int(row.balance_after_cents),
        "related_order_id": str(row.related_order_id) if row.related_order_id else None,
        "method": row.method,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }

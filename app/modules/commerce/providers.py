"""Payment channel adapters.

``payment_provider=stub`` (default): wechat / alipay / apple_pay return mock client
params and auto-complete via ``/internal/pay/notify/{provider}`` or immediate simulate.

Swap to real SDKs later without changing order/wallet orchestration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from app.shared.config import settings


@dataclass
class ChargeIntent:
    provider: str
    provider_txn_id: str
    client_params: dict[str, Any]
    immediate: bool  # True => settle in-process (wallet / stub simulate)


class PaymentProvider(ABC):
    name: str

    @abstractmethod
    async def create_charge(
        self,
        *,
        order_id: UUID,
        order_no: str,
        amount_cents: int,
        description: str,
        user_id: UUID,
    ) -> ChargeIntent: ...

    @abstractmethod
    async def verify_notify(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate callback and return normalized {provider_txn_id, amount_cents, success}."""

    @abstractmethod
    async def create_refund(
        self,
        *,
        provider_txn_id: str,
        amount_cents: int,
        reason: str,
    ) -> dict[str, Any]:
        """Return {provider_refund_id, success, stub}."""


class WalletPaymentProvider(PaymentProvider):
    name = "wallet"

    async def create_charge(self, *, order_id, order_no, amount_cents, description, user_id) -> ChargeIntent:
        return ChargeIntent(
            provider=self.name,
            provider_txn_id=f"wallet_{order_no}",
            client_params={"mode": "wallet", "ready": True},
            immediate=True,
        )

    async def verify_notify(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "provider_txn_id": payload.get("provider_txn_id", ""),
            "amount_cents": int(payload.get("amount_cents") or 0),
            "success": True,
        }

    async def create_refund(self, *, provider_txn_id: str, amount_cents: int, reason: str) -> dict[str, Any]:
        return {
            "provider_refund_id": f"wallet_rf_{uuid4().hex[:16]}",
            "success": True,
            "stub": False,
        }


class StubChannelProvider(PaymentProvider):
    """Fake WeChat / Alipay / Apple Pay — demo UX only."""

    def __init__(self, name: str):
        self.name = name

    async def create_charge(self, *, order_id, order_no, amount_cents, description, user_id) -> ChargeIntent:
        txn = f"stub_{self.name}_{order_no}"
        return ChargeIntent(
            provider=self.name,
            provider_txn_id=txn,
            client_params={
                "mode": "stub",
                "provider": self.name,
                "ready": True,
                "message": f"{self.name} 为演示通道，确认支付将立即成功",
                "prepay_id": txn,
                "order_no": order_no,
                "amount_cents": amount_cents,
                "simulate_notify_url": f"/internal/pay/notify/{self.name}",
                "auto_complete": settings.payment_stub_auto_complete,
            },
            # When auto_complete, orchestration settles immediately after create.
            immediate=bool(settings.payment_stub_auto_complete),
        )

    async def verify_notify(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Stub: accept any payload that carries our txn id; no signature check.
        return {
            "provider_txn_id": str(payload.get("provider_txn_id") or payload.get("prepay_id") or ""),
            "amount_cents": int(payload.get("amount_cents") or 0),
            "success": bool(payload.get("success", True)),
            "stub": True,
        }

    async def create_refund(self, *, provider_txn_id: str, amount_cents: int, reason: str) -> dict[str, Any]:
        return {
            "provider_refund_id": f"stub_rf_{uuid4().hex[:16]}",
            "success": True,
            "stub": True,
            "message": "演示退款已即时完成",
        }


_PROVIDERS: dict[str, PaymentProvider] = {
    "wallet": WalletPaymentProvider(),
    "wechat": StubChannelProvider("wechat"),
    "alipay": StubChannelProvider("alipay"),
    "apple_pay": StubChannelProvider("apple_pay"),
}


def get_payment_provider(method: str) -> PaymentProvider:
    key = (method or "").strip().lower()
    provider = _PROVIDERS.get(key)
    if provider is None:
        raise ValueError(f"unsupported pay method: {method}")
    # Future: if settings.payment_provider == "wechat_real": return WechatRealProvider()
    return provider


def list_pay_methods() -> list[dict[str, Any]]:
    return [
        {"method": "wallet", "title": "钱包余额", "stub": False},
        {"method": "wechat", "title": "微信支付", "stub": True},
        {"method": "alipay", "title": "支付宝", "stub": True},
        {"method": "apple_pay", "title": "Apple Pay", "stub": True},
    ]

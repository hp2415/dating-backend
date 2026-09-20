from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CreateOrderRequest(BaseModel):
    kind: str = Field(description="activity | companion_booking | membership | wallet_topup")
    subject_id: Optional[UUID] = None
    subject_title: Optional[str] = Field(default=None, max_length=200)
    amount_cents: Optional[int] = Field(default=None, ge=0)
    discount_cents: int = Field(default=0, ge=0)
    meta: dict[str, Any] = Field(default_factory=dict)


class PayOrderRequest(BaseModel):
    method: str = Field(description="wallet | wechat | alipay | apple_pay")


class RefundRequest(BaseModel):
    order_id: UUID
    reason: str = Field(min_length=1, max_length=120)
    detail: str = Field(default="", max_length=500)
    amount_cents: Optional[int] = Field(default=None, ge=1)


class TopUpRequest(BaseModel):
    amount_cents: int = Field(ge=100, description="至少 ¥1")
    method: str = Field(default="wechat")


class SubscribeRequest(BaseModel):
    plan_code: Optional[str] = "monthly"
    plan_id: Optional[UUID] = None
    method: str = Field(default="wallet")


class AdminRefundAction(BaseModel):
    action: str = Field(description="complete | reject")
    admin_note: Optional[str] = Field(default=None, max_length=500)


class StubNotifyRequest(BaseModel):
    provider_txn_id: str
    amount_cents: int = 0
    success: bool = True

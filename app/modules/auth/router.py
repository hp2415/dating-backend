from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.schemas import PasswordLoginRequest, RefreshRequest, SmsLoginRequest, SmsSendRequest
from app.modules.auth.service import AuthService
from app.shared.deps import get_db, get_request_id
from app.shared.response import ok

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/sms/send")
async def sms_send(
    body: SmsSendRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    client_ip = request.client.host if request.client else None
    data = await AuthService(db).send_sms(
        body.phone,
        client_ip=client_ip,
        request_id=get_request_id(request),
    )
    return ok(data, request_id=get_request_id(request))


@router.post("/sms/login")
async def sms_login(
    body: SmsLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    data = await AuthService(db).login(body.phone, body.code, body.device_id, body.platform)
    return ok(data, request_id=get_request_id(request))


@router.post("/password/login")
async def password_login(
    body: PasswordLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    data = await AuthService(db).login_with_password(
        body.phone, body.password, body.device_id, body.platform
    )
    return ok(data, request_id=get_request_id(request))


@router.post("/token/refresh")
async def token_refresh(
    body: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    tokens = await AuthService(db).refresh(body.refresh_token)
    return ok(tokens, request_id=get_request_id(request))


@router.post("/logout")
async def logout(
    body: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await AuthService(db).logout(body.refresh_token)
    return ok({"logged_out": True}, request_id=get_request_id(request))

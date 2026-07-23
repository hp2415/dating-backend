from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.modules.user.schemas import DeleteAccountRequest, PreferenceUpdateRequest, ProfileUpdateRequest
from app.modules.user.service import UserService
from app.shared.deps import get_current_user, get_db, get_request_id
from app.shared.response import ok

router = APIRouter(prefix="/api/v1", tags=["user"])


@router.get("/me")
async def get_me(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await UserService(db).get_me(user)
    return ok(data, request_id=get_request_id(request))


@router.put("/me/profile")
async def update_profile(
    body: ProfileUpdateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await UserService(db).update_profile(user, body.model_dump(exclude_unset=True))
    return ok(data, request_id=get_request_id(request))


@router.put("/me/preferences")
async def update_preferences(
    body: PreferenceUpdateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await UserService(db).update_preference(user, body.model_dump(exclude_unset=True))
    return ok(data, request_id=get_request_id(request))


@router.post("/account/delete")
async def delete_account(
    body: DeleteAccountRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await UserService(db).delete_account(user, body.confirm)
    return ok(data, request_id=get_request_id(request))

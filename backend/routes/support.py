from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from config import SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS, secure_cookie_for_request
from routes.rooms import require_admin, get_current_user_or_401
from services.admin_user_service import log_admin_action
from services.community_service import get_feature_settings
from services.support_access_service import (
    create_support_link,
    consume_support_link,
    end_support_session,
    get_support_session,
    SupportAccessError,
)

router = APIRouter()


class SupportLinkRequest(BaseModel):
    reason: str = Field(default="Assistance technique", max_length=240)
    validity_minutes: int = Field(default=5, ge=1, le=15)


@router.post("/api/admin/users/{user_id}/support-link")
def create_link(user_id: int, data: SupportLinkRequest, request: Request):
    admin = require_admin(request)
    if not get_feature_settings().get("support_access_enabled"):
        raise HTTPException(status_code=403, detail="L’accès assistance est désactivé.")
    try:
        result = create_support_link(admin, user_id, data.reason, data.validity_minutes)
        log_admin_action(admin["id"], "support_link", result["target_username"], data.reason)
        result["absolute_url"] = str(request.base_url).rstrip("/") + result["url"]
        return result
    except SupportAccessError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.get("/support/{token}")
def enter_support(token: str, request: Request):
    admin = require_admin(request)
    try:
        result = consume_support_link(token, admin)
        log_admin_action(admin["id"], "support_enter", result["target_username"], result.get("reason") or "")
    except SupportAccessError as error:
        raise HTTPException(status_code=422, detail=str(error))
    response = RedirectResponse(url="/?support=1", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=result["session_token"],
        httponly=True,
        samesite="lax",
        secure=secure_cookie_for_request(request),
        max_age=SESSION_MAX_AGE_SECONDS,
    )
    return response


@router.get("/api/support/status")
def support_status(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    info = get_support_session(token) if token else None
    return {"active": bool(info), "session": info}


@router.post("/api/support/end")
def end_support(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Aucune session active.")
    info = get_support_session(token)
    if not info:
        raise HTTPException(status_code=409, detail="Aucun mode assistance actif.")
    try:
        result = end_support_session(token)
        log_admin_action(result["admin_id"], "support_exit", info.get("target_username") or "", "Retour au compte admin")
    except SupportAccessError as error:
        raise HTTPException(status_code=422, detail=str(error))
    response = RedirectResponse(url="/admin#users", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=result["session_token"],
        httponly=True,
        samesite="lax",
        secure=secure_cookie_for_request(request),
        max_age=SESSION_MAX_AGE_SECONDS,
    )
    return response

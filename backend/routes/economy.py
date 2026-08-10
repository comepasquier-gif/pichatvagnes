from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Response
from pydantic import BaseModel, Field

from routes.rooms import get_current_user_or_401, require_admin
from services.community_service import get_feature_settings
from services.pycoin_service import (
    get_wallet, claim_daily, transfer, redeem_promo,
    get_economy_settings, update_economy_settings,
    PyCoinError,
)
from services.economy_admin_service import (
    get_dashboard, adjust_user_balance, bulk_adjust,
    create_promo_code, toggle_promo_code, export_transactions_csv,
    EconomyAdminError,
)
from services.admin_user_service import log_admin_action
from services.custom_server_service import (
    list_custom_servers,
    create_custom_server,
    join_custom_server,
    add_member,
    customize_server,
    leave_custom_server,
    delete_custom_server,
    CustomServerError,
)

router = APIRouter()


class TransferRequest(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    amount: int = Field(ge=1, le=100000)


class PromoRedeemRequest(BaseModel):
    code: str = Field(min_length=3, max_length=24)


class CustomServerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=40)
    description: str = Field(default="", max_length=160)
    icon: str = Field(default="💬", max_length=8)


class CustomServerJoin(BaseModel):
    invite_code: str = Field(min_length=3, max_length=20)


class CustomServerMember(BaseModel):
    username: str = Field(min_length=1, max_length=32)


class CustomServerUpdate(CustomServerCreate):
    pass


class AdminBalanceRequest(BaseModel):
    operation: str = Field(pattern="^(credit|debit|set)$")
    amount: int = Field(ge=0, le=1000000)
    reason: str = Field(default="Ajustement administrateur", max_length=240)


class AdminBulkBalanceRequest(BaseModel):
    scope: str = Field(pattern="^(class|all)$")
    operation: str = Field(pattern="^(credit|debit)$")
    amount: int = Field(ge=1, le=100000)
    class_code: str = Field(default="", max_length=16)
    reason: str = Field(default="Distribution administrateur", max_length=240)


class EconomySettingsRequest(BaseModel):
    daily_reward: int = Field(ge=0, le=100000)
    transfer_max: int = Field(ge=1, le=100000)
    transfers_enabled: bool = True
    server_creation_cost: int = Field(ge=0, le=1000000)
    server_customization_cost: int = Field(ge=0, le=1000000)
    code_cost: int = Field(ge=0, le=100000)
    max_owned_servers: int = Field(ge=1, le=20)


class PromoCodeCreateRequest(BaseModel):
    code: str = Field(min_length=3, max_length=24)
    amount: int = Field(ge=1, le=100000)
    max_uses: int = Field(ge=1, le=100000)
    expires_at: Optional[str] = Field(default=None, max_length=40)
    note: str = Field(default="", max_length=200)


class PromoCodeToggleRequest(BaseModel):
    active: bool


def _features_or_403(key: str):
    settings = get_feature_settings()
    if not settings.get(key):
        raise HTTPException(status_code=403, detail="Cette fonction est désactivée par un administrateur.")


@router.get("/api/pycoins/wallet")
def wallet(request: Request):
    _features_or_403("pycoins_enabled")
    user = get_current_user_or_401(request)
    data = get_wallet(user["id"])
    settings = get_economy_settings()
    data.update({
        "server_creation_cost": settings["server_creation_cost"],
        "server_customization_cost": settings["server_customization_cost"],
        "max_owned_servers": settings["max_owned_servers"],
        "code_cost": settings["code_cost"],
    })
    return data


@router.post("/api/pycoins/daily")
def daily(request: Request):
    _features_or_403("pycoins_enabled")
    user = get_current_user_or_401(request)
    try:
        return claim_daily(user["id"])
    except PyCoinError as error:
        raise HTTPException(status_code=409, detail=str(error))


@router.post("/api/pycoins/transfer")
def transfer_route(data: TransferRequest, request: Request):
    _features_or_403("pycoins_enabled")
    user = get_current_user_or_401(request)
    try:
        return transfer(user["id"], data.username, data.amount)
    except PyCoinError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.post("/api/pycoins/redeem")
def redeem_route(data: PromoRedeemRequest, request: Request):
    _features_or_403("pycoins_enabled")
    user = get_current_user_or_401(request)
    try:
        return redeem_promo(user["id"], data.code)
    except PyCoinError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.get("/api/admin/economy")
def admin_economy(request: Request, q: str = "", transaction_limit: int = 100):
    require_admin(request)
    return get_dashboard(q, transaction_limit)


@router.post("/api/admin/economy/users/{user_id}/balance")
def admin_balance(user_id: int, data: AdminBalanceRequest, request: Request):
    admin = require_admin(request)
    try:
        result = adjust_user_balance(user_id, data.operation, data.amount, data.reason, admin["id"])
        log_admin_action(admin["id"], f"pycoins_{data.operation}", result["username"], f"{result['delta']:+d} · {data.reason}")
        return result
    except EconomyAdminError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.post("/api/admin/economy/bulk")
def admin_bulk(data: AdminBulkBalanceRequest, request: Request):
    admin = require_admin(request)
    try:
        result = bulk_adjust(data.scope, data.amount, data.operation, data.reason, admin["id"], data.class_code)
        target = data.class_code.upper() if data.scope == "class" else "TOUS"
        log_admin_action(admin["id"], f"pycoins_bulk_{data.operation}", target, f"{data.amount} × {result['changed']} · {data.reason}")
        return result
    except EconomyAdminError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.patch("/api/admin/economy/settings")
def admin_settings(data: EconomySettingsRequest, request: Request):
    admin = require_admin(request)
    try:
        result = update_economy_settings(data.model_dump())
        log_admin_action(admin["id"], "economy_settings", "PyCoins", str(result))
        return result
    except PyCoinError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.post("/api/admin/economy/promo-codes", status_code=201)
def admin_create_promo(data: PromoCodeCreateRequest, request: Request):
    admin = require_admin(request)
    try:
        result = create_promo_code(data.code, data.amount, data.max_uses, data.expires_at or "", data.note, admin["id"])
        log_admin_action(admin["id"], "promo_create", result["code"], f"{result['amount']} PyCoins · {result['max_uses']} utilisations")
        return result
    except EconomyAdminError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.patch("/api/admin/economy/promo-codes/{promo_id}")
def admin_toggle_promo(promo_id: int, data: PromoCodeToggleRequest, request: Request):
    admin = require_admin(request)
    try:
        result = toggle_promo_code(promo_id, data.active)
        log_admin_action(admin["id"], "promo_toggle", result["code"], "actif" if data.active else "désactivé")
        return result
    except EconomyAdminError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.get("/api/admin/economy/export.csv")
def admin_export_economy(request: Request, limit: int = 5000):
    require_admin(request)
    content = export_transactions_csv(limit)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=pycoins_transactions.csv"},
    )


@router.get("/api/custom-servers")
def custom_servers(request: Request):
    _features_or_403("custom_servers_enabled")
    user = get_current_user_or_401(request)
    return list_custom_servers(user["id"], bool(user.get("is_admin")))


@router.post("/api/custom-servers", status_code=201)
def create_server(data: CustomServerCreate, request: Request):
    _features_or_403("custom_servers_enabled")
    user = get_current_user_or_401(request)
    try:
        return create_custom_server(user["id"], data.name, data.description, data.icon)
    except CustomServerError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.post("/api/custom-servers/join")
def join_server(data: CustomServerJoin, request: Request):
    _features_or_403("custom_servers_enabled")
    user = get_current_user_or_401(request)
    try:
        return join_custom_server(user["id"], data.invite_code)
    except CustomServerError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.post("/api/custom-servers/{server_id}/members")
def add_server_member(server_id: int, data: CustomServerMember, request: Request):
    user = get_current_user_or_401(request)
    try:
        return add_member(server_id, user["id"], data.username, bool(user.get("is_admin")))
    except CustomServerError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.patch("/api/custom-servers/{server_id}")
def edit_server(server_id: int, data: CustomServerUpdate, request: Request):
    user = get_current_user_or_401(request)
    try:
        return customize_server(
            server_id, user["id"], data.name, data.description, data.icon,
            bool(user.get("is_admin")),
        )
    except CustomServerError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.post("/api/custom-servers/{server_id}/leave", status_code=204)
def leave_server(server_id: int, request: Request):
    user = get_current_user_or_401(request)
    try:
        leave_custom_server(server_id, user["id"])
    except CustomServerError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.delete("/api/custom-servers/{server_id}", status_code=204)
def delete_server(server_id: int, request: Request):
    user = get_current_user_or_401(request)
    try:
        delete_custom_server(server_id, user["id"], bool(user.get("is_admin")))
    except CustomServerError as error:
        raise HTTPException(status_code=422, detail=str(error))

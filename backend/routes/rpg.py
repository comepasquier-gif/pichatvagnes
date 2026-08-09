from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from config import SESSION_COOKIE_NAME
from services.auth_service import get_user_from_session
from services.community_service import get_feature_settings
from models.v21 import RPGClassRequest, RPGItemRequest, RPGBossAttackRequest
from services.rpg_service import (
    profile, choose_class, shop, inventory, buy_item, equip_item, use_item,
    quests, claim_quest, daily_reward, active_boss, attack_boss, leaderboard,
)

router = APIRouter()


def current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = get_user_from_session(token) if token else None
    if not user:
        raise HTTPException(status_code=401, detail="Non connecté.")
    if not get_feature_settings().get("rpg_enabled", True):
        raise HTTPException(status_code=403, detail="RPG désactivé.")
    return user


def call(fn, *args):
    try:
        return fn(*args)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/api/rpg/profile")
def rpg_profile(request: Request):
    user = current_user(request)
    return profile(user["id"])


@router.post("/api/rpg/class")
def rpg_class(data: RPGClassRequest, request: Request):
    user = current_user(request)
    return choose_class(user["id"], data.rpg_class)


@router.get("/api/rpg/shop")
def rpg_shop(request: Request):
    current_user(request)
    return shop()


@router.get("/api/rpg/inventory")
def rpg_inventory(request: Request):
    user = current_user(request)
    return inventory(user["id"])


@router.post("/api/rpg/buy")
def rpg_buy(data: RPGItemRequest, request: Request):
    user = current_user(request)
    return call(buy_item, user["id"], data.item_code)


@router.post("/api/rpg/equip")
def rpg_equip(data: RPGItemRequest, request: Request):
    user = current_user(request)
    return call(equip_item, user["id"], data.item_code)


@router.post("/api/rpg/use")
def rpg_use(data: RPGItemRequest, request: Request):
    user = current_user(request)
    return call(use_item, user["id"], data.item_code)


@router.get("/api/rpg/quests")
def rpg_quests(request: Request):
    user = current_user(request)
    return quests(user["id"])


@router.post("/api/rpg/quests/{quest_id}/claim")
def rpg_claim(quest_id: int, request: Request):
    user = current_user(request)
    return call(claim_quest, user["id"], quest_id)


@router.post("/api/rpg/daily")
def rpg_daily(request: Request):
    user = current_user(request)
    return call(daily_reward, user["id"])


@router.get("/api/rpg/boss")
def rpg_boss(request: Request):
    current_user(request)
    return active_boss()


@router.post("/api/rpg/boss/attack")
def rpg_attack(data: RPGBossAttackRequest, request: Request):
    user = current_user(request)
    return call(attack_boss, user["id"], data.style)


@router.get("/api/rpg/leaderboard")
def rpg_leaderboard(request: Request):
    current_user(request)
    return leaderboard()

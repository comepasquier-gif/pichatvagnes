from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from routes.rooms import get_current_user_or_401, require_admin
from services.community_service import get_feature_settings
from services.game_studio_service import (
    CHATGPT_URL,
    GameStudioError,
    build_special_prompt,
    delete_game,
    generate_with_api,
    get_game,
    get_pigame_context,
    submit_pigame_score,
    unlock_pigame_achievement,
    get_settings,
    import_chatgpt_answer,
    import_game_file,
    build_game_template_zip,
    list_games,
    review_game,
    submit_game,
    update_settings,
)

router = APIRouter()


class PromptRequest(BaseModel):
    idea: str = Field(min_length=8, max_length=3000)
    title: str = Field(default="", max_length=80)


class ImportRequest(PromptRequest):
    answer: str = Field(min_length=20, max_length=120000)


class GameScoreRequest(BaseModel):
    score: int = Field(ge=-1000000000, le=1000000000)


class GameAchievementRequest(BaseModel):
    key: str = Field(min_length=1, max_length=48)
    title: str = Field(default="", max_length=80)


class ReviewRequest(BaseModel):
    note: str = Field(default="", max_length=300)


class StudioSettingsRequest(BaseModel):
    enabled: bool = True
    direct_api_enabled: bool = False
    require_admin_approval: bool = True
    max_games_per_user: int = Field(default=8, ge=1, le=30)


def _ensure_enabled() -> None:
    features = get_feature_settings()
    settings = get_settings()
    if not features.get("game_studio_enabled", True) or not settings.get("enabled"):
        raise HTTPException(status_code=403, detail="PiGame Studio est désactivé.")


@router.get("/api/game-studio/status")
def game_studio_status(request: Request):
    user = get_current_user_or_401(request)
    settings = get_settings()
    return {
        "enabled": bool(get_feature_settings().get("game_studio_enabled", True) and settings.get("enabled")),
        "chatgpt_url": CHATGPT_URL,
        "chatgpt_web_mode": True,
        "direct_api_enabled": bool(settings.get("direct_api_enabled")),
        "api_key_configured": bool(settings.get("api_key_configured")),
        "require_admin_approval": bool(settings.get("require_admin_approval")),
        "max_games_per_user": int(settings.get("max_games_per_user") or 8),
        "is_admin": bool(user.get("is_admin")),
    }


@router.post("/api/game-studio/prompt")
def make_prompt(data: PromptRequest, request: Request):
    get_current_user_or_401(request)
    _ensure_enabled()
    try:
        prompt = build_special_prompt(data.idea, data.title)
    except GameStudioError as error:
        raise HTTPException(status_code=422, detail=str(error))
    return {"prompt": prompt, "chatgpt_url": CHATGPT_URL}


@router.post("/api/game-studio/import")
def import_game(data: ImportRequest, request: Request):
    user = get_current_user_or_401(request)
    _ensure_enabled()
    try:
        return import_chatgpt_answer(user["id"], data.answer, data.idea, data.title)
    except GameStudioError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.post("/api/game-studio/import-file")
async def import_game_upload(request: Request, file: UploadFile = File(...)):
    user = get_current_user_or_401(request)
    _ensure_enabled()
    try:
        content = await file.read()
        return import_game_file(user["id"], file.filename or "jeu", content)
    except GameStudioError as error:
        raise HTTPException(status_code=422, detail=str(error))
    finally:
        await file.close()


@router.get("/api/game-studio/template")
def game_template(request: Request):
    get_current_user_or_401(request)
    _ensure_enabled()
    return Response(
        content=build_game_template_zip(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=PiGame_Modele.zip"},
    )


@router.post("/api/game-studio/generate")
async def generate_game(data: PromptRequest, request: Request):
    user = get_current_user_or_401(request)
    _ensure_enabled()
    try:
        return await generate_with_api(user["id"], data.idea, data.title)
    except GameStudioError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.get("/api/game-studio/games")
def games(request: Request):
    user = get_current_user_or_401(request)
    _ensure_enabled()
    return list_games(user["id"], bool(user.get("is_admin")))


@router.get("/api/game-studio/games/{game_id}")
def game_detail(game_id: int, request: Request):
    user = get_current_user_or_401(request)
    _ensure_enabled()
    try:
        return get_game(game_id, user["id"], bool(user.get("is_admin")), count_play=False)
    except GameStudioError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.post("/api/game-studio/games/{game_id}/play")
def play_game(game_id: int, request: Request):
    user = get_current_user_or_401(request)
    _ensure_enabled()
    try:
        return get_game(game_id, user["id"], bool(user.get("is_admin")), count_play=True)
    except GameStudioError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.get("/api/game-studio/games/{game_id}/pigame/context")
def pigame_context(game_id: int, request: Request):
    user = get_current_user_or_401(request)
    _ensure_enabled()
    try:
        return get_pigame_context(game_id, user["id"], bool(user.get("is_admin")))
    except GameStudioError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.post("/api/game-studio/games/{game_id}/pigame/score")
def pigame_score(game_id: int, data: GameScoreRequest, request: Request):
    user = get_current_user_or_401(request)
    _ensure_enabled()
    try:
        return submit_pigame_score(game_id, user["id"], data.score, bool(user.get("is_admin")))
    except GameStudioError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.post("/api/game-studio/games/{game_id}/pigame/achievement")
def pigame_achievement(game_id: int, data: GameAchievementRequest, request: Request):
    user = get_current_user_or_401(request)
    _ensure_enabled()
    try:
        return unlock_pigame_achievement(game_id, user["id"], data.key, data.title, bool(user.get("is_admin")))
    except GameStudioError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.post("/api/game-studio/games/{game_id}/submit")
def submit(game_id: int, request: Request):
    user = get_current_user_or_401(request)
    _ensure_enabled()
    try:
        return submit_game(game_id, user["id"], bool(user.get("is_admin")))
    except GameStudioError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.delete("/api/game-studio/games/{game_id}", status_code=204)
def remove_game(game_id: int, request: Request):
    user = get_current_user_or_401(request)
    try:
        delete_game(game_id, user["id"], bool(user.get("is_admin")))
    except GameStudioError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.get("/api/admin/game-studio/settings")
def admin_settings(request: Request):
    require_admin(request)
    return get_settings()


@router.patch("/api/admin/game-studio/settings")
def admin_settings_update(data: StudioSettingsRequest, request: Request):
    require_admin(request)
    return update_settings(data.enabled, data.direct_api_enabled, data.require_admin_approval, data.max_games_per_user)


@router.post("/api/admin/game-studio/games/{game_id}/approve")
def approve_game(game_id: int, data: ReviewRequest, request: Request):
    admin = require_admin(request)
    try:
        return review_game(game_id, admin["id"], True, data.note)
    except GameStudioError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.post("/api/admin/game-studio/games/{game_id}/reject")
def reject_game(game_id: int, data: ReviewRequest, request: Request):
    admin = require_admin(request)
    try:
        return review_game(game_id, admin["id"], False, data.note)
    except GameStudioError as error:
        raise HTTPException(status_code=422, detail=str(error))

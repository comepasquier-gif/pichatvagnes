from fastapi import APIRouter, Response, Request, HTTPException, status

from config import SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS, REGISTRATION_MODE, secure_cookie_for_request
from models.user import UserRegister, UserLogin, UserPublic
from services.auth_service import (
    submit_registration_request,
    register_user_direct,
    authenticate_user,
    create_session,
    get_user_from_session,
    delete_session,
    UsernameAlreadyTakenError,
    InvalidCredentialsError,
    BannedUserError,
    RegistrationPendingError,
    check_login_allowed, record_login_attempt,
)
from services.class_service import InvalidClassCodeError
from database import get_db_cursor

router = APIRouter()

def _registration_mode() -> str:
    try:
        with get_db_cursor() as c:
            row=c.execute("SELECT registration_mode FROM instance_settings WHERE id=1").fetchone()
        mode=str(row["registration_mode"] or "") if row else ""
        return mode if mode in {"open","approval","closed"} else REGISTRATION_MODE
    except Exception:
        return REGISTRATION_MODE

@router.get("/api/registration-mode")
def registration_mode():
    return {"mode": _registration_mode()}


@router.post("/api/register")
def register(user_data: UserRegister, response: Response, request: Request):
    """Inscription publique v1.0.0, avec modes open/approval/closed."""
    mode = _registration_mode()
    if mode == "closed":
        raise HTTPException(status_code=403, detail="Les inscriptions sont fermées pour le moment.")

    try:
        if mode == "approval":
            request_id = submit_registration_request(
                user_data.username, user_data.password, user_data.class_code
            )
            return {
                "mode": "approval",
                "message": "Demande envoyée. Un administrateur doit maintenant l'accepter.",
                "request_id": request_id,
            }

        user = register_user_direct(
            user_data.username, user_data.password, user_data.class_code
        )
        token = create_session(
            user["id"],
            request.headers.get("user-agent", ""),
            request.client.host if request.client else "",
        )
        response.set_cookie(
            key=SESSION_COOKIE_NAME, value=token, httponly=True, samesite="lax",
            secure=secure_cookie_for_request(request), max_age=SESSION_MAX_AGE_SECONDS,
        )
        return {"mode": "open", "message": "Compte créé. Bienvenue sur PiChat !", "user": user}
    except UsernameAlreadyTakenError:
        raise HTTPException(status_code=409, detail="Ce pseudo est déjà utilisé.")
    except RegistrationPendingError:
        raise HTTPException(status_code=409, detail="Une demande est déjà en attente pour ce pseudo.")
    except InvalidClassCodeError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.post("/api/login", response_model=UserPublic)
def login(credentials: UserLogin, response: Response, request: Request):
    ip = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip() or (request.client.host if request.client else "")
    try:
        check_login_allowed(credentials.username, ip)
        user = authenticate_user(credentials.username, credentials.password)
    except BannedUserError as error:
        message = "Ce compte est banni."
        if str(error):
            message += f" Motif : {error}"
        raise HTTPException(status_code=403, detail=message)
    except InvalidCredentialsError as error:
        record_login_attempt(credentials.username, ip, False)
        detail = str(error) if "Trop de tentatives" in str(error) else "Pseudo ou mot de passe incorrect."
        raise HTTPException(status_code=429 if "Trop de tentatives" in detail else 401, detail=detail)

    record_login_attempt(credentials.username, ip, True)
    token = create_session(
        user["id"],
        request.headers.get("user-agent", ""),
        request.client.host if request.client else "",
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=secure_cookie_for_request(request),
        max_age=SESSION_MAX_AGE_SECONDS,
    )
    return UserPublic(**user)


@router.post("/api/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        delete_session(token)
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return {"message": "Déconnexion réussie."}


@router.get("/api/me", response_model=UserPublic)
def get_current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Non connecté.")
    user = get_user_from_session(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Session invalide, expirée ou compte bloqué.")
    return UserPublic(**user)

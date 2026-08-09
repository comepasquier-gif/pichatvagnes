from typing import List
import csv
import secrets
import string
import sqlite3
import io
import json
from fastapi import APIRouter, Request, HTTPException, Response

from models.admin_user import (AdminUserPublic, BanUserRequest, UserClassUpdate,
    RegistrationRequestPublic, RegistrationDecision, ModeratorUpdate, AdminConsoleCommand, UserRoleUpdate, UserBadgeUpdate, ProfanitySettingsUpdate, ModeratorPermissionsUpdate, ModeratorPackApply)
from routes.rooms import require_admin, get_current_user_or_401
from permissions import (
    require_role, require_moderator_permission, MODERATOR_PERMISSION_DEFINITIONS,
    moderator_pack_catalog, normalize_moderator_pack,
)
from services.admin_user_service import (ProtectedUserError, UserNotFoundError,
    RegistrationRequestNotFoundError, RegistrationRequestStateError, UsernameConflictError,
    ban_user, unban_user, update_user_class, set_moderator, set_user_role, list_users_for_admin,
    list_users_for_moderator, list_registration_requests, approve_registration_request,
    reject_registration_request, kick_user, reset_user_password, delete_user_account, update_user_badge,
    get_profanity_settings, set_profanity_settings, log_admin_action, list_audit_logs, update_moderator_permissions, apply_moderator_pack)
from services.class_service import InvalidClassCodeError, normalize_class_code, ensure_class_room
from services.message_service import get_message_for_moderation, delete_message
from connection_manager import manager
from database import get_db_cursor, IntegrityError
from services.moderation_service import mute_user, unmute_user, temp_ban_user
from services.automod_service import get_automod_settings, list_automod_incidents, ensure_automod_bot
from services.message_service import save_message
from config import APP_VERSION, PROJECT_ROOT, UPLOADS_DIR
from security import hash_password
from services.economy_admin_service import adjust_user_balance, bulk_adjust, get_dashboard, EconomyAdminError
from services.gaming_profile_service import list_badge_catalog, award_badge, revoke_badge, get_user_badges
from services.arcade_service import admin_overview as arcade_admin_overview, get_arcade_settings, update_arcade_settings
from services.test_lab_service import create_batch as create_test_batch, delete_all_active_batches as delete_all_test_batches, delete_batch as delete_test_batch, list_batches as list_test_batches, TestLabError

router = APIRouter()


def require_moderator_or_admin(request: Request):
    user = get_current_user_or_401(request)
    require_role(user, "moderator")
    return user


@router.get("/api/admin/users", response_model=List[AdminUserPublic])
def get_admin_users(request: Request):
    require_admin(request); return list_users_for_admin()


@router.get("/api/moderation/users", response_model=List[AdminUserPublic])
def get_moderation_users(request: Request):
    user=require_moderator_or_admin(request)
    if user.get("is_admin"): return list_users_for_admin()
    return list_users_for_moderator(user.get("moderator_class_code"))


@router.post("/api/admin/users/{user_id}/ban", response_model=AdminUserPublic)
async def ban_admin_user(user_id: int, ban_data: BanUserRequest, request: Request):
    actor=require_moderator_or_admin(request)
    if not actor.get("is_admin"): require_moderator_permission(actor,"users_ban")
    allowed=None if actor.get("is_admin") else actor.get("moderator_class_code")
    try:
        result=ban_user(user_id, actor["id"], ban_data.reason, allowed)
        await manager.disconnect_user(user_id); log_admin_action(actor["id"],"ban",result["username"],ban_data.reason); return result
    except UserNotFoundError: raise HTTPException(status_code=404, detail="Compte introuvable.")
    except ProtectedUserError as e: raise HTTPException(status_code=409, detail=str(e))


@router.post("/api/admin/users/{user_id}/unban", response_model=AdminUserPublic)
def unban_admin_user(user_id: int, request: Request):
    actor=require_moderator_or_admin(request)
    if not actor.get("is_admin"): require_moderator_permission(actor,"users_unban")
    allowed=None if actor.get("is_admin") else actor.get("moderator_class_code")
    try:
        result=unban_user(user_id, allowed); log_admin_action(actor["id"],"unban",result["username"]); return result
    except UserNotFoundError: raise HTTPException(status_code=404, detail="Compte introuvable.")
    except ProtectedUserError as e: raise HTTPException(status_code=409, detail=str(e))


@router.patch("/api/admin/users/{user_id}/class", response_model=AdminUserPublic)
async def change_user_class(user_id: int, data: UserClassUpdate, request: Request):
    admin=require_admin(request)
    if admin["id"]==user_id: raise HTTPException(status_code=409, detail="Tu ne peux pas modifier ta propre classe ici.")
    try:
        result=update_user_class(user_id, data.class_code); await manager.disconnect_user(user_id); log_admin_action(admin["id"],"class",result["username"],result.get("class_code") or ""); return result
    except UserNotFoundError: raise HTTPException(status_code=404, detail="Compte introuvable.")
    except (ProtectedUserError, InvalidClassCodeError) as e: raise HTTPException(status_code=422, detail=str(e))


@router.patch("/api/admin/users/{user_id}/moderator", response_model=AdminUserPublic)
async def change_moderator(user_id: int, data: ModeratorUpdate, request: Request):
    admin=require_admin(request)
    if admin["id"]==user_id: raise HTTPException(status_code=409, detail="Ton compte est déjà administrateur.")
    try:
        result=set_moderator(user_id, data.enabled, data.class_code, data.permissions, data.moderator_pack); await manager.disconnect_user(user_id); return result
    except UserNotFoundError: raise HTTPException(status_code=404, detail="Compte introuvable.")
    except (ProtectedUserError, InvalidClassCodeError) as e: raise HTTPException(status_code=422, detail=str(e))




@router.patch("/api/admin/users/{user_id}/role", response_model=AdminUserPublic)
async def change_user_role(user_id:int,data:UserRoleUpdate,request:Request):
    admin=require_admin(request)
    try:
        result=set_user_role(user_id,data.role,data.class_code,admin["id"],data.permissions,data.moderator_pack); await manager.disconnect_user(user_id); log_admin_action(admin["id"],"role",result["username"],result.get("role_label") or data.role); return result
    except UserNotFoundError: raise HTTPException(status_code=404,detail="Compte introuvable.")
    except (ProtectedUserError,InvalidClassCodeError) as e: raise HTTPException(status_code=422,detail=str(e))

@router.get("/api/admin/moderator-permissions")
def moderator_permission_catalog(request: Request):
    require_admin(request)
    return {
        "permissions": [{"key": key, "label": label} for key, label in MODERATOR_PERMISSION_DEFINITIONS.items()],
        "packs": moderator_pack_catalog(),
    }


@router.patch("/api/admin/users/{user_id}/moderator-pack", response_model=AdminUserPublic)
async def change_moderator_pack(user_id: int, data: ModeratorPackApply, request: Request):
    admin=require_admin(request)
    try:
        result=apply_moderator_pack(user_id,data.pack,data.class_code)
        await manager.disconnect_user(user_id)
        log_admin_action(admin["id"],"moderator_pack",result["username"],f"{result.get('moderator_pack')}:{result.get('moderator_class_code') or '-'}")
        return result
    except UserNotFoundError:
        raise HTTPException(status_code=404,detail="Compte introuvable.")
    except (ProtectedUserError,InvalidClassCodeError) as exc:
        raise HTTPException(status_code=422,detail=str(exc))


@router.patch("/api/admin/users/{user_id}/moderator-permissions", response_model=AdminUserPublic)
async def change_moderator_permissions(user_id: int, data: ModeratorPermissionsUpdate, request: Request):
    admin=require_admin(request)
    try:
        result=update_moderator_permissions(user_id,data.permissions)
        await manager.disconnect_user(user_id)
        log_admin_action(admin["id"],"moderator_permissions",result["username"],",".join(result.get("moderator_permissions") or []))
        return result
    except UserNotFoundError: raise HTTPException(status_code=404,detail="Compte introuvable.")
    except ProtectedUserError as e: raise HTTPException(status_code=422,detail=str(e))


@router.get("/api/admin/registration-requests", response_model=List[RegistrationRequestPublic])
def get_registration_requests(request: Request, status_filter: str="pending"):
    require_admin(request); return list_registration_requests(status_filter)


@router.post("/api/admin/registration-requests/{request_id}/approve", response_model=AdminUserPublic)
def approve_request(request_id: int, request: Request):
    admin=require_admin(request)
    try:
        result=approve_registration_request(request_id, admin["id"]); log_admin_action(admin["id"],"approve_request",result["username"],result.get("class_code") or ""); return result
    except RegistrationRequestNotFoundError: raise HTTPException(status_code=404, detail="Demande introuvable.")
    except RegistrationRequestStateError: raise HTTPException(status_code=409, detail="Cette demande a déjà été traitée.")
    except UsernameConflictError: raise HTTPException(status_code=409, detail="Ce pseudo existe déjà.")


@router.post("/api/admin/registration-requests/{request_id}/reject", status_code=204)
def reject_request(request_id: int, decision: RegistrationDecision, request: Request):
    admin=require_admin(request)
    try: reject_registration_request(request_id, admin["id"], decision.note); log_admin_action(admin["id"],"reject_request",str(request_id),decision.note)
    except RegistrationRequestNotFoundError: raise HTTPException(status_code=404, detail="Demande introuvable.")
    except RegistrationRequestStateError: raise HTTPException(status_code=409, detail="Cette demande a déjà été traitée.")


@router.delete("/api/moderation/messages/{message_id}", status_code=204)
def moderation_delete_message(message_id: int, request: Request):
    actor=require_moderator_or_admin(request)
    if not actor.get("is_admin"): require_moderator_permission(actor,"messages_delete")
    msg=get_message_for_moderation(message_id)
    if not msg: raise HTTPException(status_code=404, detail="Message introuvable.")
    if not actor.get("is_admin"):
        if msg.get("class_code") != actor.get("moderator_class_code"):
            raise HTTPException(status_code=403, detail="Ce message appartient à une autre classe.")
        if msg.get("is_admin") or msg.get("is_bot"):
            raise HTTPException(status_code=403, detail="Ce message est protégé.")
    delete_message(message_id)


@router.post("/api/admin/users/{user_id}/kick")
async def kick_admin_user(user_id:int, request:Request):
    admin=require_moderator_or_admin(request)
    if not admin.get("is_admin"): require_moderator_permission(admin,"users_kick")
    try:
        if not admin.get("is_admin"):
            allowed_users={u["id"] for u in list_users_for_moderator(admin.get("moderator_class_code")) if not u.get("is_admin") and not u.get("is_moderator")}
            if user_id not in allowed_users: raise ProtectedUserError("Tu ne peux expulser que les joueurs de ta classe.")
        result=kick_user(user_id,admin["id"]); await manager.disconnect_user(user_id); log_admin_action(admin["id"],"kick",result["username"]); return result
    except UserNotFoundError: raise HTTPException(status_code=404,detail="Compte introuvable.")
    except ProtectedUserError as e: raise HTTPException(status_code=409,detail=str(e))

@router.post("/api/admin/users/{user_id}/reset-password")
async def reset_password_admin(user_id:int, request:Request):
    admin=require_admin(request)
    try:
        result=reset_user_password(user_id,admin["id"]); await manager.disconnect_user(user_id); log_admin_action(admin["id"],"reset_password",result["username"]); return result
    except UserNotFoundError: raise HTTPException(status_code=404,detail="Compte introuvable.")
    except ProtectedUserError as e: raise HTTPException(status_code=409,detail=str(e))

@router.delete("/api/admin/users/{user_id}")
async def delete_admin_user(user_id:int, request:Request):
    admin=require_admin(request)
    try:
        username=delete_user_account(user_id,admin["id"]); await manager.disconnect_user(user_id); log_admin_action(admin["id"],"delete_user",username); return {"deleted":True,"username":username}
    except UserNotFoundError: raise HTTPException(status_code=404,detail="Compte introuvable.")
    except ProtectedUserError as e: raise HTTPException(status_code=409,detail=str(e))

@router.patch("/api/admin/users/{user_id}/badge", response_model=AdminUserPublic)
def change_user_badge(user_id:int,data:UserBadgeUpdate,request:Request):
    admin=require_admin(request)
    try:
        result=update_user_badge(user_id,data.title,data.color); log_admin_action(admin["id"],"badge",result["username"],result.get("role_label") or ""); return result
    except UserNotFoundError: raise HTTPException(status_code=404,detail="Compte introuvable.")
    except ProtectedUserError as e: raise HTTPException(status_code=422,detail=str(e))

@router.get("/api/admin/export/users.csv")
def export_users_csv(request:Request):
    require_admin(request); rows=list_users_for_admin(); output=io.StringIO(newline='')
    writer=csv.writer(output); writer.writerow(["id","username","class","role","badge","banned","created_at"])
    for u in rows:
        if u.get("is_bot"): continue
        writer.writerow([u["id"],u["username"],u.get("class_code") or "",u.get("role") or "player",u.get("grade_title") or "",1 if u.get("is_banned") else 0,u.get("created_at") or ""])
    return Response(output.getvalue(),media_type="text/csv; charset=utf-8",headers={"Content-Disposition":"attachment; filename=pichat_comptes.csv"})

@router.get("/api/admin/export/users.json")
def export_users_json(request:Request):
    require_admin(request); rows=[]
    for u in list_users_for_admin():
        if u.get("is_bot"): continue
        rows.append({k:u.get(k) for k in ("id","username","class_code","role","role_label","grade_title","grade_color","is_banned","banned_reason","created_at")})
    return Response(json.dumps(rows,ensure_ascii=False,indent=2),media_type="application/json; charset=utf-8",headers={"Content-Disposition":"attachment; filename=pichat_comptes.json"})

@router.get("/api/admin/audit")
def get_audit(request:Request,limit:int=100):
    require_admin(request); return list_audit_logs(limit)

@router.get("/api/moderation/filter")
def public_filter_settings(request:Request):
    get_current_user_or_401(request); s=get_profanity_settings(); return {"enabled":s["enabled"],"words":s["words"]}

@router.get("/api/admin/moderation-settings")
def admin_filter_settings(request:Request):
    require_admin(request); return get_profanity_settings()

@router.patch("/api/admin/moderation-settings")
def admin_update_filter_settings(data:ProfanitySettingsUpdate,request:Request):
    admin=require_admin(request); result=set_profanity_settings(data.enabled,data.words); log_admin_action(admin["id"],"profanity_settings","filter",f"enabled={data.enabled}; words={len(result['words'])}"); return result

@router.post("/api/admin/console")
async def admin_console(data: AdminConsoleCommand, request: Request):
    admin = require_admin(request)
    raw = data.command.strip()
    parts = raw.split()
    cmd = parts[0].lower() if parts else ""

    def output(text):
        return {"output": str(text)}

    def find_user(token):
        token = (token or "").strip()
        with get_db_cursor() as c:
            if token.isdigit():
                row = c.execute("SELECT id,username FROM users WHERE id=?", (int(token),)).fetchone()
            else:
                row = c.execute("SELECT id,username FROM users WHERE lower(username)=lower(?)", (token,)).fetchone()
        return dict(row) if row else None

    if cmd in {"help", "?"}:
        return output("""COMMANDES PICHAT 2.1
Informations : status | version | whoami | users [classe/grade] | user <pseudo> | rooms | pending | moderators | ai | automod | incidents [open|all] | files
Demandes : approve <id> | reject <id> [motif]
Création : create-user <pseudo> <classe> [motdepasse]
           create-user user <pseudo> class <classe> [password <motdepasse>]
Comptes : kick <pseudo> | mute <pseudo> <minutes> [motif] | unmute <pseudo> | tempban <pseudo> <minutes> [motif]
          role <pseudo> <player|moderator|admin> [classe] | class <pseudo> <classe> | reset-password <pseudo>
Packs modo : mod-packs | mod-pack <pseudo> <petit|normal|super> [classe]
Badges : badges | badge-give <pseudo> <code> [motif] | badge-remove <pseudo> <code>
Messages : broadcast <room_id> <message>
Économie : economy | coins <pseudo> <+100|-50|=500> [motif] | coins class <5C> <+25|-10> [motif] | coins all <+10|-5> [motif]
Arcade : arcade | arcade <on|off> | arcade-rewards <on|off>
PiGame Studio : gestion dans Administration → PiGame Studio
Labo test : test-pack [nombre] [préfixe] [motdepasse] | test-batches | test-clean <id|all>
Maintenance : backup | clear
V2.1.5 : correctif envoi, Pack Labo & Diagnostic, comptes de test""")
    if cmd in {"test-pack", "test-create"}:
        try:
            count = int(parts[1]) if len(parts) > 1 else 20
        except ValueError:
            return output("Le nombre de comptes doit être un entier entre 1 et 100.")
        prefix = parts[2] if len(parts) > 2 else "test"
        password = parts[3] if len(parts) > 3 else "PiChatTest2026!"
        try:
            result = create_test_batch(admin["id"], count, prefix, password, True, True)
        except TestLabError as exc:
            return output("ERREUR : " + str(exc))
        lines = [
            f"Lot créé : {result['batch_code']}",
            f"Mot de passe commun : {result['password']}",
            "",
        ]
        lines.extend([f"{x['username']} | {x['class_code']} | {x['role']}" for x in result["credentials"]])
        lines.append("\nNettoyage : test-clean %s" % result["batch_id"])
        return output("\n".join(lines))
    if cmd == "test-batches":
        batches = list_test_batches()
        return output("\n".join([f"#{x['id']} {x['batch_code']} | {x['active_accounts']} compte(s) | {x['status']}" for x in batches]) or "Aucun lot de test.")
    if cmd == "test-clean":
        if len(parts) < 2:
            return output("Syntaxe : test-clean <id|all>")
        try:
            result = delete_all_test_batches() if parts[1].lower() == "all" else delete_test_batch(int(parts[1]))
        except (ValueError, TestLabError) as exc:
            return output("ERREUR : " + str(exc))
        return output(json.dumps(result, ensure_ascii=False, indent=2))
    if cmd == "version":
        return output("PiChat v" + APP_VERSION)
    if cmd == "whoami":
        return output(f"#{admin['id']} {admin['username']} [ADMIN]")
    if cmd == "status":
        with get_db_cursor() as c:
            counts = {}
            for table in ("users", "rooms", "messages", "registration_requests", "bots", "sessions", "automod_incidents"):
                try:
                    counts[table] = c.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                except Exception:
                    counts[table] = 0
        return output(" | ".join([f"{k}: {v}" for k, v in counts.items()]))
    if cmd == "users":
        xs = list_users_for_admin()
        if len(parts) > 1:
            f = parts[1].lower()
            xs = [u for u in xs if f in (u.get("class_code") or "").lower() or f == (u.get("role") or "").lower()]
        return output("\n".join([f"#{u['id']} {u['username']} [{u.get('class_code') or '-'}] {u.get('role','player')}" for u in xs]) or "Aucun utilisateur.")
    if cmd == "user" and len(parts) >= 2:
        u = find_user(parts[1])
        if not u:
            return output("Utilisateur introuvable.")
        full = next((x for x in list_users_for_admin() if x["id"] == u["id"]), None)
        return output(json.dumps(full, ensure_ascii=False, indent=2))
    if cmd == "pending":
        xs = list_registration_requests("pending")
        return output("\n".join([f"#{x['id']} {x['username']} [{x['class_code']}]" for x in xs]) or "Aucune demande.")
    if cmd in {"create-user", "add-user"}:
        def temporary_password(length=14):
            alphabet = string.ascii_letters + string.digits + "-_.!"
            return "".join(secrets.choice(alphabet) for _ in range(length))

        username = class_code = password = None
        args = parts[1:]
        if args and args[0].lower() == "user":
            values = {}
            index = 0
            while index < len(args):
                key = args[index].lower()
                if key not in {"user", "class", "password"} or index + 1 >= len(args):
                    return output("Syntaxe : create-user user <pseudo> class <classe> [password <motdepasse>]")
                values[key] = args[index + 1]
                index += 2
            username, class_code, password = values.get("user"), values.get("class"), values.get("password")
        else:
            if len(args) < 2:
                return output("Syntaxe : create-user <pseudo> <classe> [motdepasse]")
            username, class_code = args[0], args[1]
            password = args[2] if len(args) > 2 else None

        username = (username or "").strip()
        if not 3 <= len(username) <= 32:
            return output("Le pseudo doit contenir 3 à 32 caractères.")
        try:
            code = normalize_class_code(class_code or "")
        except InvalidClassCodeError as error:
            return output(str(error))
        generated = not password
        password = password or temporary_password()
        if len(password) < 8:
            return output("Le mot de passe doit contenir au moins 8 caractères.")
        try:
            with get_db_cursor() as c:
                c.execute(
                    "INSERT INTO users (username,password_hash,class_code,is_admin,is_bot,is_banned) VALUES (?,?,?,0,0,0)",
                    (username, hash_password(password), code),
                )
                c.execute("DELETE FROM registration_requests WHERE lower(username)=lower(?)", (username,))
            ensure_class_room(code)
            log_admin_action(admin["id"], "create_user", username, code)
        except IntegrityError:
            return output(f"Le pseudo '{username}' existe déjà.")
        result = f"Compte créé : {username} [{code}]"
        if generated:
            result += f"\nMot de passe temporaire : {password}\nCopie-le maintenant."
        return output(result)
    if cmd == "approve" and len(parts) >= 2 and parts[1].isdigit():
        result = approve_registration_request(int(parts[1]), admin["id"])
        return output(f"Compte accepté : {result['username']} [{result.get('class_code') or '-'}]")
    if cmd == "reject" and len(parts) >= 2 and parts[1].isdigit():
        note = " ".join(parts[2:])
        reject_registration_request(int(parts[1]), admin["id"], note)
        return output("Demande refusée.")
    if cmd == "rooms":
        with get_db_cursor() as c:
            rows = c.execute("SELECT id,name,class_code FROM rooms ORDER BY id").fetchall()
        return output("\n".join([f"#{r['id']} {r['name']} [{r['class_code'] or 'commun'}]" for r in rows]) or "Aucun serveur.")
    if cmd == "moderators":
        xs = [u for u in list_users_for_admin() if u.get("is_moderator")]
        return output("\n".join([f"{u['username']} -> {u.get('moderator_class_code') or '-'} | pack={u.get('moderator_pack') or 'custom'} | {len(u.get('moderator_permissions') or [])} permissions" for u in xs]) or "Aucun modérateur.")
    if cmd in {"mod-packs", "modo-packs", "packs-modo"}:
        lines=[]
        for pack in moderator_pack_catalog():
            lines.append(f"{pack['key']:<8} {pack['label']} — {pack['permission_count']} permissions — {pack['description']}")
        return output("\n".join(lines))
    if cmd in {"mod-pack", "modo-pack", "pack-modo"}:
        if len(parts) < 3:
            return output("Syntaxe : mod-pack <pseudo> <petit|normal|super> [classe]")
        target=find_user(parts[1])
        if not target:
            return output("Utilisateur introuvable.")
        pack=normalize_moderator_pack(parts[2])
        if not pack:
            return output("Pack inconnu. Utilise mod-packs.")
        class_code=parts[3].upper() if len(parts)>3 else None
        try:
            result=apply_moderator_pack(target["id"],pack,class_code)
            await manager.disconnect_user(target["id"])
            log_admin_action(admin["id"],"moderator_pack",result["username"],f"{pack}:{result.get('moderator_class_code') or '-'}")
            return output(f"{result['username']} -> {result.get('moderator_pack')} [{result.get('moderator_class_code') or '-'}] avec {len(result.get('moderator_permissions') or [])} permissions.")
        except (ProtectedUserError,InvalidClassCodeError) as exc:
            return output("ERREUR : "+str(exc))
    if cmd == "badges":
        xs = list_badge_catalog(include_inactive=True)
        return output("\n".join([f"#{b['id']} {b['icon']} {b['code']} — {b['name']} — {b['awarded_count']} attribution(s){' [OFF]' if not b['is_active'] else ''}" for b in xs]) or "Aucun badge.")
    if cmd in {"badge-give", "give-badge"}:
        if len(parts) < 3:
            return output("Syntaxe : badge-give <pseudo> <code> [motif]")
        target = find_user(parts[1])
        if not target:
            return output("Utilisateur introuvable.")
        code = parts[2].strip().lower()
        with get_db_cursor() as c:
            badge = c.execute("SELECT id,name FROM badge_definitions WHERE lower(code)=lower(?) AND is_active=1", (code,)).fetchone()
        if not badge:
            return output("Badge introuvable. Utilise badges.")
        try:
            award_badge(target["id"], badge["id"], admin["id"], " ".join(parts[3:]), True)
            log_admin_action(admin["id"], "badge_award", target["username"], code)
            return output(f"Badge {badge['name']} attribué à {target['username']}.")
        except ValueError as exc:
            return output("ERREUR : " + str(exc))
    if cmd in {"badge-remove", "remove-badge"}:
        if len(parts) < 3:
            return output("Syntaxe : badge-remove <pseudo> <code>")
        target = find_user(parts[1])
        if not target:
            return output("Utilisateur introuvable.")
        code = parts[2].strip().lower()
        with get_db_cursor() as c:
            badge = c.execute("SELECT id,name FROM badge_definitions WHERE lower(code)=lower(?)", (code,)).fetchone()
        if not badge:
            return output("Badge introuvable.")
        try:
            revoke_badge(target["id"], badge["id"])
            log_admin_action(admin["id"], "badge_revoke", target["username"], code)
            return output(f"Badge {badge['name']} retiré à {target['username']}.")
        except ValueError as exc:
            return output("ERREUR : " + str(exc))
    if cmd == "ai":
        from services.ai_service import get_ai_settings
        a = get_ai_settings()
        return output(f"PiAI: {'ON' if a['enabled'] else 'OFF'} | {a['provider']} | {a['model']} | clé: {'OK' if a['api_key_configured'] else 'absente'}")
    if cmd == "automod":
        a = get_automod_settings()
        return output("AutoModo: " + ("ON" if a["enabled"] else "OFF") + f" | gros mots={a['profanity_mode']} | liens={a['link_mode']} | mute={a['mute_points']} pts | ban temp={a['temp_ban_points']} pts")
    if cmd == "incidents":
        state = parts[1].lower() if len(parts) > 1 else "open"
        xs = list_automod_incidents(limit=40, status=state)
        return output("\n".join([f"#{x['id']} {x['username']} [{x.get('room_name') or '-'}] {x['rule']} +{x['points']} {x['status']}" for x in xs]) or "Aucun incident.")
    if cmd == "files":
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        files = sorted((p for p in UPLOADS_DIR.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)[:100]
        return output("\n".join([f"{p.name} — {p.stat().st_size} octets" for p in files]) or "Aucun fichier transféré.")
    if cmd == "arcade":
        if len(parts) > 1 and parts[1].lower() in {"on", "off"}:
            settings = get_arcade_settings()
            settings["enabled"] = parts[1].lower() == "on"
            updated = update_arcade_settings(settings)
            log_admin_action(admin["id"], "arcade_toggle", "arcade", parts[1].lower())
            return output("Arcade : " + ("ON" if updated["enabled"] else "OFF"))
        overview = arcade_admin_overview()
        st = overview["totals"]
        cfg = overview["settings"]
        return output(f"Arcade: {'ON' if cfg['enabled'] else 'OFF'} | récompenses={'ON' if cfg['rewards_enabled'] else 'OFF'} | {st['plays']} parties | {st['players']} joueurs | {st['coins']} PyCoins distribués")
    if cmd == "arcade-rewards":
        if len(parts) < 2 or parts[1].lower() not in {"on", "off"}:
            return output("Syntaxe : arcade-rewards <on|off>")
        settings = get_arcade_settings()
        settings["rewards_enabled"] = parts[1].lower() == "on"
        updated = update_arcade_settings(settings)
        log_admin_action(admin["id"], "arcade_rewards", "arcade", parts[1].lower())
        return output("Récompenses Arcade : " + ("ON" if updated["rewards_enabled"] else "OFF"))
    if cmd == "economy":
        d = get_dashboard("", 10)
        st = d["stats"]
        return output(f"PyCoins: {st['total_coins']} en circulation | moyenne {st['average_coins']} | +{st['credited_24h']} / -{st['spent_24h']} sur 24 h | {st['operations_24h']} opérations")
    if cmd == "coins":
        if len(parts) < 3:
            return output("Syntaxe : coins <pseudo> <+100|-50|=500> [motif] | coins class <5C> <+25|-10> [motif] | coins all <+10|-5> [motif]")
        try:
            if parts[1].lower() in {"class", "all"}:
                scope = parts[1].lower()
                if scope == "class":
                    if len(parts) < 4:
                        return output("Syntaxe : coins class <classe> <+25|-10> [motif]")
                    class_code, token_amount, reason_start = parts[2].upper(), parts[3], 4
                else:
                    class_code, token_amount, reason_start = "", parts[2], 3
                if not token_amount or token_amount[0] not in "+-" or not token_amount[1:].isdigit():
                    return output("Le montant groupé doit commencer par + ou -, par exemple +25.")
                operation = "credit" if token_amount[0] == "+" else "debit"
                result = bulk_adjust(scope, int(token_amount[1:]), operation, " ".join(parts[reason_start:]) or "Commande console", admin["id"], class_code)
                return output(f"{result['changed']} compte(s) modifié(s), {result['skipped']} ignoré(s), total {result['total_delta']:+d} PyCoins.")
            target = find_user(parts[1])
            if not target:
                return output("Utilisateur introuvable.")
            token_amount = parts[2]
            if not token_amount or token_amount[0] not in "+-=" or not token_amount[1:].isdigit():
                return output("Montant invalide : utilise +100, -50 ou =500.")
            operation = {"+":"credit", "-":"debit", "=":"set"}[token_amount[0]]
            result = adjust_user_balance(target["id"], operation, int(token_amount[1:]), " ".join(parts[3:]) or "Commande console", admin["id"])
            return output(f"{result['username']} : {result['delta']:+d} PyCoins, nouveau solde {result['balance']}.")
        except EconomyAdminError as error:
            return output("ERREUR : " + str(error))
    if cmd in {"kick", "mute", "unmute", "tempban", "role", "class", "reset-password"}:
        if len(parts) < 2:
            return output("Pseudo manquant.")
        target = find_user(parts[1])
        if not target:
            return output("Utilisateur introuvable.")
        if cmd == "kick":
            result = kick_user(target["id"], admin["id"])
            await manager.disconnect_user(target["id"])
            return output(result["username"] + " expulsé.")
        if cmd == "mute":
            if len(parts) < 3 or not parts[2].isdigit():
                return output("Syntaxe : mute <pseudo> <minutes> [motif]")
            result = mute_user(admin, target["id"], int(parts[2]), " ".join(parts[3:]))
            return output(f"{target['username']} muet jusqu'à {result.get('muted_until')}")
        if cmd == "unmute":
            unmute_user(admin, target["id"])
            return output(target["username"] + " n'est plus muet.")
        if cmd == "tempban":
            if len(parts) < 3 or not parts[2].isdigit():
                return output("Syntaxe : tempban <pseudo> <minutes> [motif]")
            result = temp_ban_user(admin, target["id"], int(parts[2]), " ".join(parts[3:]))
            await manager.disconnect_user(target["id"])
            return output(f"{target['username']} banni temporairement jusqu'à {result.get('ban_until')}")
        if cmd == "role":
            if len(parts) < 3:
                return output("Syntaxe : role <pseudo> <player|moderator|admin> [classe]")
            result = set_user_role(target["id"], parts[2].lower(), parts[3].upper() if len(parts) > 3 else None, admin["id"])
            await manager.disconnect_user(target["id"])
            return output(f"{result['username']} -> {result.get('role_label')}")
        if cmd == "class":
            if len(parts) < 3:
                return output("Syntaxe : class <pseudo> <classe>")
            result = update_user_class(target["id"], parts[2].upper())
            await manager.disconnect_user(target["id"])
            return output(f"{result['username']} -> classe {result.get('class_code')}")
        if cmd == "reset-password":
            result = reset_user_password(target["id"], admin["id"])
            await manager.disconnect_user(target["id"])
            return output(f"Nouveau mot de passe temporaire de {result['username']} : {result['temporary_password']}\nCopie-le maintenant.")
    if cmd == "broadcast" and len(parts) >= 3 and parts[1].isdigit():
        room_id = int(parts[1])
        text = raw.split(None, 2)[2][:2000]
        bot = ensure_automod_bot()
        message = save_message(room_id, bot["id"], "📢 " + text, message_type="automod", metadata={"broadcast": True})
        await manager.broadcast_to_room(room_id, {"type": "new_message", "message": message})
        return output("Message diffusé.")
    if cmd == "backup":
        try:
            import sys
            sys.path.insert(0, str(PROJECT_ROOT))
            from backup import create_backup
            path = create_backup(quiet=True)
            return output("Backup créé : " + str(path))
        except Exception as error:
            return output("ERREUR backup : " + str(error))
    if cmd == "clear":
        return output("__CLEAR__")
    return output("Commande inconnue. Tape help.")


from __future__ import annotations
from typing import Optional

import re
import secrets
import unicodedata
import sqlite3
from database import get_db_cursor

class SpaceError(ValueError):
    pass

VALID_ROLES = {"member", "moderator", "admin", "owner"}

def _slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", (value or "").strip().lower())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return (value or "espace")[:45]

def _invite() -> str:
    return secrets.token_urlsafe(7).replace("-", "").replace("_", "")[:10].upper()

def _space_row(cursor, space_id: int, viewer_id: Optional[int] = None):
    row = cursor.execute("""
        SELECT s.*, sm.role AS member_role,
               (SELECT COUNT(*) FROM space_members x WHERE x.space_id=s.id) AS member_count,
               (SELECT COUNT(*) FROM space_rooms x WHERE x.space_id=s.id) AS room_count
        FROM spaces s
        LEFT JOIN space_members sm ON sm.space_id=s.id AND sm.user_id=?
        WHERE s.id=?
    """, (viewer_id, space_id)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["is_owner"] = d.get("member_role") == "owner" or int(d.get("owner_user_id") or 0) == int(viewer_id or 0)
    d["can_manage"] = d.get("member_role") in {"owner", "admin"}
    d["can_moderate"] = d.get("member_role") in {"owner", "admin", "moderator"}
    return d

def ensure_default_space_for_user(user_id: int) -> int:
    with get_db_cursor() as c:
        row = c.execute("SELECT id FROM spaces WHERE slug='pichat-central'").fetchone()
        if not row:
            c.execute("""INSERT INTO spaces(name,slug,icon,description,invite_code,visibility)
                         VALUES('PiChat Central','pichat-central','🏠','Espace principal','CENTRAL','invite')""")
            space_id = int(c.lastrowid)
        else:
            space_id = int(row["id"])
        user = c.execute("SELECT is_admin,active_space_id FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            return space_id
        role = "admin" if bool(user["is_admin"]) else "member"
        c.execute("INSERT OR IGNORE INTO space_members(space_id,user_id,role) VALUES(?,?,?)", (space_id,user_id,role))
        if user["active_space_id"] is None:
            c.execute("UPDATE users SET active_space_id=? WHERE id=?", (space_id,user_id))
    return space_id

def get_active_space_id(user_id: int) -> int:
    ensure_default_space_for_user(user_id)
    with get_db_cursor() as c:
        row = c.execute("SELECT active_space_id FROM users WHERE id=?", (user_id,)).fetchone()
        active = int(row["active_space_id"] or 0) if row else 0
        membership = c.execute("SELECT 1 FROM space_members WHERE space_id=? AND user_id=?", (active,user_id)).fetchone() if active else None
        if membership:
            return active
        first = c.execute("SELECT space_id FROM space_members WHERE user_id=? ORDER BY joined_at LIMIT 1", (user_id,)).fetchone()
        if first:
            active = int(first["space_id"])
            c.execute("UPDATE users SET active_space_id=? WHERE id=?", (active,user_id))
            return active
    return ensure_default_space_for_user(user_id)

def list_spaces(user: dict) -> list:
    ensure_default_space_for_user(user["id"])
    active = get_active_space_id(user["id"])
    with get_db_cursor() as c:
        if user.get("is_admin"):
            rows = c.execute("SELECT id FROM spaces ORDER BY created_at").fetchall()
        else:
            rows = c.execute("SELECT space_id AS id FROM space_members WHERE user_id=? ORDER BY joined_at", (user["id"],)).fetchall()
        result=[]
        for row in rows:
            item=_space_row(c,int(row["id"]),user["id"])
            if item:
                item["active"] = int(item["id"]) == active
                if not item.get("can_manage") and not user.get("is_admin"):
                    item["invite_code"] = None
                result.append(item)
    return result

def create_space(user: dict, name: str, icon: str="🏫", description: str="", visibility: str="invite") -> dict:
    if not user.get("is_admin"):
        raise SpaceError("Seul un administrateur PiChat peut créer un établissement en version 2.0.")
    clean = re.sub(r"\s+", " ", (name or "").strip())
    if len(clean) < 2:
        raise SpaceError("Nom trop court.")
    base = _slug(clean)
    with get_db_cursor() as c:
        slug=base; n=2
        while c.execute("SELECT 1 FROM spaces WHERE slug=?",(slug,)).fetchone():
            slug=f"{base[:40]}-{n}"; n+=1
        code=_invite()
        while c.execute("SELECT 1 FROM spaces WHERE invite_code=?",(code,)).fetchone(): code=_invite()
        c.execute("""INSERT INTO spaces(name,slug,icon,description,owner_user_id,invite_code,visibility)
                     VALUES(?,?,?,?,?,?,?)""",(clean,(slug or 'espace'),(icon or '🏫')[:12],(description or '')[:240],user['id'],code,visibility))
        sid=int(c.lastrowid)
        c.execute("INSERT INTO space_members(space_id,user_id,role) VALUES(?,?,'owner')",(sid,user['id']))
        # salon général de l'espace
        room_name=f"{clean} · général"
        suffix=2; candidate=room_name
        while c.execute("SELECT 1 FROM rooms WHERE name=?",(candidate,)).fetchone():
            candidate=f"{room_name} {suffix}"; suffix+=1
        c.execute("INSERT INTO rooms(name,class_code,room_kind,description,icon) VALUES(?,NULL,'space',?,?)",(candidate,f"Discussion générale de {clean}",'#'))
        rid=int(c.lastrowid)
        c.execute("INSERT INTO space_rooms(space_id,room_id,category,position) VALUES(?,?,'GÉNÉRAL',0)",(sid,rid))
        c.execute("UPDATE users SET active_space_id=? WHERE id=?",(sid,user['id']))
        return _space_row(c,sid,user['id'])

def switch_space(user_id: int, space_id: int) -> dict:
    with get_db_cursor() as c:
        member=c.execute("SELECT 1 FROM space_members WHERE space_id=? AND user_id=?",(space_id,user_id)).fetchone()
        admin=c.execute("SELECT is_admin FROM users WHERE id=?",(user_id,)).fetchone()
        if not member and not (admin and admin["is_admin"]):
            raise SpaceError("Tu n'appartiens pas à cet espace.")
        if not member and admin and admin["is_admin"]:
            c.execute("INSERT OR IGNORE INTO space_members(space_id,user_id,role) VALUES(?,?,'admin')",(space_id,user_id))
        c.execute("UPDATE users SET active_space_id=? WHERE id=?",(space_id,user_id))
        return _space_row(c,space_id,user_id)

def join_space(user_id: int, invite_code: str) -> dict:
    code=re.sub(r"[^A-Z0-9]","",(invite_code or '').upper())[:32]
    with get_db_cursor() as c:
        row=c.execute("SELECT id FROM spaces WHERE invite_code=? OR (visibility='public' AND slug=?)",(code,(invite_code or '').strip().lower())).fetchone()
        if not row: raise SpaceError("Invitation invalide.")
        sid=int(row["id"])
        c.execute("INSERT OR IGNORE INTO space_members(space_id,user_id,role) VALUES(?,?,'member')",(sid,user_id))
        c.execute("UPDATE users SET active_space_id=? WHERE id=?",(sid,user_id))
        return _space_row(c,sid,user_id)

def update_space(user: dict, space_id: int, values: dict) -> dict:
    with get_db_cursor() as c:
        current=_space_row(c,space_id,user['id'])
        if not current: raise SpaceError("Espace introuvable.")
        if not user.get('is_admin') and not current.get('can_manage'): raise SpaceError("Permission refusée.")
        fields=[]; args=[]
        for k in ('name','icon','description','visibility'):
            if values.get(k) is not None:
                v=values[k]
                if k=='name': v=re.sub(r"\s+"," ",v.strip())[:50]
                elif k=='icon': v=(v or '🏫')[:12]
                elif k=='description': v=(v or '')[:240]
                fields.append(k+'=?');args.append(v)
        if fields:
            args.append(space_id);c.execute('UPDATE spaces SET '+','.join(fields)+",updated_at=datetime('now') WHERE id=?",tuple(args))
        return _space_row(c,space_id,user['id'])

def regenerate_invite(user: dict, space_id: int) -> str:
    with get_db_cursor() as c:
        current=_space_row(c,space_id,user['id'])
        if not current or (not user.get('is_admin') and not current.get('can_manage')): raise SpaceError("Permission refusée.")
        code=_invite()
        while c.execute("SELECT 1 FROM spaces WHERE invite_code=?",(code,)).fetchone(): code=_invite()
        c.execute("UPDATE spaces SET invite_code=?,updated_at=datetime('now') WHERE id=?",(code,space_id))
        return code

def list_space_rooms(user: dict, space_id: Optional[int]=None) -> list:
    sid=space_id or get_active_space_id(user['id'])
    with get_db_cursor() as c:
        if not user.get('is_admin') and not c.execute("SELECT 1 FROM space_members WHERE space_id=? AND user_id=?",(sid,user['id'])).fetchone():
            raise SpaceError("Accès refusé.")
        rows=c.execute("""SELECT r.id,r.name,r.class_code,r.created_at,r.slow_mode_seconds,r.room_kind,r.owner_user_id,r.description,r.icon,r.invite_code,
                              sr.category,sr.position,sr.space_id,s.name AS space_name,s.icon AS space_icon
                       FROM space_rooms sr JOIN rooms r ON r.id=sr.room_id JOIN spaces s ON s.id=sr.space_id
                       WHERE sr.space_id=? ORDER BY sr.category,sr.position,r.id""",(sid,)).fetchall()
    return [dict(x) for x in rows]

def create_space_room(user: dict, space_id: int, name: str, category: str='SALONS', class_code: Optional[str]=None) -> dict:
    with get_db_cursor() as c:
        current=_space_row(c,space_id,user['id'])
        if not current or (not user.get('is_admin') and not current.get('can_manage')): raise SpaceError("Permission refusée.")
        clean=re.sub(r"\s+"," ",(name or '').strip())[:50]
        if len(clean)<2: raise SpaceError("Nom de salon trop court.")
        candidate=f"{current['name']} · {clean}"; n=2
        while c.execute("SELECT 1 FROM rooms WHERE name=?",(candidate,)).fetchone(): candidate=f"{current['name']} · {clean} {n}"; n+=1
        c.execute("INSERT INTO rooms(name,class_code,room_kind,description,icon) VALUES(?,?, 'space','', '#')",(candidate,(class_code or None)))
        rid=int(c.lastrowid)
        pos=c.execute("SELECT COALESCE(MAX(position),-1)+1 AS n FROM space_rooms WHERE space_id=?",(space_id,)).fetchone()['n']
        c.execute("INSERT INTO space_rooms(space_id,room_id,category,position) VALUES(?,?,?,?)",(space_id,rid,(category or 'SALONS').upper()[:30],int(pos)))
    rooms=list_space_rooms(user,space_id)
    return next(x for x in rooms if int(x['id'])==rid)

def list_members(user: dict, space_id: int) -> list:
    with get_db_cursor() as c:
        current=_space_row(c,space_id,user['id'])
        if not current: raise SpaceError("Espace introuvable.")
        rows=c.execute("""SELECT u.id,u.username,u.class_code,u.is_admin,u.is_moderator,sm.role,sm.joined_at
                          FROM space_members sm JOIN users u ON u.id=sm.user_id WHERE sm.space_id=?
                          ORDER BY CASE sm.role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 WHEN 'moderator' THEN 2 ELSE 3 END,u.username COLLATE NOCASE""",(space_id,)).fetchall()
    return [dict(x) for x in rows]

def set_member_role(user: dict, space_id: int, target_id: int, role: str) -> dict:
    if role not in {'member','moderator','admin'}: raise SpaceError("Rôle invalide.")
    with get_db_cursor() as c:
        current=_space_row(c,space_id,user['id'])
        if not current or (not user.get('is_admin') and not current.get('can_manage')): raise SpaceError("Permission refusée.")
        target=c.execute("SELECT role FROM space_members WHERE space_id=? AND user_id=?",(space_id,target_id)).fetchone()
        if not target: raise SpaceError("Membre introuvable.")
        if target['role']=='owner': raise SpaceError("Le propriétaire ne peut pas être rétrogradé.")
        c.execute("UPDATE space_members SET role=? WHERE space_id=? AND user_id=?",(role,space_id,target_id))
        return {'space_id':space_id,'user_id':target_id,'role':role}

def remove_member(user: dict, space_id: int, target_id: int) -> None:
    with get_db_cursor() as c:
        current=_space_row(c,space_id,user['id'])
        if int(target_id)==int(user['id']):
            target=c.execute("SELECT role FROM space_members WHERE space_id=? AND user_id=?",(space_id,target_id)).fetchone()
            if target and target['role']=='owner': raise SpaceError("Le propriétaire ne peut pas quitter son espace.")
        elif not current or (not user.get('is_admin') and not current.get('can_manage')):
            raise SpaceError("Permission refusée.")
        target=c.execute("SELECT role FROM space_members WHERE space_id=? AND user_id=?",(space_id,target_id)).fetchone()
        if target and target['role']=='owner': raise SpaceError("Le propriétaire ne peut pas être retiré.")
        c.execute("DELETE FROM space_members WHERE space_id=? AND user_id=?",(space_id,target_id))
        active=c.execute("SELECT active_space_id FROM users WHERE id=?",(target_id,)).fetchone()
        if active and int(active['active_space_id'] or 0)==int(space_id): c.execute("UPDATE users SET active_space_id=NULL WHERE id=?",(target_id,))

def delete_space(user: dict, space_id: int) -> None:
    with get_db_cursor() as c:
        current=_space_row(c,space_id,user['id'])
        if not current: raise SpaceError("Espace introuvable.")
        if current['slug']=='pichat-central': raise SpaceError("PiChat Central ne peut pas être supprimé.")
        if not user.get('is_admin') and not current.get('is_owner'): raise SpaceError("Seul le propriétaire peut supprimer cet espace.")
        room_ids=[int(r['room_id']) for r in c.execute("SELECT room_id FROM space_rooms WHERE space_id=?",(space_id,)).fetchall()]
        c.execute("DELETE FROM spaces WHERE id=?",(space_id,))
        for rid in room_ids: c.execute("DELETE FROM rooms WHERE id=?",(rid,))

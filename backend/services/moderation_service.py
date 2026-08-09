from __future__ import annotations
from datetime import datetime, timedelta, timezone
from database import get_db_cursor
from permissions import moderator_can_manage

class ModerationError(Exception): pass
class ModerationPermissionError(ModerationError): pass
class ModerationNotFoundError(ModerationError): pass


def _utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def _sql_dt(value):
    return value.strftime("%Y-%m-%d %H:%M:%S")

def _user_row(user_id):
    with get_db_cursor() as c:
        row=c.execute("""SELECT id,username,class_code,is_admin,is_moderator,moderator_class_code,is_bot,
            is_banned,banned_reason,ban_until,muted_until,mute_reason,warning_count FROM users WHERE id=?""",(user_id,)).fetchone()
    return dict(row) if row else None

def clear_expired_restrictions(user_id):
    now=_sql_dt(_utc_now())
    with get_db_cursor() as c:
        c.execute("""UPDATE users SET is_banned=0,banned_at=NULL,banned_reason='',ban_until=NULL
                     WHERE id=? AND is_banned=1 AND ban_until IS NOT NULL AND ban_until<=?""",(user_id,now))
        c.execute("""UPDATE users SET muted_until=NULL,mute_reason=''
                     WHERE id=? AND muted_until IS NOT NULL AND muted_until<=?""",(user_id,now))

def restriction_status(user_id):
    clear_expired_restrictions(user_id)
    u=_user_row(user_id)
    if not u: return None
    now=_sql_dt(_utc_now())
    u['is_muted']=bool(u.get('muted_until') and u['muted_until']>now)
    return u

def ensure_can_manage(actor,target):
    if not target: raise ModerationNotFoundError("Compte introuvable.")
    if actor['id']==target['id']: raise ModerationPermissionError("Tu ne peux pas te sanctionner toi-même.")
    if actor.get('is_admin'):
        if target.get('is_admin'): raise ModerationPermissionError("Un administrateur est protégé.")
        return
    if not moderator_can_manage(actor,target):
        raise ModerationPermissionError("Tu ne peux modérer que les joueurs de ta classe.")

def _record(actor_id,target_id,action,reason='',duration=None,room_id=None,message_id=None,expires_at=None):
    with get_db_cursor() as c:
        c.execute("""INSERT INTO moderation_actions
            (actor_id,target_id,action,reason,duration_minutes,room_id,message_id,expires_at)
            VALUES (?,?,?,?,?,?,?,?)""",(actor_id,target_id,action,(reason or '')[:400],duration,room_id,message_id,expires_at))

def warn_user(actor,user_id,reason):
    target=_user_row(user_id); ensure_can_manage(actor,target)
    with get_db_cursor() as c:
        c.execute("UPDATE users SET warning_count=warning_count+1 WHERE id=?",(user_id,))
    _record(actor['id'],user_id,'warning',reason)
    return restriction_status(user_id)

def mute_user(actor,user_id,duration_minutes,reason):
    target=_user_row(user_id); ensure_can_manage(actor,target)
    expires=_sql_dt(_utc_now()+timedelta(minutes=duration_minutes))
    with get_db_cursor() as c:
        c.execute("UPDATE users SET muted_until=?,mute_reason=? WHERE id=?",(expires,(reason or '')[:400],user_id))
    _record(actor['id'],user_id,'mute',reason,duration_minutes,expires_at=expires)
    return restriction_status(user_id)

def unmute_user(actor,user_id):
    target=_user_row(user_id); ensure_can_manage(actor,target)
    with get_db_cursor() as c:
        c.execute("UPDATE users SET muted_until=NULL,mute_reason='' WHERE id=?",(user_id,))
    _record(actor['id'],user_id,'unmute')
    return restriction_status(user_id)

def temp_ban_user(actor,user_id,duration_minutes,reason):
    target=_user_row(user_id); ensure_can_manage(actor,target)
    expires=_sql_dt(_utc_now()+timedelta(minutes=duration_minutes))
    with get_db_cursor() as c:
        c.execute("""UPDATE users SET is_banned=1,banned_at=datetime('now'),banned_reason=?,ban_until=? WHERE id=?""",((reason or '')[:400],expires,user_id))
        c.execute("DELETE FROM sessions WHERE user_id=?",(user_id,))
    _record(actor['id'],user_id,'temporary_ban',reason,duration_minutes,expires_at=expires)
    return restriction_status(user_id)

def list_actions(actor,limit=200):
    limit=max(1,min(int(limit),500)); params=[]
    where=''
    if not actor.get('is_admin'):
        where='WHERE tu.class_code=?'; params.append(actor.get('moderator_class_code'))
    params.append(limit)
    with get_db_cursor() as c:
        rows=c.execute(f"""SELECT a.id,a.action,a.reason,a.duration_minutes,a.expires_at,a.created_at,
            au.username AS actor,tu.username AS target,tu.class_code,r.name AS room_name
            FROM moderation_actions a LEFT JOIN users au ON au.id=a.actor_id
            LEFT JOIN users tu ON tu.id=a.target_id LEFT JOIN rooms r ON r.id=a.room_id
            {where} ORDER BY a.created_at DESC LIMIT ?""",tuple(params)).fetchall()
    return [dict(x) for x in rows]

def add_note(actor,target_id,note):
    target=_user_row(target_id); ensure_can_manage(actor,target)
    with get_db_cursor() as c:
        c.execute("INSERT INTO moderator_notes(target_id,author_id,note) VALUES(?,?,?)",(target_id,actor['id'],note.strip()[:1000]))
    _record(actor['id'],target_id,'note',note)

def list_notes(actor,target_id):
    target=_user_row(target_id); ensure_can_manage(actor,target)
    with get_db_cursor() as c:
        rows=c.execute("""SELECT n.id,n.note,n.created_at,u.username AS author
            FROM moderator_notes n LEFT JOIN users u ON u.id=n.author_id WHERE n.target_id=? ORDER BY n.created_at DESC""",(target_id,)).fetchall()
    return [dict(x) for x in rows]

def list_reports(actor,status='open'):
    clauses=[]; params=[]
    if status in {'open','resolved','rejected'}:
        clauses.append('mr.status=?'); params.append(status)
    if not actor.get('is_admin'):
        clauses.append('room.class_code=?'); params.append(actor.get('moderator_class_code'))
    where=('WHERE '+' AND '.join(clauses)) if clauses else ''
    with get_db_cursor() as c:
        rows=c.execute(f"""SELECT mr.id,mr.message_id,mr.reason,mr.status,mr.resolution_note,mr.created_at,mr.handled_at,
            reporter.username AS reporter,author.username AS author,author.id AS author_id,author.class_code,
            m.content,m.room_id,room.name AS room_name,room.class_code AS room_class,handler.username AS handled_by
            FROM message_reports mr JOIN users reporter ON reporter.id=mr.reporter_id
            JOIN messages m ON m.id=mr.message_id JOIN users author ON author.id=m.user_id
            JOIN rooms room ON room.id=m.room_id LEFT JOIN users handler ON handler.id=mr.handled_by
            {where} ORDER BY CASE WHEN mr.status='open' THEN 0 ELSE 1 END,mr.created_at DESC LIMIT 300""",tuple(params)).fetchall()
    return [dict(x) for x in rows]

def decide_report(actor,report_id,status,note):
    reports=list_reports(actor,status='all')
    report=next((x for x in reports if x['id']==report_id),None)
    if not report: raise ModerationNotFoundError("Signalement introuvable ou hors de ta classe.")
    with get_db_cursor() as c:
        c.execute("UPDATE message_reports SET status=?,resolution_note=?,handled_by=?,handled_at=datetime('now') WHERE id=?",(status,note.strip()[:500],actor['id'],report_id))
    _record(actor['id'],report.get('author_id'),'report_'+status,note,room_id=report.get('room_id'),message_id=report.get('message_id'))
    return True

def get_room_slow_mode(room_id):
    with get_db_cursor() as c:
        row=c.execute("SELECT id,name,class_code,slow_mode_seconds FROM rooms WHERE id=?",(room_id,)).fetchone()
    return dict(row) if row else None

def set_room_slow_mode(actor,room_id,seconds):
    room=get_room_slow_mode(room_id)
    if not room: raise ModerationNotFoundError("Salon introuvable.")
    if not actor.get('is_admin') and room.get('class_code')!=actor.get('moderator_class_code'):
        raise ModerationPermissionError("Le mode lent est limité à ton serveur de classe.")
    with get_db_cursor() as c:
        c.execute("UPDATE rooms SET slow_mode_seconds=? WHERE id=?",(seconds,room_id))
    _record(actor['id'],None,'slow_mode',str(seconds),room_id=room_id)
    return get_room_slow_mode(room_id)

def get_advanced_settings():
    with get_db_cursor() as c:
        row=c.execute("""SELECT profanity_enabled,profanity_words,duplicate_enabled,duplicate_window_seconds,
            similarity_enabled,similarity_ratio,similarity_min_length,similarity_window_seconds,
            burst_enabled,burst_count,burst_window_seconds,uppercase_enabled,uppercase_min_length,uppercase_ratio,
            rate_limit_count,rate_limit_window_seconds,repeated_char_limit,punctuation_limit,emoji_limit,
            word_repeat_limit,cooldown_base_seconds,cooldown_max_seconds,rapid_count,rapid_window_seconds
            FROM moderation_settings WHERE id=1""").fetchone()
    d=dict(row)
    for k in ('profanity_enabled','duplicate_enabled','similarity_enabled','burst_enabled','uppercase_enabled'):
        d[k]=bool(d[k])
    return d

def set_advanced_settings(values):
    with get_db_cursor() as c:
        c.execute("""UPDATE moderation_settings SET profanity_enabled=?,profanity_words=?,duplicate_enabled=?,
            duplicate_window_seconds=?,similarity_enabled=?,similarity_ratio=?,similarity_min_length=?,
            similarity_window_seconds=?,burst_enabled=?,burst_count=?,burst_window_seconds=?,uppercase_enabled=?,
            uppercase_min_length=?,uppercase_ratio=?,rate_limit_count=?,rate_limit_window_seconds=?,
            repeated_char_limit=?,punctuation_limit=?,emoji_limit=?,word_repeat_limit=?,cooldown_base_seconds=?,
            cooldown_max_seconds=?,updated_at=datetime('now') WHERE id=1""",
            (int(values['profanity_enabled']),values['profanity_words'],int(values['duplicate_enabled']),values['duplicate_window_seconds'],
             int(values['similarity_enabled']),values['similarity_ratio'],values['similarity_min_length'],values['similarity_window_seconds'],
             int(values['burst_enabled']),values['burst_count'],values['burst_window_seconds'],int(values['uppercase_enabled']),
             values['uppercase_min_length'],values['uppercase_ratio'],values['rate_limit_count'],values['rate_limit_window_seconds'],
             values['repeated_char_limit'],values['punctuation_limit'],values['emoji_limit'],values['word_repeat_limit'],
             values['cooldown_base_seconds'],values['cooldown_max_seconds'],values['rapid_count'],values['rapid_window_seconds']))
    return get_advanced_settings()

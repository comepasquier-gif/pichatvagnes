from __future__ import annotations

import json
from database import get_db_cursor
from services.tutor_service import tutor_answer


def _structured_items(mode: str, answer: str):
    items = []
    if mode == "flashcards":
        for raw in (answer or "").splitlines():
            if "::" not in raw:
                continue
            front, back = raw.split("::", 1)
            front, back = front.strip(" -*\t"), back.strip()
            if front and back:
                items.append({"front": front[:300], "back": back[:800]})
    elif mode == "quiz":
        # Le texte reste toujours disponible ; cette structure sert au mode révision.
        questions = [line.strip(" -*\t") for line in (answer or "").splitlines() if line.strip().startswith(tuple(str(i) for i in range(1, 10)))]
        items = [{"question": q[:700], "answer": "Voir la correction dans la réponse PiTutor."} for q in questions[:20]]
    return items


async def ask_and_record(subject, mode, prompt, student_answer, user, difficulty="adaptée", count=5):
    enriched = prompt
    if mode in {"quiz", "flashcards"}:
        enriched = f"{prompt}\n\nNombre d'éléments souhaité : {count}. Difficulté : {difficulty}."
    elif difficulty:
        enriched = f"{prompt}\n\nDifficulté souhaitée : {difficulty}."
    response = await tutor_answer(subject, mode, enriched, student_answer, user)
    answer = response.get("answer") or ""
    with get_db_cursor() as c:
        c.execute(
            """INSERT INTO tutor_history(user_id,subject,mode,prompt,student_answer,tutor_answer,provider)
               VALUES(?,?,?,?,?,?,?)""",
            (user["id"], subject[:60], mode[:30], prompt[:5000], student_answer[:4000], answer[:12000], response.get("provider") or "local"),
        )
        history_id = int(c.lastrowid)
    try:
        from services.rpg_service import progress_quest
        progress_quest(user["id"], "tutor", 1)
    except Exception:
        pass
    response.update({
        "history_id": history_id,
        "subject": subject,
        "mode": mode,
        "difficulty": difficulty,
        "study_items": _structured_items(mode, answer),
    })
    return response


def list_history(user_id: int, limit=100):
    with get_db_cursor() as c:
        rows = c.execute(
            """SELECT id,subject,mode,prompt,student_answer,tutor_answer,provider,favorite,created_at
               FROM tutor_history WHERE user_id=? ORDER BY id DESC LIMIT ?""",
            (user_id, max(1, min(int(limit), 300))),
        ).fetchall()
    return [dict(r) for r in rows]


def toggle_favorite(user_id: int, history_id: int):
    with get_db_cursor() as c:
        row = c.execute("SELECT favorite FROM tutor_history WHERE id=? AND user_id=?", (history_id, user_id)).fetchone()
        if not row:
            return None
        value = 0 if row["favorite"] else 1
        c.execute("UPDATE tutor_history SET favorite=? WHERE id=?", (value, history_id))
    return bool(value)


def delete_history(user_id: int, history_id: int):
    with get_db_cursor() as c:
        c.execute("DELETE FROM tutor_history WHERE id=? AND user_id=?", (history_id, user_id))
        return c.rowcount > 0


def create_study_set(user_id: int, title: str, subject: str, kind: str, items: list[dict]):
    safe_items = items[:50]
    with get_db_cursor() as c:
        c.execute(
            "INSERT INTO study_sets(user_id,title,subject,kind,content_json) VALUES(?,?,?,?,?)",
            (user_id, title.strip()[:80], subject.strip()[:60], kind, json.dumps(safe_items, ensure_ascii=False)[:30000]),
        )
        set_id = int(c.lastrowid)
    return get_study_set(user_id, set_id)


def get_study_set(user_id: int, set_id: int):
    with get_db_cursor() as c:
        row = c.execute(
            "SELECT id,title,subject,kind,content_json,created_at,updated_at FROM study_sets WHERE id=? AND user_id=?",
            (set_id, user_id),
        ).fetchone()
    if not row:
        return None
    result = dict(row)
    try:
        result["items"] = json.loads(result.pop("content_json") or "[]")
    except Exception:
        result["items"] = []
    return result


def list_study_sets(user_id: int):
    with get_db_cursor() as c:
        rows = c.execute(
            """SELECT s.id,s.title,s.subject,s.kind,s.content_json,s.created_at,s.updated_at,
                      COUNT(a.id) AS attempts,COALESCE(MAX(CASE WHEN a.total>0 THEN a.score*100.0/a.total END),0) AS best_percent
               FROM study_sets s LEFT JOIN study_attempts a ON a.set_id=s.id AND a.user_id=?
               WHERE s.user_id=? GROUP BY s.id ORDER BY s.updated_at DESC,s.id DESC""",
            (user_id, user_id),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            content = json.loads(item.pop("content_json") or "[]")
        except Exception:
            content = []
        item["item_count"] = len(content)
        item["best_percent"] = round(float(item.get("best_percent") or 0), 1)
        result.append(item)
    return result


def delete_study_set(user_id: int, set_id: int):
    with get_db_cursor() as c:
        c.execute("DELETE FROM study_sets WHERE id=? AND user_id=?", (set_id, user_id))
        return c.rowcount > 0


def record_attempt(user_id: int, set_id: int, score: int, total: int, answers: list):
    if not get_study_set(user_id, set_id):
        return None
    with get_db_cursor() as c:
        c.execute(
            "INSERT INTO study_attempts(set_id,user_id,score,total,answers_json) VALUES(?,?,?,?,?)",
            (set_id, user_id, score, total, json.dumps(answers, ensure_ascii=False)[:20000]),
        )
    return {"recorded": True, "score": score, "total": total}


def tutor_dashboard(user_id: int):
    with get_db_cursor() as c:
        history = c.execute("SELECT COUNT(*) AS n,COUNT(DISTINCT subject) AS subjects FROM tutor_history WHERE user_id=?", (user_id,)).fetchone()
        sets = c.execute("SELECT COUNT(*) AS n FROM study_sets WHERE user_id=?", (user_id,)).fetchone()
        attempts = c.execute("SELECT COUNT(*) AS n,COALESCE(AVG(CASE WHEN total>0 THEN score*100.0/total END),0) AS avg_score FROM study_attempts WHERE user_id=?", (user_id,)).fetchone()
    return {
        "questions": int(history["n"] or 0),
        "subjects": int(history["subjects"] or 0),
        "study_sets": int(sets["n"] or 0),
        "attempts": int(attempts["n"] or 0),
        "average_score": round(float(attempts["avg_score"] or 0), 1),
    }

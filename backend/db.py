"""
db.py — SQLite database for interview sessions, candidates, and question caching.
Zero extra dependencies — uses stdlib sqlite3.
"""

import sqlite3
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).resolve().parent / "interviews.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS candidates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS job_templates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            role        TEXT NOT NULL,
            skills_json TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            UNIQUE(role, skills_json)
        );

        CREATE TABLE IF NOT EXISTS questions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            job_template_id INTEGER NOT NULL REFERENCES job_templates(id) ON DELETE CASCADE,
            skill           TEXT NOT NULL,
            question_text   TEXT NOT NULL,
            sort_order      INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id              TEXT PRIMARY KEY,
            candidate_id    INTEGER NOT NULL REFERENCES candidates(id),
            job_template_id INTEGER NOT NULL REFERENCES job_templates(id),
            status          TEXT NOT NULL DEFAULT 'active',
            question_index  INTEGER NOT NULL DEFAULT 0,
            current_question TEXT,
            job_description TEXT DEFAULT '',
            candidate_profile TEXT DEFAULT '',
            created_at      TEXT NOT NULL,
            completed_at    TEXT
        );

        CREATE TABLE IF NOT EXISTS session_answers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            skill       TEXT NOT NULL,
            question    TEXT NOT NULL,
            transcript  TEXT NOT NULL DEFAULT '',
            score       INTEGER NOT NULL DEFAULT 0,
            feedback    TEXT NOT NULL DEFAULT '',
            is_followup INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL
        );
    """)
    # Migrate: add question_index to existing sessions table
    try:
        conn.execute("ALTER TABLE sessions ADD COLUMN question_index INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    # Migrate: add job_description and candidate_profile
    for col in ("job_description", "candidate_profile"):
        try:
            conn.execute(f"ALTER TABLE sessions ADD COLUMN {col} TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


# ── Candidates ──────────────────────────────────────────────────────────────

def register_candidate(name: str) -> dict:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO candidates (name, created_at) VALUES (?, ?)",
        (name.strip(), _now()),
    )
    conn.commit()
    candidate_id = cur.lastrowid
    conn.close()
    return {"id": candidate_id, "name": name.strip()}


# ── Job Templates & Questions ───────────────────────────────────────────────

def _skills_key(skills: list[str]) -> str:
    return json.dumps(sorted(skills))


def find_or_create_job_template(role: str, skills: list[str]) -> int:
    """Return job_template_id. Creates if not exists."""
    key = _skills_key(skills)
    conn = get_conn()

    row = conn.execute(
        "SELECT id FROM job_templates WHERE role = ? AND skills_json = ?",
        (role.strip(), key),
    ).fetchone()

    if row:
        conn.close()
        return row["id"]

    cur = conn.execute(
        "INSERT INTO job_templates (role, skills_json, created_at) VALUES (?, ?, ?)",
        (role.strip(), key, _now()),
    )
    conn.commit()
    jtid = cur.lastrowid
    conn.close()
    return jtid


def job_template_has_questions(job_template_id: int) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM questions WHERE job_template_id = ?",
        (job_template_id,),
    ).fetchone()
    conn.close()
    return row["cnt"] > 0


def insert_questions(job_template_id: int, questions: list[dict]):
    """
    questions: [{"skill": str, "question_text": str}, ...]
    """
    conn = get_conn()
    for i, q in enumerate(questions):
        conn.execute(
            "INSERT INTO questions (job_template_id, skill, question_text, sort_order) VALUES (?, ?, ?, ?)",
            (job_template_id, q["skill"], q["question_text"], i),
        )
    conn.commit()
    conn.close()


def get_questions_for_job(job_template_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, skill, question_text, sort_order FROM questions WHERE job_template_id = ? ORDER BY sort_order",
        (job_template_id,),
    ).fetchall()
    conn.close()
    return [{"id": r["id"], "skill": r["skill"], "question_text": r["question_text"], "sort_order": r["sort_order"]} for r in rows]


# ── Sessions ────────────────────────────────────────────────────────────────

def create_session(candidate_id: int, job_template_id: int, skills: list[str], first_question: str, job_description: str = "", candidate_profile: str = "") -> str:
    session_id = str(uuid.uuid4())
    conn = get_conn()
    conn.execute(
        "INSERT INTO sessions (id, candidate_id, job_template_id, status, question_index, current_question, job_description, candidate_profile, created_at) VALUES (?, ?, ?, 'active', 0, ?, ?, ?, ?)",
        (session_id, candidate_id, job_template_id, first_question, job_description, candidate_profile, _now()),
    )
    conn.commit()
    conn.close()
    return session_id


def get_session(session_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        conn.close()
        return None

    jt_row = conn.execute(
        "SELECT role, skills_json FROM job_templates WHERE id = ?",
        (row["job_template_id"],),
    ).fetchone()
    conn.close()

    skills = json.loads(jt_row["skills_json"]) if jt_row else []
    return {
        "session_id": row["id"],
        "candidate_id": row["candidate_id"],
        "job_template_id": row["job_template_id"],
        "role": jt_row["role"] if jt_row else "",
        "skills": skills,
        "question_index": row["question_index"],
        "history": get_session_history(session_id),
        "status": row["status"],
        "current_question": row["current_question"],
        "job_description": row["job_description"] or "",
        "candidate_profile": row["candidate_profile"] or "",
    }


def update_session(session_id: str, updates: dict):
    allowed = {"status", "question_index", "current_question", "completed_at"}
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if not filtered:
        return
    set_clause = ", ".join(f"{k} = ?" for k in filtered)
    values = list(filtered.values()) + [session_id]
    conn = get_conn()
    conn.execute(f"UPDATE sessions SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def get_session_history(session_id: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT skill, question, transcript, score, feedback, is_followup FROM session_answers WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "skill": r["skill"],
            "question": r["question"],
            "answer": r["transcript"],
            "score": r["score"],
            "feedback": r["feedback"],
            "is_followup": bool(r["is_followup"]),
        }
        for r in rows
    ]


def append_history(session_id: str, entry: dict):
    conn = get_conn()
    conn.execute(
        "INSERT INTO session_answers (session_id, skill, question, transcript, score, feedback, is_followup, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            entry.get("skill", ""),
            entry.get("question", ""),
            entry.get("answer", ""),
            entry.get("score", 0),
            entry.get("feedback", ""),
            1 if entry.get("is_followup") else 0,
            _now(),
        ),
    )
    conn.commit()
    conn.close()


def delete_session(session_id: str):
    conn = get_conn()
    conn.execute("DELETE FROM session_answers WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()


# ── Candidate Session History ───────────────────────────────────────────────

def get_candidate_sessions(candidate_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT s.id, s.status, s.created_at, s.completed_at, jt.role, jt.skills_json
        FROM sessions s
        JOIN job_templates jt ON s.job_template_id = jt.id
        WHERE s.candidate_id = ?
        ORDER BY s.created_at DESC
        """,
        (candidate_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "session_id": r["id"],
            "status": r["status"],
            "role": r["role"],
            "skills": json.loads(r["skills_json"]),
            "created_at": r["created_at"],
            "completed_at": r["completed_at"],
        }
        for r in rows
    ]


# ── Dashboard Overview ──────────────────────────────────────────────────────

def get_dashboard_overview() -> dict:
    """Return all candidates, sessions, answers, and aggregate stats."""
    conn = get_conn()

    # Stats
    stats = {}
    row = conn.execute("SELECT COUNT(*) AS n FROM candidates").fetchone()
    stats["total_candidates"] = row["n"]

    row = conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()
    stats["total_sessions"] = row["n"]

    row = conn.execute("SELECT COUNT(*) AS n FROM sessions WHERE status = 'complete'").fetchone()
    stats["completed"] = row["n"]
    stats["active"] = stats["total_sessions"] - stats["completed"]

    row = conn.execute("SELECT AVG(score) AS avg FROM session_answers").fetchone()
    stats["avg_score"] = round(row["avg"], 1) if row["avg"] else 0

    # All candidates with their sessions
    cand_rows = conn.execute(
        "SELECT id, name, created_at FROM candidates ORDER BY name"
    ).fetchall()

    candidates = []
    for c in cand_rows:
        sess_rows = conn.execute(
            """
            SELECT s.id, s.status, s.created_at, s.completed_at, s.follow_up_count,
                   jt.role, jt.skills_json
            FROM sessions s
            JOIN job_templates jt ON s.job_template_id = jt.id
            WHERE s.candidate_id = ?
            ORDER BY s.created_at DESC
            """,
            (c["id"],),
        ).fetchall()

        sessions = []
        for s in sess_rows:
            ans_rows = conn.execute(
                """
                SELECT skill, question, transcript, score, feedback, is_followup
                FROM session_answers
                WHERE session_id = ?
                ORDER BY id
                """,
                (s["id"],),
            ).fetchall()

            answers = [
                {
                    "skill": a["skill"],
                    "question": a["question"],
                    "transcript": a["transcript"],
                    "score": a["score"],
                    "feedback": a["feedback"],
                    "is_followup": bool(a["is_followup"]),
                }
                for a in ans_rows
            ]

            scores = [a["score"] for a in answers if a["score"] > 0]
            avg_score = round(sum(scores) / len(scores), 1) if scores else 0

            sessions.append({
                "session_id": s["id"],
                "role": s["role"],
                "skills": json.loads(s["skills_json"]),
                "status": s["status"],
                "avg_score": avg_score,
                "created_at": s["created_at"],
                "completed_at": s["completed_at"],
                "answers": answers,
            })

        candidates.append({
            "id": c["id"],
            "name": c["name"],
            "created_at": c["created_at"],
            "sessions": sessions,
        })

    conn.close()
    return {"stats": stats, "candidates": candidates}


# ── Init on import ──────────────────────────────────────────────────────────
init_db()

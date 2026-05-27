from __future__ import annotations
import sqlite3
import json
from typing import Any, Dict, List, Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import DB_PATH


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sources (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                filename     TEXT NOT NULL,
                filepath     TEXT NOT NULL,
                content_hash TEXT UNIQUE NOT NULL,
                title        TEXT,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS questions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id    INTEGER REFERENCES sources(id),
                concept      TEXT NOT NULL,
                question     TEXT NOT NULL,
                ideal_answer TEXT NOT NULL,
                difficulty   INTEGER DEFAULT 3,
                times_asked  INTEGER DEFAULT 0,
                times_correct INTEGER DEFAULT 0,
                anki_note_id INTEGER,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id  INTEGER REFERENCES sources(id),
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at   TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS answers (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id       INTEGER REFERENCES sessions(id),
                question_id      INTEGER REFERENCES questions(id),
                answer_text      TEXT NOT NULL,
                score            INTEGER,
                feedback         TEXT,
                correct_elements TEXT,
                missing_elements TEXT,
                anki_ease        INTEGER,
                answered_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)


def save_ingestion(data: Dict[str, Any]) -> int:
    """Persist a source + its questions. Returns source_id."""
    with _conn() as conn:
        existing = conn.execute(
            "SELECT id FROM sources WHERE content_hash = ?",
            (data["content_hash"],),
        ).fetchone()
        if existing:
            return existing["id"]

        cur = conn.execute(
            "INSERT INTO sources (filename, filepath, content_hash, title) VALUES (?, ?, ?, ?)",
            (data["filename"], data["filepath"], data["content_hash"], data.get("source_title", data["filename"])),
        )
        source_id = cur.lastrowid

        for q in data["questions"]:
            conn.execute(
                """INSERT INTO questions (source_id, concept, question, ideal_answer, difficulty)
                   VALUES (?, ?, ?, ?, ?)""",
                (source_id, q["concept"], q["question"], q["ideal_answer"], q.get("difficulty", 3)),
            )
        return source_id


def get_sources() -> List[Dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute("""
            SELECT s.*, COUNT(q.id) as question_count
            FROM sources s
            LEFT JOIN questions q ON q.source_id = s.id
            GROUP BY s.id
            ORDER BY s.created_at DESC
        """).fetchall()
        return [dict(r) for r in rows]


def get_questions_for_quiz(source_id: Optional[int] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """Return questions prioritised by struggle (lowest accuracy first, new questions first)."""
    with _conn() as conn:
        where = "WHERE source_id = ?" if source_id is not None else ""
        params: tuple = (source_id, limit) if source_id is not None else (limit,)
        rows = conn.execute(
            f"""
            SELECT *,
                CASE
                    WHEN times_asked = 0 THEN 1.1
                    ELSE 1.0 - (CAST(times_correct AS REAL) / times_asked)
                END AS struggle_weight
            FROM questions
            {where}
            ORDER BY struggle_weight DESC, RANDOM()
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def start_session(source_id: Optional[int] = None) -> int:
    with _conn() as conn:
        cur = conn.execute("INSERT INTO sessions (source_id) VALUES (?)", (source_id,))
        return cur.lastrowid


def end_session(session_id: int) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE sessions SET ended_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session_id,),
        )


def save_answer(
    session_id: int,
    question_id: int,
    answer_text: str,
    evaluation: Dict[str, Any],
    anki_ease: int,
) -> None:
    score = evaluation["score"]
    with _conn() as conn:
        conn.execute(
            """INSERT INTO answers
               (session_id, question_id, answer_text, score, feedback,
                correct_elements, missing_elements, anki_ease)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                question_id,
                answer_text,
                score,
                evaluation.get("feedback", ""),
                json.dumps(evaluation.get("correct_elements", [])),
                json.dumps(evaluation.get("missing_elements", [])),
                anki_ease,
            ),
        )
        conn.execute(
            """UPDATE questions
               SET times_asked   = times_asked + 1,
                   times_correct = times_correct + ?
               WHERE id = ?""",
            (1 if score >= 6 else 0, question_id),
        )


def get_question_history(question_id: int) -> List[Dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT score, anki_ease, answered_at
               FROM answers
               WHERE question_id = ?
               ORDER BY answered_at DESC
               LIMIT 10""",
            (question_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def update_anki_note_id(question_id: int, note_id: int) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE questions SET anki_note_id = ? WHERE id = ?",
            (note_id, question_id),
        )


def get_all_questions(source_id: Optional[int] = None) -> List[Dict[str, Any]]:
    with _conn() as conn:
        where = "WHERE source_id = ?" if source_id is not None else ""
        params: tuple = (source_id,) if source_id is not None else ()
        rows = conn.execute(f"SELECT * FROM questions {where}", params).fetchall()
        return [dict(r) for r in rows]


def get_stats() -> Dict[str, Any]:
    with _conn() as conn:
        total_q = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        total_a = conn.execute("SELECT COUNT(*) FROM answers").fetchone()[0]
        avg_score = conn.execute("SELECT AVG(score) FROM answers").fetchone()[0]
        struggling = conn.execute("""
            SELECT concept, question, times_asked, times_correct,
                   ROUND(CAST(times_correct AS REAL) / times_asked * 100, 1) AS accuracy_pct
            FROM questions
            WHERE times_asked > 0
            ORDER BY accuracy_pct ASC
            LIMIT 5
        """).fetchall()
        return {
            "total_questions": total_q,
            "total_answers": total_a,
            "avg_score": round(avg_score, 1) if avg_score else None,
            "struggling": [dict(r) for r in struggling],
        }

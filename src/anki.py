from __future__ import annotations
import sys
import os
from typing import Any, Dict, List, Optional

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import ANKI_CONNECT_URL, ANKI_DECK_NAME


def _invoke(action: str, **params: Any) -> Any:
    payload = {"action": action, "version": 6, "params": params}
    try:
        resp = requests.post(ANKI_CONNECT_URL, json=payload, timeout=5)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise ConnectionError(
            "Cannot reach AnkiConnect at port 8765. "
            "Make sure Anki is open and AnkiConnect is installed."
        )
    result = resp.json()
    if result.get("error"):
        raise RuntimeError(f"AnkiConnect: {result['error']}")
    return result["result"]


def is_running() -> bool:
    try:
        _invoke("version")
        return True
    except Exception:
        return False


def ensure_deck(deck_name: str = ANKI_DECK_NAME) -> None:
    existing = _invoke("deckNames")
    if deck_name not in existing:
        _invoke("createDeck", deck=deck_name)


def add_note(question: str, ideal_answer: str, concept: str, deck: str = ANKI_DECK_NAME) -> Optional[int]:
    """
    Add a Basic note to Anki. Returns note ID, or None if duplicate.
    """
    tag = concept.lower().replace(" ", "-").replace("/", "-")
    note = {
        "deckName": deck,
        "modelName": "Basic",
        "fields": {
            "Front": f"<b>[{concept}]</b><br><br>{question}",
            "Back": ideal_answer.replace("\n", "<br>"),
        },
        "options": {"allowDuplicate": False, "duplicateScope": "deck"},
        "tags": ["academic-tutor", tag],
    }
    try:
        note_id = _invoke("addNote", note=note)
        return note_id
    except RuntimeError as e:
        if "duplicate" in str(e).lower():
            return None
        raise


def tag_note_with_performance(note_id: int, ease: int) -> None:
    """
    Add a performance tag to a note so reviews are visible in Anki browser.
    ease: 1=Again, 2=Hard, 3=Good, 4=Easy
    """
    tag_map = {1: "tutor::again", 2: "tutor::hard", 3: "tutor::good", 4: "tutor::easy"}
    # Remove previous tutor performance tags first
    for tag in tag_map.values():
        try:
            _invoke("removeTags", notes=[note_id], tags=tag)
        except Exception:
            pass
    _invoke("addTags", notes=[note_id], tags=tag_map[ease])


def sync_questions(questions: List[Dict[str, Any]]) -> Dict[int, Optional[int]]:
    """
    Sync a list of question dicts to Anki.
    Returns {db_question_id: anki_note_id | None}.
    """
    ensure_deck()
    results: Dict[int, Optional[int]] = {}
    for q in questions:
        if q.get("anki_note_id"):
            results[q["id"]] = q["anki_note_id"]
            continue
        note_id = add_note(q["question"], q["ideal_answer"], q["concept"])
        results[q["id"]] = note_id
    return results

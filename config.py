from __future__ import annotations
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "tutor.db"
ANKI_CONNECT_URL = "http://localhost:8765"
ANKI_DECK_NAME = "Academic Tutor"
DEFAULT_QUESTIONS_PER_INGEST = 10

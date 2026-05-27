# Academic Tutor — Project Structure

```
Academic-tutor/
├── main.py              CLI entry point
├── config.py            Paths, model name, Anki URL, defaults
├── requirements.txt     Python dependencies
├── STRUCTURE.md         This file
│
├── pdfs/                ← DROP YOUR PDFS HERE
│
├── data/
│   └── tutor.db         SQLite database (auto-created on first run)
│
└── src/
    ├── __init__.py
    ├── database.py      All DB reads/writes and schema
    ├── ingestion.py     PDF → Claude → structured questions
    ├── quiz.py          Interactive quiz loop + Claude answer evaluation
    └── anki.py          AnkiConnect HTTP wrapper
```

## Commands

```bash
# Ingest a PDF (generates 10 questions by default)
python3 main.py ingest pdfs/my-paper.pdf

# Generate more or fewer questions
python3 main.py ingest pdfs/my-paper.pdf -n 15

# See all ingested sources and their IDs
python3 main.py sources

# Quiz across everything
python3 main.py quiz

# Quiz from one source only
python3 main.py quiz --source 1

# Push questions to Anki (Anki must be open with AnkiConnect)
python3 main.py sync

# Your performance stats
python3 main.py stats
```

## How it works

1. **Ingest** — PDF is base64-encoded and sent to Claude, which extracts key
   concepts and generates open-recall questions (no multiple choice).
   Questions and source metadata are saved to SQLite.

2. **Quiz** — Questions are served in priority order: ones you struggle with
   come first (lowest accuracy score). You type a free-text answer, Claude
   scores it 0–10 with detailed feedback, and the result is stored.

3. **Sync** — Questions are pushed to Anki as Basic cards in the
   "Academic Tutor" deck. Performance ratings (Again/Hard/Good/Easy) are
   applied as tags.

4. **Prioritisation** — The quiz query weights questions by
   `1 - (times_correct / times_asked)`, so cards you always get right
   fade to the back and ones you keep missing stay front and centre.

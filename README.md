# Academic Tutor

A personal learning system that turns PDFs into an active recall quiz, tracks your progress over time, and syncs cards to Anki.

Built on [Make It Stick](https://www.goodreads.com/book/show/18770267-make-it-stick) principles: retrieval practice, desirable difficulty, spaced repetition. No multiple choice — you write your answers from memory and Claude evaluates them.

Runs locally on your Mac using your Claude Code Pro plan. No separate API key required.

---

## How it works

1. **Ingest** a PDF → Claude reads it and generates open-recall questions ranked by difficulty
2. **Quiz** → questions are served hardest-first based on your past performance; you type free-text answers; Claude scores them 0–10 with detailed feedback
3. **Track** → every answer is stored in a local SQLite database; your struggle score per question updates automatically
4. **Sync** → push cards to Anki via AnkiConnect with performance-based ease ratings

---

## Setup

**Requirements:**
- Mac with [Claude Code](https://claude.ai/download) installed (Pro plan)
- [Conda](https://docs.conda.io/en/latest/miniconda.html)
- [Anki](https://apps.ankiweb.net) + [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on *(optional — only needed for Anki sync)*

**Install:**

```bash
conda create -n academic-tutor python=3.11 -y
conda activate academic-tutor
pip install -r requirements.txt
```

---

## Usage

```bash
conda activate academic-tutor
cd ~/Desktop/Academic-tutor
```

### Ingest a PDF

Drop PDFs in the `pdfs/` folder, then:

```bash
python main.py ingest pdfs/yourfile.pdf
```

Generates 10 questions by default. Use `-n` to change that:

```bash
python main.py ingest pdfs/yourfile.pdf -n 15
```

### Quiz

```bash
python main.py quiz
```

You'll see an interactive picker:

```
Which PDF do you want to study?

  0  All PDFs (23 questions)
  1  Can a biologist fix a radio?  (10 questions)
  2  Some other paper  (13 questions)

Enter number:
```

Type your answer freely and press Enter twice to submit. Claude scores it 0–10, tells you what you got right, what you missed, and why it matters.

Use `--limit` to cap the session length:

```bash
python main.py quiz --limit 10
```

### Other commands

```bash
python main.py sources    # list all ingested PDFs
python main.py stats      # performance summary + weakest questions
python main.py sync       # push cards to Anki (Anki must be open)
python main.py reset      # wipe the database and start fresh
```

---

## Progress tracking

Everything is stored in `data/tutor.db` (SQLite — stays local, never committed to git).

Questions are prioritised by struggle weight:

| History | Weight |
|---|---|
| Never asked | 1.1 — always near the top |
| Always wrong | 1.0 |
| 50% correct | 0.5 |
| Always correct | 0.1 — fades to the back |

Run `python main.py stats` to see your average score and the questions you struggle with most.

---

## Project structure

```
Academic-tutor/
├── main.py              CLI entry point
├── config.py            Settings (deck name, question count, etc.)
├── requirements.txt
├── pdfs/                Your PDFs go here (gitignored)
├── data/tutor.db        SQLite database (gitignored)
└── src/
    ├── claude_cli.py    Calls Claude via the claude CLI (no API key)
    ├── database.py      All DB reads and writes
    ├── ingestion.py     PDF text extraction + question generation
    ├── quiz.py          Interactive quiz loop + answer evaluation
    └── anki.py          AnkiConnect integration
```

---

## Upgrading to the Anthropic API

Currently uses `claude -p` (Claude Code CLI) so no API key is needed. When you're ready to run it fully standalone, the only file to change is `src/claude_cli.py` — swap the subprocess calls for the [Anthropic Python SDK](https://github.com/anthropic/anthropic-sdk-python).

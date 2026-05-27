from __future__ import annotations
import hashlib
import sys
import os
from pathlib import Path
from typing import Any, Dict

from pypdf import PdfReader

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import DEFAULT_QUESTIONS_PER_INGEST
from src.claude_cli import ask_json


def _extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text and text.strip():
            pages.append(text.strip())
    if not pages:
        raise ValueError("Could not extract any text from this PDF. It may be scanned/image-only.")
    return "\n\n---\n\n".join(pages)


PROMPT_TEMPLATE = """\
You are an expert educator applying principles from "Make It Stick" \
(retrieval practice, desirable difficulty, elaborative interrogation, spaced repetition).

Below is the full text of a document. Analyse it carefully, then generate exactly {n} \
open-recall questions that:
1. Force retrieval from memory — NO multiple choice, NO true/false
2. Target the most important concepts and mechanisms, not surface trivia
3. Mix question styles: "explain why", "describe how", "what would happen if", "compare X and Y"
4. Vary cognitive depth: some direct recall, some analytical, some synthesis
5. Are challenging enough to require real thought (desirable difficulty)

Return ONLY valid JSON — no prose, no markdown fences — exactly this structure:
{{
  "source_title": "<inferred title of the document>",
  "questions": [
    {{
      "concept": "<key concept being tested>",
      "question": "<the open-recall question>",
      "ideal_answer": "<comprehensive model answer — every key point a strong answer must include>",
      "difficulty": <integer 1-5, where 1=basic recall, 5=deep synthesis>
    }}
  ]
}}

Generate exactly {n} questions.

DOCUMENT TEXT:
{text}
"""


def ingest_pdf(filepath: str, num_questions: int = DEFAULT_QUESTIONS_PER_INGEST) -> Dict[str, Any]:
    """
    Extract text from a PDF, send to Claude, return structured question data
    ready for database.save_ingestion().
    """
    path = Path(filepath).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file, got: {path.suffix}")

    pdf_bytes = path.read_bytes()
    content_hash = hashlib.sha256(pdf_bytes).hexdigest()

    text = _extract_pdf_text(path)

    prompt = PROMPT_TEMPLATE.format(n=num_questions, text=text)
    data = ask_json(prompt, timeout=240)

    if "questions" not in data:
        raise ValueError(f"Unexpected response structure — missing 'questions' key.")

    data["content_hash"] = content_hash
    data["filename"] = path.name
    data["filepath"] = str(path)
    return data

from __future__ import annotations
import sys
import os
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from src.claude_cli import ask_json
import src.database as db

console = Console()

EASE_LABEL: Dict[int, str] = {1: "Again", 2: "Hard", 3: "Good", 4: "Easy"}
EASE_COLOR: Dict[int, str] = {1: "red", 2: "yellow", 3: "green", 4: "bright_green"}
SCORE_COLOR: Dict[int, str] = {
    0: "red", 1: "red", 2: "red", 3: "red",
    4: "yellow", 5: "yellow",
    6: "green", 7: "green", 8: "green",
    9: "bright_green", 10: "bright_green",
}

EVAL_PROMPT = """\
You are evaluating a student's open-recall answer for a retrieval practice session.

Question: {question}

Model answer (key points the student should cover): {ideal_answer}

Student's answer: {user_answer}

Return ONLY valid JSON — no prose, no markdown fences:
{{
  "score": <integer 0-10>,
  "feedback": "<2-4 sentences: what was strong, what was missing, why it matters>",
  "correct_elements": ["<point the student got right>"],
  "missing_elements": ["<important point the student missed>"],
  "encouragement": "<one short encouraging sentence>"
}}

Scoring:
 9-10 — comprehensive, precise, shows deep understanding
 7-8  — good coverage, minor gaps or imprecision
 5-6  — partial understanding, notable gaps
 3-4  — basic recall only, missing core concepts
 1-2  — mostly incorrect or very superficial
 0    — blank or entirely off-topic\
"""


def evaluate_answer(question: str, ideal_answer: str, user_answer: str) -> Dict[str, Any]:
    prompt = EVAL_PROMPT.format(
        question=question,
        ideal_answer=ideal_answer,
        user_answer=user_answer,
    )
    return ask_json(prompt, timeout=60)


def score_to_ease(score: int) -> int:
    """Map 0-10 score → Anki ease: 1=Again, 2=Hard, 3=Good, 4=Easy."""
    if score <= 3:
        return 1
    if score <= 5:
        return 2
    if score <= 8:
        return 3
    return 4


def _get_multiline_input() -> str:
    """Collect typed answer; blank line to submit."""
    lines: List[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "" and lines:
            break
        lines.append(line)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _render_evaluation(evaluation: Dict[str, Any], ease: int) -> None:
    score = evaluation["score"]
    color = SCORE_COLOR.get(score, "white")
    ease_color = EASE_COLOR[ease]

    console.print()
    console.rule(
        f"[bold]Score: [{color}]{score}/10[/{color}]   "
        f"Anki: [{ease_color}]{EASE_LABEL[ease]}[/{ease_color}]"
    )
    console.print(f"\n[italic]{evaluation.get('feedback', '')}[/italic]")

    correct = evaluation.get("correct_elements", [])
    missing = evaluation.get("missing_elements", [])

    if correct:
        console.print("\n[green]You covered:[/green]")
        for point in correct:
            console.print(f"  [green]✓[/green] {point}")

    if missing:
        console.print("\n[yellow]You missed:[/yellow]")
        for point in missing:
            console.print(f"  [yellow]○[/yellow] {point}")

    if evaluation.get("encouragement"):
        console.print(f"\n[dim]{evaluation['encouragement']}[/dim]")


def run_quiz_session(source_id: Optional[int] = None, limit: int = 20) -> None:
    db.init_db()
    questions = db.get_questions_for_quiz(source_id=source_id, limit=limit)

    if not questions:
        console.print("[yellow]No questions found. Run `ingest` first.[/yellow]")
        return

    session_id = db.start_session(source_id)
    total = len(questions)
    scores: List[int] = []

    console.print(Panel(
        f"[bold]Starting quiz — {total} question{'s' if total != 1 else ''}[/bold]\n"
        "[dim]Type your answer and press Enter twice to submit. Ctrl-C to quit.[/dim]",
        title="Academic Tutor",
        border_style="cyan",
    ))

    for idx, q in enumerate(questions, 1):
        console.print()
        console.print(Panel(
            f"[bold]{q['question']}[/bold]",
            title=f"[cyan]Q{idx}/{total}[/cyan]  [dim]{q['concept']}[/dim]",
            border_style="cyan",
        ))

        history = db.get_question_history(q["id"])
        if history:
            recent = [str(h["score"]) for h in history[:3]]
            console.print(f"[dim]Recent scores: {', '.join(recent)}[/dim]")

        console.print("[dim]Your answer (blank line to submit):[/dim]")

        try:
            user_answer = _get_multiline_input()
        except KeyboardInterrupt:
            console.print("\n[yellow]Quiz interrupted.[/yellow]")
            break

        if not user_answer.strip():
            console.print("[dim]Skipped.[/dim]")
            continue

        with console.status("[cyan]Evaluating…[/cyan]"):
            try:
                evaluation = evaluate_answer(q["question"], q["ideal_answer"], user_answer)
            except Exception as e:
                console.print(f"[red]Evaluation error: {e}[/red]")
                continue

        ease = score_to_ease(evaluation["score"])
        _render_evaluation(evaluation, ease)
        db.save_answer(session_id, q["id"], user_answer, evaluation, ease)
        scores.append(evaluation["score"])

        console.print("\n[dim]Press Enter to continue…[/dim]")
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            break

    db.end_session(session_id)

    if scores:
        avg = round(sum(scores) / len(scores), 1)
        console.print()
        console.rule("[bold]Session complete[/bold]")
        console.print(f"Questions answered: {len(scores)}/{total}")
        console.print(f"Average score: [bold]{avg}/10[/bold]")

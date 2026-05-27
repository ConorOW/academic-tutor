#!/usr/bin/env python3
"""
Academic Tutor — Claude + SQLite + Anki personal learning system.

Commands:
  ingest <pdf>          Extract concepts and generate recall questions from a PDF
  quiz                  Start an interactive quiz session
  sync                  Push questions to Anki via AnkiConnect
  stats                 Show your performance statistics
  sources               List ingested PDFs
"""
from __future__ import annotations
import argparse
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

import src.database as db
from src.ingestion import ingest_pdf
from src.quiz import run_quiz_session
from src.anki import sync_questions, is_running, tag_note_with_performance
from config import DEFAULT_QUESTIONS_PER_INGEST

console = Console()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_ingest(args: argparse.Namespace) -> None:
    db.init_db()
    n = args.questions
    console.print(Panel(
        f"Ingesting [bold]{args.pdf}[/bold]\nGenerating [bold]{n}[/bold] open-recall questions…",
        border_style="cyan",
    ))
    with console.status("[cyan]Sending PDF to Claude…[/cyan]"):
        try:
            data = ingest_pdf(args.pdf, num_questions=n)
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
            sys.exit(1)
        except Exception as e:
            console.print(f"[red]Ingestion failed: {e}[/red]")
            sys.exit(1)

    source_id = db.save_ingestion(data)

    title = data.get("source_title", data["filename"])
    console.print(f"\n[green]✓[/green] Saved source [bold]#{source_id}[/bold]: {title}")

    table = Table(box=box.SIMPLE, show_header=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Concept", style="bold")
    table.add_column("Question")
    table.add_column("Diff", justify="center", width=4)

    for i, q in enumerate(data["questions"], 1):
        table.add_row(str(i), q["concept"], q["question"][:80], str(q.get("difficulty", "?")))

    console.print(table)
    console.print(f"\nRun [bold]python main.py quiz --source {source_id}[/bold] to start studying.")


def _pick_source() -> int | None:
    """Show an interactive source picker. Returns source_id or None for all."""
    sources = db.get_sources()
    if not sources:
        return None

    console.print("\n[bold]Which PDF do you want to study?[/bold]\n")
    console.print(f"  [cyan]0[/cyan]  All PDFs ({sum(s['question_count'] for s in sources)} questions)")
    for s in sources:
        console.print(f"  [cyan]{s['id']}[/cyan]  {s['title'] or s['filename']}  [dim]({s['question_count']} questions)[/dim]")

    console.print()
    while True:
        raw = input("Enter number: ").strip()
        if raw == "0":
            return None
        try:
            chosen = int(raw)
            if any(s["id"] == chosen for s in sources):
                return chosen
        except ValueError:
            pass
        console.print("[yellow]Please enter one of the numbers above.[/yellow]")


def cmd_quiz(args: argparse.Namespace) -> None:
    db.init_db()
    source_id = _pick_source()
    run_quiz_session(source_id=source_id, limit=args.limit)


def cmd_sync(args: argparse.Namespace) -> None:
    db.init_db()
    if not is_running():
        console.print("[red]Anki is not running or AnkiConnect is not installed.[/red]")
        console.print("Open Anki and ensure the AnkiConnect add-on is active (Tools → Add-ons).")
        sys.exit(1)

    source_id: int | None = args.source
    questions = db.get_all_questions(source_id=source_id)
    unsynced = [q for q in questions if not q.get("anki_note_id")]

    if not unsynced:
        console.print("[green]All questions are already synced to Anki.[/green]")
        return

    console.print(f"Syncing [bold]{len(unsynced)}[/bold] question(s) to Anki…")
    with console.status("[cyan]Talking to AnkiConnect…[/cyan]"):
        results = sync_questions(unsynced)

    added = 0
    for q_id, note_id in results.items():
        if note_id:
            db.update_anki_note_id(q_id, note_id)
            added += 1

    console.print(f"[green]✓[/green] Added {added} new card(s). {len(unsynced) - added} duplicate(s) skipped.")

    # Also tag existing synced cards with their latest performance rating
    if args.ratings:
        _sync_ratings(questions)


def _sync_ratings(questions: list) -> None:
    """Tag Anki notes with the most recent performance rating from DB."""
    synced = [q for q in questions if q.get("anki_note_id")]
    updated = 0
    for q in synced:
        history = db.get_question_history(q["id"])
        if history:
            latest_ease = history[0].get("anki_ease")
            if latest_ease:
                try:
                    tag_note_with_performance(q["anki_note_id"], latest_ease)
                    updated += 1
                except Exception:
                    pass
    if updated:
        console.print(f"[green]✓[/green] Updated performance tags on {updated} note(s).")


def cmd_stats(args: argparse.Namespace) -> None:
    db.init_db()
    stats = db.get_stats()

    console.print(Panel(
        f"Total questions: [bold]{stats['total_questions']}[/bold]\n"
        f"Total answers:   [bold]{stats['total_answers']}[/bold]\n"
        f"Average score:   [bold]{stats['avg_score'] or '—'}/10[/bold]",
        title="Your Performance",
        border_style="cyan",
    ))

    if stats["struggling"]:
        console.print("\n[bold yellow]Questions you struggle with most:[/bold yellow]")
        table = Table(box=box.SIMPLE)
        table.add_column("Concept")
        table.add_column("Question")
        table.add_column("Accuracy", justify="right")
        for row in stats["struggling"]:
            table.add_row(
                row["concept"],
                row["question"][:60],
                f"{row['accuracy_pct']}%",
            )
        console.print(table)


def cmd_reset(args: argparse.Namespace) -> None:
    from config import DB_PATH
    if not args.yes:
        confirm = input("This will delete all sources, questions, and answers. Type YES to confirm: ")
        if confirm.strip() != "YES":
            console.print("[yellow]Cancelled.[/yellow]")
            return
    if DB_PATH.exists():
        DB_PATH.unlink()
    db.init_db()
    console.print("[green]✓[/green] Database wiped and reset. Ready to ingest fresh PDFs.")


def cmd_sources(args: argparse.Namespace) -> None:
    db.init_db()
    sources = db.get_sources()
    if not sources:
        console.print("[yellow]No PDFs ingested yet. Run `ingest <pdf>` first.[/yellow]")
        return

    table = Table(box=box.SIMPLE, show_header=True)
    table.add_column("ID", width=4)
    table.add_column("Title")
    table.add_column("File")
    table.add_column("Questions", justify="right")
    table.add_column("Ingested")

    for s in sources:
        table.add_row(
            str(s["id"]),
            s.get("title") or s["filename"],
            s["filename"],
            str(s["question_count"]),
            s["created_at"][:10],
        )
    console.print(table)


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Academic Tutor — PDF → questions → quiz → Anki",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ingest
    p_ingest = sub.add_parser("ingest", help="Ingest a PDF and generate questions")
    p_ingest.add_argument("pdf", help="Path to the PDF file")
    p_ingest.add_argument(
        "-n", "--questions",
        type=int,
        default=DEFAULT_QUESTIONS_PER_INGEST,
        help=f"Number of questions to generate (default {DEFAULT_QUESTIONS_PER_INGEST})",
    )

    # quiz
    p_quiz = sub.add_parser("quiz", help="Start an interactive quiz session")
    p_quiz.add_argument("--limit", type=int, default=20, help="Max questions per session (default 20)")

    # sync
    p_sync = sub.add_parser("sync", help="Sync questions to Anki via AnkiConnect")
    p_sync.add_argument("--source", type=int, default=None, help="Limit to a specific source ID")
    p_sync.add_argument("--ratings", action="store_true", help="Also tag notes with performance ratings")

    # stats
    sub.add_parser("stats", help="Show performance statistics")

    # sources
    sub.add_parser("sources", help="List ingested PDFs")

    # reset
    p_reset = sub.add_parser("reset", help="Wipe the database and start fresh")
    p_reset.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "ingest": cmd_ingest,
        "quiz": cmd_quiz,
        "sync": cmd_sync,
        "stats": cmd_stats,
        "sources": cmd_sources,
        "reset": cmd_reset,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()

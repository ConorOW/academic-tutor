from __future__ import annotations
import json
import re
import subprocess
from typing import Any


def ask(prompt: str, timeout: int = 180) -> str:
    """
    Send a prompt to Claude via the CLI and return the raw text response.
    Uses your Claude Code Pro plan — no API key needed.
    """
    result = subprocess.run(
        ["claude", "-p", "--output-format", "text", "--no-session-persistence"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI failed: {result.stderr.strip()}")
    return result.stdout.strip()


def ask_json(prompt: str, timeout: int = 180) -> Any:
    """Ask Claude for a JSON response and parse it."""
    raw = ask(prompt, timeout=timeout)
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw.strip())

"""Tiny .env loader (no dependency) plus the settings the analyzer needs."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env(path=ROOT / ".env"):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()


def llm_provider():
    """'claude' or 'mock'. OBSERVER_LLM=auto uses Claude only when an API key is present."""
    choice = os.environ.get("OBSERVER_LLM", "auto").lower()
    if choice == "auto":
        return "claude" if os.environ.get("ANTHROPIC_API_KEY") else "mock"
    return choice


def model_name():
    return os.environ.get("OBSERVER_MODEL", "claude-haiku-5-5")

"""Общие константы и мелкие помощники."""
from datetime import date

KINDS = ("movie", "series", "anime", "other")
STATUSES = ("planned", "watching", "completed", "dropped")


def today() -> str:
    return date.today().isoformat()

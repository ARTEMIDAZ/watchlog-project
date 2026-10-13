"""Настройки из переменных окружения.

Это функции, а не константы: значения читаются в момент вызова,
поэтому их легко подменять в тестах и в docker-compose.
"""
import os
from pathlib import Path


def db_path() -> Path:
    default = Path.home() / ".watchlog" / "watch.db"
    return Path(os.environ.get("WATCH_DB", default))


def tmdb_key() -> str:
    """Ключ TMDB: либо v3 API Key, либо v4 API Read Access Token."""
    return os.environ.get("TMDB_API_KEY", "").strip()


def lang() -> str:
    """Язык, на котором TMDB отдаёт названия."""
    return os.environ.get("WATCH_LANG", "ru-RU")

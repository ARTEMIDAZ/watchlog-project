"""Вывод в терминал: цвета и таблицы без внешних библиотек."""
import os
import sys
import unicodedata
from typing import Dict, List, Optional, Sequence

ANSI = {"cyan": "36", "yellow": "33", "green": "32", "red": "31", "bold": "1", "dim": "2"}
STATUS_COLOR = {"planned": "cyan", "watching": "yellow", "completed": "green", "dropped": "red"}


def use_color() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def paint(text: str, color: Optional[str]) -> str:
    if not color or color not in ANSI or not use_color():
        return text
    return f"\033[{ANSI[color]}m{text}\033[0m"


def fail(msg: str, code: int = 1):
    print(paint(msg, "red"), file=sys.stderr)
    raise SystemExit(code)


def warn(msg: str) -> None:
    print(paint(msg, "yellow"), file=sys.stderr)


def display_width(text: str) -> int:
    """Ширина строки в ячейках терминала (иероглифы занимают две)."""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int, align: str) -> str:
    gap = " " * (width - display_width(text))
    return gap + text if align == "r" else text + gap


def print_table(
    headers: Sequence[str],
    rows: List[List[str]],
    align: str = "",
    colors: Optional[List[Dict[int, str]]] = None,
) -> None:
    """align — строка из 'l'/'r' по числу столбцов; colors — {столбец: цвет} для каждой строки."""
    align = align.ljust(len(headers), "l")
    widths = [display_width(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], display_width(cell))
    print("  ".join(paint(_pad(h, widths[i], align[i]), "bold") for i, h in enumerate(headers)))
    print("  ".join("─" * w for w in widths))
    for ri, row in enumerate(rows):
        cells = []
        for i, cell in enumerate(row):
            padded = _pad(cell, widths[i], align[i])
            color = colors[ri].get(i) if colors else None
            cells.append(paint(padded, color) if color else padded)
        print("  ".join(cells))

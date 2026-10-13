"""Командная строка: разбор аргументов и обработчики команд."""
import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import List, Optional

from . import __version__, db, providers, repo
from .models import KINDS, STATUSES
from .providers import Meta, ProviderError
from .ui import STATUS_COLOR, fail, paint, print_table, warn

# ───────────────────────── помощники ─────────────────────────


def rating_type(value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("оценка должна быть числом от 1 до 10")
    if not 1 <= n <= 10:
        raise argparse.ArgumentTypeError("оценка должна быть от 1 до 10")
    return n


def get_or_fail(conn, item_id: int):
    item = repo.get_item(conn, item_id)
    if item is None:
        fail(f"Запись #{item_id} не найдена.")
    return item


def fmt_progress(r) -> str:
    if r["type"] == "movie":
        return "—"
    if r["total"]:
        return f"{r['progress']}/{r['total']}"
    return str(r["progress"]) if r["progress"] else "—"


def print_results(results: List[Meta]) -> None:
    rows = [
        [
            str(i),
            m.title,
            m.original_title if m.original_title and m.original_title != m.title else "",
            m.kind,
            str(m.year or "—"),
            str(m.total or "—"),
            m.ext_id,
        ]
        for i, m in enumerate(results, 1)
    ]
    print_table(["#", "Название", "Оригинал", "Тип", "Год", "Серий", "ID"], rows, align="rlllrrl")


def pick_meta(query: str, kind: Optional[str], source: Optional[str], pick: Optional[int]) -> Optional[Meta]:
    """Ищет тайтл онлайн и даёт выбрать нужный. None — добавить без онлайн-данных."""
    try:
        results, warnings = providers.search(query, kind, source)
    except ProviderError as e:
        warn(f"Онлайн-поиск не удался: {e}")
        return None
    for w in warnings:
        warn(w)
    if not results:
        print(paint("Онлайн ничего не нашлось.", "dim"))
        return None

    chosen = _choose_result(results, pick)
    return providers.enrich(chosen) if chosen else None


def _choose_result(results: List[Meta], pick: Optional[int]) -> Optional[Meta]:
    if pick is not None:
        if pick == 0:
            return None
        if not 1 <= pick <= len(results):
            fail(f"--pick: номер должен быть от 0 до {len(results)}")
        return results[pick - 1]

    if not sys.stdin.isatty():
        fail("Для выбора результата в неинтерактивном режиме укажите --pick N (0 — без онлайн-данных).", 2)
    print_results(results)
    while True:
        try:
            answer = input("Номер результата [1], 0 — без онлайн-данных: ").strip()
        except EOFError:
            return None
        if answer == "":
            return results[0]
        if answer.isdigit() and 0 <= int(answer) <= len(results):
            n = int(answer)
            return results[n - 1] if n else None
        print("Введите число из списка.")


# ───────────────────────── команды ─────────────────────────


def cmd_add(conn, a):
    meta = None
    if a.lookup or a.source:
        meta = pick_meta(a.title, a.type, a.source, a.pick)
    kind = a.type or (meta.kind if meta else "movie")
    title = meta.title if meta else a.title
    total = a.total if a.total is not None else (meta.total if meta else None)
    item_id = repo.add_item(
        conn,
        title=title,
        type=kind,
        status=a.status,
        rating=a.rating,
        total=total,
        notes=a.notes,
        external_id=meta.ext_id if meta else None,
        year=meta.year if meta else None,
        original_title=meta.original_title if meta else None,
    )
    extra = f", {meta.year}" if meta and meta.year else ""
    print(f"{paint('Добавлено:', 'green')} #{item_id} {title} ({kind}, {a.status}{extra})")


def cmd_search(conn, a):
    try:
        results, warnings = providers.search(a.query, a.type, a.source)
    except ProviderError as e:
        fail(f"Онлайн-поиск не удался: {e}")
    for w in warnings:
        warn(w)
    if not results:
        print(paint("Ничего не найдено.", "dim"))
        return
    print_results(results)


def cmd_link(conn, a):
    item = get_or_fail(conn, a.id)
    meta = pick_meta(item["title"], item["type"], a.source, a.pick)
    if meta is None:
        print("Связь не создана.")
        return
    changes = repo.apply_meta(conn, item, meta)
    print(f"{paint('Связано:', 'green')} #{item['id']} {item['title']} ↔ {meta.ext_id}")
    for field, (old, new) in changes.items():
        if field != "external_id":
            print(f"  {field}: {old or '—'} → {new}")


def cmd_refresh(conn, a):
    if a.id is not None:
        items = [get_or_fail(conn, a.id)]
    elif a.all:
        items = [
            r for r in repo.list_items(conn)
            if r["external_id"] and r["status"] in ("planned", "watching")
        ]
    else:
        fail("Укажите ID записи или --all.", 2)
    if not items:
        print("Нечего обновлять.")
        return 0

    errors = 0
    for n, item in enumerate(items):
        if not item["external_id"]:
            warn(f"#{item['id']} {item['title']}: нет связи с онлайн-базой (см. команду link)")
            continue
        if n:
            time.sleep(0.25)  # лимит Shikimori — 5 запросов в секунду
        try:
            meta = providers.details(item["external_id"])
        except ProviderError as e:
            warn(f"#{item['id']} {item['title']}: {e}")
            errors += 1
            continue
        changes = repo.apply_meta(conn, item, meta)
        if "total" in changes:
            old, new = changes["total"]
            print(f"#{item['id']} {item['title']}: серий {old or '?'} → {new}")
        else:
            print(f"#{item['id']} {item['title']}: без изменений")
    return 1 if errors else 0


def cmd_list(conn, a):
    items = repo.list_items(conn, a.status, a.type, a.search, a.sort)
    if not items:
        print(paint("Ничего не найдено.", "dim"))
        return
    rows = [
        [
            str(r["id"]),
            r["title"],
            r["type"],
            str(r["year"] or "—"),
            r["status"],
            fmt_progress(r),
            str(r["rating"]) if r["rating"] else "—",
            r["finished_at"] or "—",
        ]
        for r in items
    ]
    colors = [{4: STATUS_COLOR[r["status"]]} for r in items]
    print_table(
        ["ID", "Название", "Тип", "Год", "Статус", "Прогресс", "Оценка", "Завершено"],
        rows,
        align="rllrlrrl",
        colors=colors,
    )


def cmd_show(conn, a):
    r = get_or_fail(conn, a.id)
    print(paint(f"#{r['id']} {r['title']}", "bold"))
    if r["original_title"] and r["original_title"] != r["title"]:
        print(f"Оригинал: {r['original_title']}")
    print(f"Тип: {r['type']}   Год: {r['year'] or '—'}   Статус: {paint(r['status'], STATUS_COLOR[r['status']])}")
    print(f"Прогресс: {fmt_progress(r)}   Оценка: {r['rating'] or '—'}")
    print(f"Начато: {r['started_at'] or '—'}   Завершено: {r['finished_at'] or '—'}")
    if r["notes"]:
        print(f"Заметка: {r['notes']}")
    if r["external_id"]:
        link = providers.url_for(r["external_id"])
        print(f"Источник: {r['external_id']}" + (f"  {link}" if link else ""))


def cmd_progress(conn, a):
    if a.ep < 0:
        fail("Номер серии не может быть отрицательным.")
    item = get_or_fail(conn, a.id)
    if repo.set_progress(conn, item, a.ep):
        print(f"{paint('Досмотрено:', 'green')} {item['title']}. Поставьте оценку: watch rate {a.id} 9")
    else:
        tail = f" из {item['total']}" if item["total"] else ""
        print(f"{paint(item['title'], 'yellow')}: серия {a.ep}{tail}")


def cmd_done(conn, a):
    item = get_or_fail(conn, a.id)
    repo.mark_done(conn, a.id, a.rating)
    print(f"{paint('Готово:', 'green')} {item['title']}" + (f" — {a.rating}/10" if a.rating else ""))


def cmd_rate(conn, a):
    item = get_or_fail(conn, a.id)
    repo.set_rating(conn, a.id, a.rating)
    print(f"{item['title']}: оценка {a.rating}/10")


def cmd_drop(conn, a):
    item = get_or_fail(conn, a.id)
    repo.set_status(conn, a.id, "dropped")
    print(f"{paint('Брошено:', 'red')} {item['title']}")


def cmd_edit(conn, a):
    item = get_or_fail(conn, a.id)
    repo.edit_item(conn, item, a.title, a.type, a.total, a.notes)
    print(f"{paint('Обновлено:', 'green')} #{a.id}")


def cmd_rm(conn, a):
    item = get_or_fail(conn, a.id)
    if not a.yes:
        try:
            answer = input(f"Удалить «{item['title']}»? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes", "д", "да"):
            print("Отменено.")
            return
    repo.delete_item(conn, a.id)
    print(f"Удалено: {item['title']}")


def cmd_stats(conn, a):
    done = repo.completed_rows(conn, a.year)
    print(paint(f"Статистика{f' за {a.year}' if a.year else ''}", "bold"))
    if not a.year:
        counts = repo.status_counts(conn)
        if counts:
            print("По статусам: " + ", ".join(f"{r['status']} — {r['c']}" for r in counts))
        else:
            print("Пока пусто.")
    if not done:
        print(paint("Завершённых записей нет.", "dim"))
        return
    rows = []
    for kind in sorted({r["type"] for r in done}):
        items = [r for r in done if r["type"] == kind]
        rated = [r["rating"] for r in items if r["rating"]]
        avg = f"{sum(rated) / len(rated):.1f}" if rated else "—"
        rows.append([kind, str(len(items)), avg])
    print()
    print_table(["Тип", "Завершено", "Ср. оценка"], rows, align="lrr")
    rated_all = [r for r in done if r["rating"]]
    if rated_all:
        best = max(rated_all, key=lambda r: r["rating"])
        print(f"\nЛучшее: {best['title']} ({best['rating']}/10)")


def cmd_export(conn, a):
    rows = repo.all_items(conn)
    path = Path(a.path)
    suffix = path.suffix.lower()
    if suffix == ".json":
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    elif suffix == ".csv":
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["id"])
            writer.writeheader()
            writer.writerows(rows)
    else:
        fail("Расширение файла должно быть .csv или .json")
    print(f"Экспортировано записей: {len(rows)} → {path}")


# ───────────────────────── разбор аргументов ─────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="watch",
        description="Личный трекер просмотренного: фильмы, сериалы, аниме и всё остальное.",
    )
    p.add_argument("--version", action="version", version=f"watchlog {__version__}")
    sub = p.add_subparsers(dest="command", metavar="КОМАНДА")
    sub.required = True

    def add_cmd(name, func, help_text):
        sp = sub.add_parser(name, help=help_text, description=help_text)
        sp.set_defaults(func=func)
        return sp

    def online_options(sp):
        sp.add_argument("--source", choices=sorted(providers.PROVIDERS), help="Источник: tmdb или shikimori")
        sp.add_argument("--pick", type=int, metavar="N", help="Взять N-й результат без вопросов (0 — без онлайн-данных)")

    sp = add_cmd("add", cmd_add, "Добавить запись (с -l — подтянуть данные из TMDB/Shikimori)")
    sp.add_argument("title", help="Название")
    sp.add_argument("-t", "--type", choices=KINDS, help="Тип (по умолчанию movie или как у найденного)")
    sp.add_argument("-s", "--status", choices=STATUSES, default="planned", help="Статус (по умолчанию planned)")
    sp.add_argument("--total", type=int, help="Всего серий/эпизодов")
    sp.add_argument("-r", "--rating", type=rating_type, help="Оценка 1–10")
    sp.add_argument("-n", "--notes", help="Заметка")
    sp.add_argument("-l", "--lookup", action="store_true", help="Найти тайтл онлайн и заполнить данные")
    online_options(sp)

    sp = add_cmd("search", cmd_search, "Найти тайтл онлайн, ничего не сохраняя")
    sp.add_argument("query", help="Что искать")
    sp.add_argument("-t", "--type", choices=KINDS, help="Подсказка по типу: anime → Shikimori, movie/series → TMDB")
    sp.add_argument("--source", choices=sorted(providers.PROVIDERS), help="Источник: tmdb или shikimori")

    sp = add_cmd("link", cmd_link, "Привязать существующую запись к онлайн-базе")
    sp.add_argument("id", type=int)
    online_options(sp)

    sp = add_cmd("refresh", cmd_refresh, "Обновить число серий и данные из онлайн-базы")
    sp.add_argument("id", type=int, nargs="?", help="ID записи")
    sp.add_argument("--all", action="store_true", help="Все запланированные и текущие записи со связью")

    sp = add_cmd("list", cmd_list, "Показать список с фильтрами")
    sp.add_argument("-s", "--status", choices=STATUSES)
    sp.add_argument("-t", "--type", choices=KINDS)
    sp.add_argument("-q", "--search", help="Поиск по названию")
    sp.add_argument("--sort", choices=sorted(repo.SORTS), default="id")

    sp = add_cmd("show", cmd_show, "Подробности о записи")
    sp.add_argument("id", type=int)

    sp = add_cmd("progress", cmd_progress, "Обновить прогресс (серию)")
    sp.add_argument("id", type=int)
    sp.add_argument("-e", "--ep", type=int, required=True, help="Номер последней просмотренной серии")

    sp = add_cmd("done", cmd_done, "Отметить как просмотренное")
    sp.add_argument("id", type=int)
    sp.add_argument("-r", "--rating", type=rating_type, help="Оценка 1–10")

    sp = add_cmd("rate", cmd_rate, "Поставить или изменить оценку")
    sp.add_argument("id", type=int)
    sp.add_argument("rating", type=rating_type)

    sp = add_cmd("drop", cmd_drop, "Бросить просмотр")
    sp.add_argument("id", type=int)

    sp = add_cmd("edit", cmd_edit, "Изменить название, тип, число серий или заметку")
    sp.add_argument("id", type=int)
    sp.add_argument("--title")
    sp.add_argument("-t", "--type", choices=KINDS)
    sp.add_argument("--total", type=int)
    sp.add_argument("-n", "--notes")

    sp = add_cmd("rm", cmd_rm, "Удалить запись")
    sp.add_argument("id", type=int)
    sp.add_argument("-y", "--yes", action="store_true", help="Не спрашивать подтверждение")

    sp = add_cmd("stats", cmd_stats, "Статистика")
    sp.add_argument("-y", "--year", type=int, help="Только завершённое в этом году")

    sp = add_cmd("export", cmd_export, "Экспорт всех записей в CSV или JSON")
    sp.add_argument("path", help="Куда сохранить: *.csv или *.json")

    return p


def main(argv: Optional[List[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    args = build_parser().parse_args(argv)
    conn = db.connect()
    try:
        return args.func(conn, args) or 0
    except ProviderError as e:
        fail(f"Ошибка онлайн-базы: {e}")
    except KeyboardInterrupt:
        print()
        return 130
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

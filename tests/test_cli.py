import contextlib
import io
import os
import sqlite3
import unittest
from unittest import mock

from tests import mock_server
from tests.base import MockedApiTestCase
from watchlog import cli


def run(*args):
    """Запускает команду в этом же процессе. Возвращает (код, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(list(args))
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return code, out.getvalue(), err.getvalue()


class CliBasicTests(MockedApiTestCase):
    def test_add_list_progress_done_flow(self):
        self.assertEqual(run("add", "Вручную", "-t", "anime", "--total", "3")[0], 0)
        run("progress", "1", "--ep", "2")
        code, out, _ = run("show", "1")
        self.assertIn("2/3", out)
        code, out, _ = run("progress", "1", "--ep", "3")
        self.assertIn("Досмотрено", out)
        code, out, _ = run("list", "-s", "completed")
        self.assertIn("Вручную", out)
        self.assertIn("3/3", out)

    def test_search_in_list_ignores_case_for_cyrillic(self):
        run("add", "Дюна 2")
        _, out, _ = run("list", "-q", "ДЮНА")
        self.assertIn("Дюна 2", out)

    def test_rating_validation(self):
        run("add", "Фильм")
        self.assertEqual(run("rate", "1", "11")[0], 2)
        self.assertEqual(run("rate", "1", "7")[0], 0)

    def test_missing_item(self):
        self.assertEqual(run("show", "99")[0], 1)

    def test_old_database_is_migrated(self):
        path = os.environ["WATCH_DB"]
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, "
            "type TEXT NOT NULL DEFAULT 'movie', status TEXT NOT NULL DEFAULT 'planned', "
            "rating INTEGER, progress INTEGER NOT NULL DEFAULT 0, total INTEGER, started_at TEXT, "
            "finished_at TEXT, notes TEXT, external_id TEXT, created_at TEXT NOT NULL DEFAULT (date('now')))"
        )
        conn.execute("INSERT INTO items (title) VALUES ('Старая запись')")
        conn.commit()
        conn.close()
        code, out, _ = run("list")
        self.assertEqual(code, 0)
        self.assertIn("Старая запись", out)
        conn = sqlite3.connect(path)
        columns = {r[1] for r in conn.execute("PRAGMA table_info(items)")}
        conn.close()
        self.assertLessEqual({"year", "original_title"}, columns)


class CliOnlineTests(MockedApiTestCase):
    def test_add_lookup_anime_fills_everything(self):
        code, out, _ = run("add", "fullmetal", "-t", "anime", "-l", "--pick", "1")
        self.assertEqual(code, 0)
        self.assertIn("Стальной алхимик: Братство", out)
        _, out, _ = run("show", "1")
        self.assertIn("Fullmetal Alchemist: Brotherhood", out)
        self.assertIn("0/64", out)
        self.assertIn("shikimori:5114", out)
        self.assertIn("2009", out)

    def test_add_lookup_series_via_tmdb(self):
        run("add", "breaking bad", "-t", "series", "-l", "--pick", "1")
        _, out, _ = run("list")
        self.assertIn("Во все тяжкие", out)
        self.assertIn("0/62", out)

    def test_tmdb_series_total_comes_from_details_request(self):
        run("add", "breaking bad", "-t", "series", "-l", "--pick", "1")
        paths = [r["path"] for r in mock_server.STATE["requests"]]
        self.assertEqual(paths, ["/3/search/tv", "/3/tv/1396"])

    def test_movie_lookup_makes_no_extra_request(self):
        run("add", "матрица", "-t", "movie", "-l", "--pick", "1")
        paths = [r["path"] for r in mock_server.STATE["requests"]]
        self.assertEqual(paths, ["/3/search/movie"])

    def test_failed_details_request_keeps_basic_data(self):
        with mock.patch("watchlog.providers.details", side_effect=cli.ProviderError("сбой")):
            code, _, _ = run("add", "breaking bad", "-t", "series", "-l", "--pick", "1")
        self.assertEqual(code, 0)
        _, out, _ = run("list")
        self.assertIn("Во все тяжкие", out)
        self.assertIn("2008", out)

    def test_explicit_total_beats_online_total(self):
        run("add", "fullmetal", "-t", "anime", "-l", "--pick", "1", "--total", "10")
        _, out, _ = run("show", "1")
        self.assertIn("0/10", out)

    def test_type_is_taken_from_result_when_not_given(self):
        run("add", "fullmetal", "--source", "shikimori", "--pick", "1")
        _, out, _ = run("list")
        self.assertIn("anime", out)

    def test_pick_zero_adds_as_typed(self):
        run("add", "Моё название", "-l", "--pick", "0")
        _, out, _ = run("list")
        self.assertIn("Моё название", out)
        self.assertNotIn("shikimori", out)

    def test_pick_out_of_range(self):
        self.assertEqual(run("add", "fullmetal", "-t", "anime", "-l", "--pick", "5")[0], 1)

    def test_noninteractive_without_pick_is_refused(self):
        with mock.patch("sys.stdin") as stdin:
            stdin.isatty.return_value = False
            code, _, err = run("add", "fullmetal", "-t", "anime", "-l")
        self.assertEqual(code, 2)
        self.assertIn("--pick", err)

    def test_lookup_failure_still_adds_item(self):
        with mock.patch.dict(os.environ, {"SHIKIMORI_URL": "http://127.0.0.1:1"}):
            code, out, err = run("add", "Без сети", "-t", "anime", "-l", "--pick", "1")
        self.assertEqual(code, 0)
        self.assertIn("Онлайн-поиск не удался", err)
        _, out, _ = run("list")
        self.assertIn("Без сети", out)

    def test_search_command_does_not_save(self):
        code, out, _ = run("search", "матрица", "-t", "movie")
        self.assertEqual(code, 0)
        self.assertIn("The Matrix", out)
        self.assertIn("tmdb:movie:603", out)
        self.assertIn("Ничего не найдено", run("list")[1])

    def test_search_without_key_explains_what_to_do(self):
        with mock.patch.dict(os.environ, {"TMDB_API_KEY": ""}):
            code, _, err = run("search", "матрица", "-t", "movie")
        self.assertEqual(code, 1)
        self.assertIn("TMDB_API_KEY", err)

    def test_refresh_updates_episode_count(self):
        run("add", "ongoing show", "-t", "anime", "-l", "--pick", "1")
        _, out, _ = run("show", "1")
        self.assertIn("0", out)
        mock_server.STATE["ongoing_episodes"] = 24
        code, out, _ = run("refresh", "1")
        self.assertEqual(code, 0)
        self.assertIn("? → 24", out)
        self.assertIn("0/24", run("show", "1")[1])
        self.assertIn("без изменений", run("refresh", "1")[1])

    def test_refresh_all_skips_completed_and_unlinked(self):
        run("add", "ongoing show", "-t", "anime", "-l", "--pick", "1")
        run("add", "Без связи")
        run("add", "fullmetal", "-t", "anime", "-l", "--pick", "1", "-s", "completed")
        mock_server.STATE["requests"].clear()
        mock_server.STATE["ongoing_episodes"] = 12
        code, out, _ = run("refresh", "--all")
        self.assertEqual(code, 0)
        self.assertEqual(len(mock_server.STATE["requests"]), 1)
        self.assertIn("? → 12", out)

    def test_refresh_requires_target(self):
        self.assertEqual(run("refresh")[0], 2)

    def test_refresh_reports_network_error_in_exit_code(self):
        run("add", "ongoing show", "-t", "anime", "-l", "--pick", "1")
        with mock.patch.dict(os.environ, {"SHIKIMORI_URL": "http://127.0.0.1:1"}):
            code, _, err = run("refresh", "1")
        self.assertEqual(code, 1)
        self.assertIn("нет соединения", err)

    def test_link_existing_item_keeps_title_and_progress(self):
        run("add", "fullmetal", "-t", "anime", "--total", "64", "-s", "watching")
        run("progress", "1", "--ep", "10")
        code, out, _ = run("link", "1", "--pick", "1")
        self.assertEqual(code, 0)
        _, out, _ = run("show", "1")
        self.assertIn("#1 fullmetal", out)          # своё название не затёрто
        self.assertIn("10/64", out)                 # прогресс на месте
        self.assertIn("Fullmetal Alchemist: Brotherhood", out)
        self.assertIn("shikimori:5114", out)


if __name__ == "__main__":
    unittest.main()

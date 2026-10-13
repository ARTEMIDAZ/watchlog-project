import os
import unittest
from unittest import mock

from tests import mock_server
from tests.base import MockedApiTestCase
from watchlog import providers
from watchlog.providers import ProviderError
from watchlog.providers.shikimori import Shikimori
from watchlog.providers.tmdb import TMDB


class TmdbTests(MockedApiTestCase):
    def test_search_movie(self):
        results = TMDB().search("матрица", "movie")
        self.assertEqual(len(results), 1)
        m = results[0]
        self.assertEqual((m.title, m.original_title, m.kind, m.year), ("Матрица", "The Matrix", "movie", 1999))
        self.assertEqual(m.ext_id, "tmdb:movie:603")

    def test_search_sends_key_and_language(self):
        TMDB().search("matrix", "movie")
        req = mock_server.STATE["requests"][-1]
        self.assertEqual(req["query"]["api_key"], [mock_server.TMDB_KEY])
        self.assertEqual(req["query"]["language"], ["ru-RU"])
        self.assertEqual(req["query"]["query"], ["matrix"])

    def test_multi_search_skips_people(self):
        results = TMDB().search("что-то")
        self.assertEqual([m.ext_id for m in results], ["tmdb:movie:603", "tmdb:tv:1396"])

    def test_tv_details_have_episode_count(self):
        meta = TMDB().details("tmdb:tv:1396")
        self.assertEqual(meta.total, 62)
        self.assertEqual(meta.kind, "series")
        self.assertEqual(meta.year, 2008)

    def test_long_token_goes_to_bearer_header(self):
        with mock.patch.dict(os.environ, {"TMDB_API_KEY": mock_server.TMDB_TOKEN}):
            TMDB().search("matrix", "movie")
        req = mock_server.STATE["requests"][-1]
        self.assertNotIn("api_key", req["query"])
        self.assertEqual(req["headers"]["Authorization"], f"Bearer {mock_server.TMDB_TOKEN}")

    def test_wrong_key_gives_readable_error(self):
        with mock.patch.dict(os.environ, {"TMDB_API_KEY": "wrong"}):
            with self.assertRaises(ProviderError) as ctx:
                TMDB().search("matrix", "movie")
        self.assertIn("401", str(ctx.exception))
        self.assertFalse(ctx.exception.network)

    def test_missing_key(self):
        with mock.patch.dict(os.environ, {"TMDB_API_KEY": ""}):
            self.assertFalse(TMDB().configured())
            with self.assertRaises(ProviderError) as ctx:
                TMDB().search("matrix", "movie")
        self.assertIn("TMDB_API_KEY", str(ctx.exception))

    def test_bad_ext_id(self):
        with self.assertRaises(ProviderError):
            TMDB().details("tmdb:person:1")


class ShikimoriTests(MockedApiTestCase):
    def test_search_maps_fields(self):
        m = Shikimori().search("fullmetal")[0]
        self.assertEqual(m.ext_id, "shikimori:5114")
        self.assertEqual(m.title, "Стальной алхимик: Братство")
        self.assertEqual(m.original_title, "Fullmetal Alchemist: Brotherhood")
        self.assertEqual((m.kind, m.year, m.total), ("anime", 2009, 64))

    def test_sends_user_agent(self):
        Shikimori().search("fullmetal")
        self.assertIn("watchlog", mock_server.STATE["requests"][-1]["headers"]["User-Agent"])

    def test_unknown_episode_count_becomes_none(self):
        m = Shikimori().details("shikimori:777")
        self.assertIsNone(m.total)
        mock_server.STATE["ongoing_episodes"] = 24
        self.assertEqual(Shikimori().details("shikimori:777").total, 24)

    def test_falls_back_to_second_host_when_first_is_down(self):
        live = f"http://127.0.0.1:{self.port}"
        with mock.patch.object(Shikimori, "hosts", staticmethod(lambda: ["http://127.0.0.1:1", live])):
            self.assertEqual(Shikimori().search("fullmetal")[0].ext_id, "shikimori:5114")

    def test_network_failure_is_flagged(self):
        with mock.patch.dict(os.environ, {"SHIKIMORI_URL": "http://127.0.0.1:1"}):
            with self.assertRaises(ProviderError) as ctx:
                Shikimori().search("fullmetal")
        self.assertTrue(ctx.exception.network)

    def test_not_found(self):
        with self.assertRaises(ProviderError) as ctx:
            Shikimori().details("shikimori:999999")
        self.assertIn("404", str(ctx.exception))


class RoutingTests(MockedApiTestCase):
    def test_anime_goes_only_to_shikimori(self):
        results, _ = providers.search("fullmetal", kind="anime")
        self.assertEqual({m.source for m in results}, {"shikimori"})
        self.assertTrue(all(r["path"].startswith("/api/") for r in mock_server.STATE["requests"]))

    def test_movie_goes_only_to_tmdb(self):
        results, _ = providers.search("матрица", kind="movie")
        self.assertEqual({m.source for m in results}, {"tmdb"})

    def test_without_type_both_are_searched(self):
        results, warnings = providers.search("что-то")
        self.assertEqual({m.source for m in results}, {"tmdb", "shikimori"})
        self.assertEqual(warnings, [])

    def test_without_type_and_without_key_still_finds_anime(self):
        with mock.patch.dict(os.environ, {"TMDB_API_KEY": ""}):
            results, warnings = providers.search("fullmetal")
        self.assertEqual({m.source for m in results}, {"shikimori"})
        self.assertEqual(len(warnings), 1)
        self.assertIn("TMDB_API_KEY", warnings[0])

    def test_movie_without_key_raises(self):
        with mock.patch.dict(os.environ, {"TMDB_API_KEY": ""}):
            with self.assertRaises(ProviderError):
                providers.search("матрица", kind="movie")

    def test_unknown_source(self):
        with self.assertRaises(ProviderError):
            providers.search("x", source="imdb")

    def test_url_for(self):
        self.assertEqual(providers.url_for("tmdb:tv:1396"), "https://www.themoviedb.org/tv/1396")
        self.assertTrue(providers.url_for("shikimori:5114").endswith("/animes/5114"))
        self.assertIsNone(providers.url_for("garbage"))


if __name__ == "__main__":
    unittest.main()

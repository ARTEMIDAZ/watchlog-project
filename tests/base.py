import os
import tempfile
import unittest
from unittest import mock

from tests import mock_server


class MockedApiTestCase(unittest.TestCase):
    """Поднимает поддельные TMDB и Shikimori и временную базу."""

    @classmethod
    def setUpClass(cls):
        cls.server = mock_server.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = f"http://127.0.0.1:{self.port}"
        patcher = mock.patch.dict(os.environ, {
            "WATCH_DB": os.path.join(self.tmp.name, "watch.db"),
            "TMDB_API_KEY": mock_server.TMDB_KEY,
            "TMDB_BASE_URL": f"{base}/3",
            "SHIKIMORI_URL": base,
            "WATCH_LANG": "ru-RU",
            "NO_PROXY": "127.0.0.1",
            "no_proxy": "127.0.0.1",
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        mock_server.STATE["requests"].clear()
        mock_server.STATE["ongoing_episodes"] = 0

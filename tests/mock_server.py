"""Локальный поддельный сервер, имитирующий TMDB и Shikimori.

Нужен, чтобы тесты шли без интернета и без настоящих ключей.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

TMDB_KEY = "testkey"
TMDB_TOKEN = "aaa.bbb.ccc"  # похож на v4 Read Access Token (JWT)

# Меняется из тестов: сколько серий у «текущего» аниме
STATE = {"ongoing_episodes": 0, "requests": []}

TMDB_MOVIE = {
    "id": 603, "title": "Матрица", "original_title": "The Matrix",
    "release_date": "1999-03-30", "media_type": "movie",
}
TMDB_TV = {
    "id": 1396, "name": "Во все тяжкие", "original_name": "Breaking Bad",
    "first_air_date": "2008-01-20", "media_type": "tv",
}
TMDB_PERSON = {"id": 1, "name": "Какой-то человек", "media_type": "person"}

SHIKI_FMAB = {
    "id": 5114, "name": "Fullmetal Alchemist: Brotherhood", "russian": "Стальной алхимик: Братство",
    "kind": "tv", "status": "released", "episodes": 64, "aired_on": "2009-04-05",
}


def shiki_ongoing():
    return {
        "id": 777, "name": "Ongoing Show", "russian": "Текущее аниме", "kind": "tv",
        "status": "ongoing", "episodes": STATE["ongoing_episodes"], "aired_on": "2026-10-01",
    }


def route(path, query, headers):
    """Возвращает (код, тело)."""
    if path.startswith("/3/"):
        authorized = (
            query.get("api_key") == [TMDB_KEY]
            or headers.get("Authorization") == f"Bearer {TMDB_TOKEN}"
        )
        if not authorized:
            return 401, {"status_message": "Invalid API key"}
        if path == "/3/search/movie":
            return 200, {"results": [{k: v for k, v in TMDB_MOVIE.items() if k != "media_type"}]}
        if path == "/3/search/tv":
            return 200, {"results": [{k: v for k, v in TMDB_TV.items() if k != "media_type"}]}
        if path == "/3/search/multi":
            return 200, {"results": [TMDB_PERSON, TMDB_MOVIE, TMDB_TV]}
        if path == "/3/tv/1396":
            return 200, {**TMDB_TV, "number_of_episodes": 62, "status": "Ended"}
        if path == "/3/movie/603":
            return 200, {**TMDB_MOVIE, "status": "Released"}
        return 404, {}

    if path.startswith("/api/"):
        if not headers.get("User-Agent"):
            return 403, {}  # настоящий Shikimori без User-Agent отвечает отказом
        if path == "/api/animes":
            term = (query.get("search") or [""])[0].lower()
            if "ongoing" in term or "текущ" in term:
                return 200, [shiki_ongoing()]
            return 200, [SHIKI_FMAB]
        if path == "/api/animes/5114":
            return 200, SHIKI_FMAB
        if path == "/api/animes/777":
            return 200, shiki_ongoing()
        return 404, {}
    return 404, {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        headers = dict(self.headers)
        STATE["requests"].append({"path": url.path, "query": query, "headers": headers})
        status, body = route(url.path, query, headers)
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


def start():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server

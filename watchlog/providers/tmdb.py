"""TMDB (The Movie Database) — фильмы и сериалы. Нужен бесплатный ключ."""
import os
from typing import List, Optional, Tuple

from .. import config
from .base import Meta, Provider, ProviderError, http_get_json, year_of

DEFAULT_BASE = "https://api.themoviedb.org/3"


def _parse_ext_id(ext_id: str) -> Tuple[str, str]:
    """'tmdb:tv:1396' -> ('tv', '1396')"""
    parts = ext_id.split(":")
    if len(parts) != 3 or parts[0] != "tmdb" or parts[1] not in ("movie", "tv"):
        raise ProviderError(f"неверный идентификатор TMDB: {ext_id}")
    return parts[1], parts[2]


class TMDB(Provider):
    name = "tmdb"

    @staticmethod
    def base() -> str:
        return os.environ.get("TMDB_BASE_URL", DEFAULT_BASE).rstrip("/")

    def configured(self) -> bool:
        return bool(config.tmdb_key())

    def missing_config_message(self) -> str:
        return (
            "не задан TMDB_API_KEY. Бесплатный ключ выдают на "
            "https://www.themoviedb.org/settings/api — положите его в переменную окружения TMDB_API_KEY"
        )

    def _get(self, path: str, params: Optional[dict] = None):
        key = config.tmdb_key()
        if not key:
            raise ProviderError(self.missing_config_message())
        params = dict(params or {})
        params.setdefault("language", config.lang())
        headers = {}
        # Длинный токен вида eyJ... (v4 Read Access Token) передаётся заголовком,
        # короткий ключ (v3 API Key) — параметром запроса.
        if key.count(".") == 2 or len(key) > 40:
            headers["Authorization"] = f"Bearer {key}"
        else:
            params["api_key"] = key
        return http_get_json(f"{self.base()}{path}", params, headers)

    @staticmethod
    def _to_meta(r: dict, media: str) -> Meta:
        if media == "movie":
            title, original = r.get("title"), r.get("original_title")
            date, kind = r.get("release_date"), "movie"
        else:
            title, original = r.get("name"), r.get("original_name")
            date, kind = r.get("first_air_date"), "series"
        total = None
        if media == "tv" and r.get("number_of_episodes"):
            total = r["number_of_episodes"]
        return Meta(
            source="tmdb",
            ext_id=f"tmdb:{media}:{r['id']}",
            title=title or original or "?",
            original_title=original,
            kind=kind,
            year=year_of(date),
            total=total,
            status=r.get("status"),
        )

    def search(self, query: str, kind: Optional[str] = None, limit: int = 8) -> List[Meta]:
        endpoint = {"movie": "movie", "series": "tv", "anime": "tv"}.get(kind, "multi")
        data = self._get(f"/search/{endpoint}", {"query": query, "include_adult": "false"})
        results = []
        for r in data.get("results", []):
            media = r.get("media_type", endpoint)
            if media not in ("movie", "tv"):
                continue  # в /search/multi встречаются и люди
            results.append(self._to_meta(r, media))
            if len(results) >= limit:
                break
        return results

    def details(self, ext_id: str) -> Meta:
        media, tmdb_id = _parse_ext_id(ext_id)
        return self._to_meta({**self._get(f"/{media}/{tmdb_id}"), "id": tmdb_id}, media)

    def url(self, ext_id: str) -> str:
        media, tmdb_id = _parse_ext_id(ext_id)
        return f"https://www.themoviedb.org/{media}/{tmdb_id}"

"""Shikimori — аниме. Ключ не нужен, но обязателен заголовок User-Agent.

Лимиты сервиса: 5 запросов в секунду и 90 в минуту.
"""
import os
from typing import List, Optional

from .base import Meta, Provider, ProviderError, http_get_json, year_of

# Основной домен и его зеркало. Если первый недоступен по сети, пробуем второй.
DEFAULT_HOSTS = ["https://shikimori.io", "https://shikimori.one"]


def _parse_ext_id(ext_id: str) -> str:
    """'shikimori:5114' -> '5114'"""
    parts = ext_id.split(":")
    if len(parts) != 2 or parts[0] != "shikimori" or not parts[1].isdigit():
        raise ProviderError(f"неверный идентификатор Shikimori: {ext_id}")
    return parts[1]


class Shikimori(Provider):
    name = "shikimori"

    @staticmethod
    def hosts() -> List[str]:
        custom = os.environ.get("SHIKIMORI_URL", "").strip()
        return [custom.rstrip("/")] if custom else list(DEFAULT_HOSTS)

    def _get(self, path: str, params: Optional[dict] = None):
        last_error: Optional[ProviderError] = None
        for host in self.hosts():
            try:
                return http_get_json(f"{host}/api{path}", params)
            except ProviderError as e:
                if not e.network:
                    raise
                last_error = e
        raise last_error

    @staticmethod
    def _to_meta(r: dict) -> Meta:
        total = r.get("episodes") or None  # 0 = число серий ещё неизвестно
        if not total and r.get("kind") == "movie":
            total = 1
        return Meta(
            source="shikimori",
            ext_id=f"shikimori:{r['id']}",
            title=r.get("russian") or r.get("name") or "?",
            original_title=r.get("name"),
            kind="anime",
            year=year_of(r.get("aired_on")),
            total=total,
            status=r.get("status"),
        )

    def search(self, query: str, kind: Optional[str] = None, limit: int = 8) -> List[Meta]:
        data = self._get("/animes", {"search": query, "limit": limit, "order": "popularity"})
        return [self._to_meta(r) for r in data]

    def details(self, ext_id: str) -> Meta:
        return self._to_meta(self._get(f"/animes/{_parse_ext_id(ext_id)}"))

    def url(self, ext_id: str) -> str:
        return f"{self.hosts()[0]}/animes/{_parse_ext_id(ext_id)}"

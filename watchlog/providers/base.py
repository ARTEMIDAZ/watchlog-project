"""Общие типы и HTTP-помощник для провайдеров метаданных."""
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

USER_AGENT = "watchlog/0.2 (personal media tracker)"
TIMEOUT = 10


class ProviderError(Exception):
    """Понятная пользователю ошибка обращения к онлайн-базе.

    network=True означает, что до сервера достучаться не удалось
    (нет сети, DNS, таймаут) — в этом случае можно пробовать запасной адрес.
    """

    def __init__(self, message: str, network: bool = False):
        super().__init__(message)
        self.network = network


@dataclass
class Meta:
    """Данные о тайтле из онлайн-базы в едином формате."""

    source: str                       # "tmdb" | "shikimori"
    ext_id: str                       # "tmdb:tv:1396" | "shikimori:5114"
    title: str                        # название на языке пользователя
    original_title: Optional[str]
    kind: str                         # movie | series | anime
    year: Optional[int] = None
    total: Optional[int] = None       # число серий, если известно
    status: Optional[str] = None      # статус выхода у источника (как есть)


def http_get_json(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = TIMEOUT,
) -> Any:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    req_headers.update(headers or {})
    request = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ProviderError(f"доступ отклонён (HTTP {e.code}) — проверьте ключ или доступность сервиса")
        if e.code == 404:
            raise ProviderError("запись не найдена (HTTP 404)")
        if e.code == 429:
            raise ProviderError("слишком много запросов (HTTP 429), подождите немного")
        raise ProviderError(f"ошибка сервера (HTTP {e.code})")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise ProviderError(f"нет соединения: {reason}", network=True)
    except json.JSONDecodeError:
        raise ProviderError("сервер вернул не JSON")


def year_of(date_string: Optional[str]) -> Optional[int]:
    """'1999-03-30' -> 1999; пустое или кривое значение -> None."""
    if date_string and len(date_string) >= 4 and date_string[:4].isdigit():
        return int(date_string[:4])
    return None


class Provider:
    name = ""

    def configured(self) -> bool:
        return True

    def missing_config_message(self) -> str:
        return ""

    def search(self, query: str, kind: Optional[str] = None, limit: int = 8) -> List[Meta]:
        raise NotImplementedError

    def details(self, ext_id: str) -> Meta:
        raise NotImplementedError

    def url(self, ext_id: str) -> str:
        raise NotImplementedError

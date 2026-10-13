"""Реестр провайдеров и общий поиск по ним."""
from typing import List, Optional, Tuple

from .base import Meta, Provider, ProviderError
from .shikimori import Shikimori
from .tmdb import TMDB

PROVIDERS = {p.name: p for p in (TMDB(), Shikimori())}

__all__ = ["Meta", "Provider", "ProviderError", "PROVIDERS", "get", "search", "details", "enrich", "url_for"]


def get(name: str) -> Provider:
    try:
        return PROVIDERS[name]
    except KeyError:
        raise ProviderError(f"неизвестный источник «{name}» (доступны: {', '.join(PROVIDERS)})")


def _for_ext_id(ext_id: str) -> Provider:
    return get(ext_id.split(":", 1)[0])


def _choose(kind: Optional[str], source: Optional[str]) -> List[Provider]:
    if source:
        return [get(source)]
    if kind == "anime":
        return [PROVIDERS["shikimori"]]
    if kind in ("movie", "series"):
        return [PROVIDERS["tmdb"]]
    return list(PROVIDERS.values())


def search(
    query: str,
    kind: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 8,
) -> Tuple[List[Meta], List[str]]:
    """Ищет по подходящим источникам. Возвращает (результаты, предупреждения).

    Если источник один (выбран явно или однозначно по типу) — его ошибки
    пробрасываются. Если источников несколько, сбой одного не мешает другому.
    """
    chosen = _choose(kind, source)
    results: List[Meta] = []
    warnings: List[str] = []
    for provider in chosen:
        if not provider.configured():
            if len(chosen) == 1:
                raise ProviderError(provider.missing_config_message())
            warnings.append(f"{provider.name}: пропущен — {provider.missing_config_message()}")
            continue
        try:
            results.extend(provider.search(query, kind, limit))
        except ProviderError as e:
            if len(chosen) == 1:
                raise
            warnings.append(f"{provider.name}: {e}")
    return results, warnings


def details(ext_id: str) -> Meta:
    provider = _for_ext_id(ext_id)
    if not provider.configured():
        raise ProviderError(provider.missing_config_message())
    return provider.details(ext_id)


def enrich(meta: Meta) -> Meta:
    """Дополняет выбранный результат поиска тем, чего нет в списке.

    У TMDB в результатах поиска нет числа серий — оно есть только в карточке
    сериала, поэтому делаем один дополнительный запрос. Если он не удался,
    остаёмся с тем, что есть.
    """
    if meta.ext_id.startswith("tmdb:tv:") and meta.total is None:
        try:
            return details(meta.ext_id)
        except ProviderError:
            return meta
    return meta


def url_for(ext_id: str) -> Optional[str]:
    try:
        return _for_ext_id(ext_id).url(ext_id)
    except ProviderError:
        return None

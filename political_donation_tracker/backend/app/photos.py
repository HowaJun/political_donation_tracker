from __future__ import annotations

from typing import Any

import httpx

from .config import settings


_photo_cache: dict[str, str | None] = {}


def display_name(raw: str) -> str:
    if "," in raw:
        last, first = [part.strip() for part in raw.split(",", 1)]
        first = _titleish(first.split()[0] if first else "")
        # Keep full first-middle if present
        first_parts = [_titleish(p) for p in raw.split(",", 1)[1].strip().split()]
        return f"{' '.join(first_parts)} {_titleish(last)}".strip()
    return _titleish(raw)


def _titleish(value: str) -> str:
    return value.title() if value.isupper() else value


async def lookup_photo_url(
    name: str,
    *,
    state: str | None = None,
    office_full: str | None = None,
) -> str | None:
    """Resolve a thumbnail via Wikipedia search (best-effort)."""
    cache_key = f"{name}|{state}|{office_full}"
    if cache_key in _photo_cache:
        return _photo_cache[cache_key]

    label = display_name(name)
    queries = [label]
    if state:
        queries.append(f"{label} {state}")
    if office_full:
        queries.append(f"{label} {office_full}")
    queries.append(f"{label} politician")

    url: str | None = None
    async with httpx.AsyncClient(
        timeout=12.0,
        verify=settings.fec_ssl_verify,
        headers={"User-Agent": "PoliticalDonationTracker/0.1 (local research tool)"},
    ) as client:
        for query in queries:
            url = await _wikipedia_thumbnail(client, query)
            if url:
                break

    _photo_cache[cache_key] = url
    return url


async def _wikipedia_thumbnail(client: httpx.AsyncClient, query: str) -> str | None:
    try:
        response = await client.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrlimit": 1,
                "prop": "pageimages",
                "piprop": "thumbnail",
                "pithumbsize": 320,
                "format": "json",
                "origin": "*",
            },
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        pages = (payload.get("query") or {}).get("pages") or {}
        for page in pages.values():
            thumb = (page.get("thumbnail") or {}).get("source")
            if thumb:
                return str(thumb)
    except Exception:
        return None
    return None

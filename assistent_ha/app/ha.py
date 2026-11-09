"""Client lleuger per a l'API REST de Home Assistant."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)

_DOMAIN_RE = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")


class HAError(RuntimeError):
    """Error retornat per Home Assistant o per la connexió."""


class HomeAssistant:
    def __init__(self, base_url: str, token: str, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
        self._states: list[dict[str, Any]] = []
        self._states_at = 0.0
        self._cache_seconds = 10.0

    async def close(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------ HTTP
    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: Any = None,
    ) -> Any:
        try:
            response = await self._client.request(
                method, path.lstrip("/"), params=params, json=json
            )
        except httpx.HTTPError as exc:
            raise HAError(f"No puc connectar amb Home Assistant: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    detail = payload.get("message") or payload.get("error") or detail
            except ValueError:
                pass
            raise HAError(f"HTTP {response.status_code}: {detail}")

        if not response.content:
            return None
        if "application/json" in response.headers.get("content-type", ""):
            return response.json()
        return response.text

    async def get_config(self) -> dict[str, Any]:
        data = await self._request("GET", "config")
        return data if isinstance(data, dict) else {}

    async def get_states(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "states")
        return data if isinstance(data, list) else []

    async def get_state(self, entity_id: str) -> dict[str, Any] | None:
        try:
            data = await self._request("GET", f"states/{entity_id}")
        except HAError as exc:
            if "404" in str(exc):
                return None
            raise
        return data if isinstance(data, dict) else None

    async def call_service(
        self,
        domain: str,
        service: str,
        data: dict[str, Any] | None = None,
        *,
        return_response: bool = False,
    ) -> Any:
        params = {"return_response": "true"} if return_response else None
        return await self._request(
            "POST", f"services/{domain}/{service}", params=params, json=data or {}
        )

    # --------------------------------------------------------------- entitats
    async def entities(self, max_age: float | None = None) -> list[dict[str, Any]]:
        max_age = self._cache_seconds if max_age is None else max_age
        now = time.monotonic()
        if self._states and now - self._states_at < max_age:
            return self._states
        raw = await self.get_states()
        self._states = [self._row(item) for item in raw if item.get("entity_id")]
        self._states_at = now
        return self._states

    @staticmethod
    def _row(state: dict[str, Any]) -> dict[str, Any]:
        entity_id = str(state.get("entity_id", ""))
        attributes = state.get("attributes") or {}
        return {
            "entity_id": entity_id,
            "domain": entity_id.split(".", 1)[0],
            "name": attributes.get("friendly_name") or entity_id,
            "state": state.get("state"),
        }

    async def has_entity(self, entity_id: str) -> bool:
        if not _DOMAIN_RE.match(entity_id or ""):
            return False
        return any(item["entity_id"] == entity_id for item in await self.entities())

    async def by_domain(self, domain: str) -> list[dict[str, Any]]:
        return [item for item in await self.entities() if item["domain"] == domain]

    async def find(
        self, query: str, domain: str | None = None, limit: int = 25
    ) -> list[dict[str, Any]]:
        """Cerca entitats per nom o entity_id amb una puntuació simple."""
        query = (query or "").strip().lower()
        pool = await self.entities()
        if domain:
            pool = [item for item in pool if item["domain"] == domain]

        if not query:
            return pool[:limit]

        tokens = [token for token in re.split(r"\W+", query) if token]
        scored: list[tuple[float, dict[str, Any]]] = []
        for item in pool:
            haystack = f"{item['entity_id']} {item['name']}".lower()
            if query == item["entity_id"] or query == item["name"].lower():
                score = 100.0
            elif query in haystack:
                score = 50.0 + min(len(query), 25)
            else:
                hits = sum(1 for token in tokens if token in haystack)
                if not hits:
                    continue
                score = 10.0 * hits / max(len(tokens), 1)
            scored.append((score, item))

        scored.sort(key=lambda pair: (-pair[0], pair[1]["entity_id"]))
        return [item for _, item in scored[:limit]]

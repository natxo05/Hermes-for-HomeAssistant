import httpx
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class HAClient:
    def __init__(self, url: str, token: str, calendar_entity: str):
        self.url = url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self.calendar_entity = calendar_entity

    async def _call_service(self, service: str, data: dict) -> dict | None:
        url = f"{self.url}/api/services/{service}"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=data, headers=self.headers, timeout=30)
            logger.info(f"HA API {service}: {resp.status_code}")
            if resp.status_code == 200:
                return resp.json()
            logger.error(f"Error HA API: {resp.status_code} {resp.text}")
            return None

    async def add_shopping_item(self, name: str) -> bool:
        result = await self._call_service(
            "shopping_list/add_item",
            {"name": name},
        )
        return result is not None

    async def create_calendar_event(self, summary: str, dt: datetime | None = None,
                                    place: str | None = None, doctor: str | None = None) -> bool:
        if dt is None:
            dt = datetime.now() + timedelta(days=1)
            dt = dt.replace(hour=10, minute=0, second=0, microsecond=0)

        start = dt.isoformat()
        end = (dt + timedelta(hours=1)).isoformat()

        description = f"Cita mèdica"
        if doctor:
            description += f"\nMetge: {doctor}"
        if place:
            description += f"\nLloc: {place}"

        data = {
            "entity_id": self.calendar_entity,
            "summary": summary,
            "description": description,
            "start_date_time": start,
            "end_date_time": end,
        }
        if place:
            data["location"] = place

        result = await self._call_service("calendar/create_event", data)
        return result is not None

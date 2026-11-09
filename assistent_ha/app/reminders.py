"""Recordatoris propis de l'assistent, persistits a /data/reminders.json."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

Sender = Callable[[int, str], Awaitable[None]]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Reminder:
    id: str
    chat_id: int
    text: str
    due: str  # ISO 8601 en UTC
    created: str

    @property
    def due_dt(self) -> datetime:
        return datetime.fromisoformat(self.due)

    def due_local(self, tz_name: str) -> datetime:
        return self.due_dt.astimezone(ZoneInfo(tz_name))


class ReminderStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._items: dict[str, Reminder] = {}
        self._load()

    # ------------------------------------------------------------- persistència
    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.exception("No puc llegir els recordatoris; començo amb una llista buida.")
            return
        for entry in raw if isinstance(raw, list) else []:
            try:
                reminder = Reminder(**entry)
                reminder.due_dt  # valida el format
            except (TypeError, ValueError):
                log.warning("Ignoro un recordatori corrupte: %r", entry)
                continue
            self._items[reminder.id] = reminder

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = [asdict(item) for item in self._items.values()]
            self._path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            log.exception("No puc desar els recordatoris a %s", self._path)

    # ------------------------------------------------------------------- API
    def add(self, chat_id: int, text: str, due: datetime) -> Reminder:
        if due.tzinfo is None:
            raise ValueError("El recordatori necessita una data amb zona horària.")
        reminder = Reminder(
            id=uuid.uuid4().hex[:8],
            chat_id=chat_id,
            text=text.strip(),
            due=due.astimezone(timezone.utc).isoformat(timespec="seconds"),
            created=_utc_now().isoformat(timespec="seconds"),
        )
        self._items[reminder.id] = reminder
        self._save()
        return reminder

    def remove(self, reminder_id: str, chat_id: int | None = None) -> Reminder | None:
        reminder = self._items.get(reminder_id)
        if reminder is None:
            return None
        if chat_id is not None and reminder.chat_id != chat_id:
            return None
        del self._items[reminder_id]
        self._save()
        return reminder

    def list_for(self, chat_id: int) -> list[Reminder]:
        items = [item for item in self._items.values() if item.chat_id == chat_id]
        return sorted(items, key=lambda item: item.due)

    def all(self) -> list[Reminder]:
        return sorted(self._items.values(), key=lambda item: item.due)

    def count(self) -> int:
        return len(self._items)

    def due(self, now: datetime | None = None) -> list[Reminder]:
        now = now or _utc_now()
        return [item for item in self._items.values() if item.due_dt <= now]

    # ----------------------------------------------------------- planificador
    async def loop(self, sender: Sender, interval: float = 15.0) -> None:
        log.info("Planificador de recordatoris en marxa (cada %.0f s).", interval)
        while True:
            try:
                for reminder in self.due():
                    self.remove(reminder.id)
                    try:
                        await sender(reminder.chat_id, f"⏰ Recordatori: {reminder.text}")
                    except Exception:
                        log.exception("No he pogut enviar el recordatori %s", reminder.id)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Error al planificador de recordatoris")
            await asyncio.sleep(interval)

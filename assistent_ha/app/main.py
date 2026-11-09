"""Punt d'entrada de l'add-on."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from telegram import Update

from .config import Settings, load_settings
from .ha import HomeAssistant
from .llm import Agent
from .reminders import ReminderStore
from .stt import SpeechToText
from .telegram_bot import build_application

VERSION = "0.1.0"

log = logging.getLogger(__name__)


@dataclass
class Runtime:
    settings: Settings
    ha: HomeAssistant
    reminders: ReminderStore
    started_at: float = field(default_factory=time.time)
    messages: int = 0
    errors: int = 0
    last_error: str | None = None
    web_runner: Any = None
    reminder_task: Any = None

    def status(self) -> dict[str, Any]:
        uptime = timedelta(seconds=int(time.time() - self.started_at))
        return {
            "Versió": VERSION,
            "Temps actiu": str(uptime).split(".")[0],
            "Model": self.settings.gemini_model,
            "Veu": f"faster-whisper {self.settings.whisper_model}",
            "Zona horària": self.settings.timezone,
            "Usuaris autoritzats": len(self.settings.allowed_user_ids),
            "Recordatoris actius": self.reminders.count(),
            "Missatges processats": self.messages,
            "Errors": self.errors,
            "Darrer error": self.last_error or "—",
        }


def _configure_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for noisy in ("httpx", "httpcore", "telegram.ext.Application", "faster_whisper"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main() -> None:
    settings = load_settings()
    _configure_logging(settings.debug)

    ha = HomeAssistant(settings.ha_url, settings.ha_token)
    reminders = ReminderStore(settings.reminders_file)
    stt = SpeechToText(settings)
    agent = Agent(settings, ha, reminders)
    runtime = Runtime(settings=settings, ha=ha, reminders=reminders)

    application = build_application(settings, ha, agent, reminders, stt, runtime)

    log.info("Hermes %s engegat (model %s)", VERSION, settings.gemini_model)
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()

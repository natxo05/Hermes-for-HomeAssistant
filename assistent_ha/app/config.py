"""Carrega la configuració de l'add-on (options.json) o de variables d'entorn."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("ASSISTANT_DATA_DIR", "/data"))
OPTIONS_FILE = DATA_DIR / "options.json"

DEFAULTS: dict = {
    "telegram_token": "",
    "allowed_user_ids": [],
    "gemini_api_key": "",
    "gemini_model": "gemini-2.5-flash",
    "whisper_model": "small",
    "whisper_compute_type": "int8",
    "language": "ca",
    "shopping_list_entity": "todo.shopping_list",
    "calendar_entity": "calendar.personal",
    "timezone": "",
    "max_history_turns": 12,
    "confirm_domains": ["lock", "alarm_control_panel", "cover"],
    "startup_message": True,
    "debug": False,
}

ENV_OVERRIDES = {
    "telegram_token": "TELEGRAM_TOKEN",
    "gemini_api_key": "GEMINI_API_KEY",
    "gemini_model": "GEMINI_MODEL",
    "language": "ASSISTANT_LANGUAGE",
    "whisper_model": "WHISPER_MODEL",
}


@dataclass
class Settings:
    telegram_token: str
    allowed_user_ids: set[int]
    gemini_api_key: str
    gemini_model: str
    whisper_model: str
    whisper_compute_type: str
    language: str
    shopping_list_entity: str
    calendar_entity: str
    timezone: str
    max_history_turns: int
    confirm_domains: set[str]
    startup_message: bool
    debug: bool
    ha_url: str
    ha_token: str
    timezone_auto: bool = False
    data_dir: Path = DATA_DIR

    @property
    def models_dir(self) -> Path:
        path = self.data_dir / "models"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def reminders_file(self) -> Path:
        return self.data_dir / "reminders.json"


def _read_options() -> dict:
    options = dict(DEFAULTS)
    if OPTIONS_FILE.is_file():
        try:
            loaded = json.loads(OPTIONS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"No puc llegir la configuració {OPTIONS_FILE}: {exc}") from exc
        if isinstance(loaded, dict):
            options.update(loaded)
    else:
        log.warning("No existeix %s; faig servir valors per defecte i variables d'entorn.", OPTIONS_FILE)

    for key, env_name in ENV_OVERRIDES.items():
        value = os.environ.get(env_name)
        if value:
            options[key] = value
    return options


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


def _as_int_set(values) -> set[int]:
    result: set[int] = set()
    for value in values or []:
        try:
            result.add(int(str(value).strip()))
        except (TypeError, ValueError):
            log.warning("Ignoro un ID d'usuari no vàlid: %r", value)
    return result


def _as_str_set(values) -> set[str]:
    return {str(value).strip().lower() for value in values or [] if str(value).strip()}


def load_settings() -> Settings:
    options = _read_options()

    telegram_token = str(options.get("telegram_token") or "").strip()
    if not telegram_token:
        raise SystemExit(
            "Falta el token del bot de Telegram. Obre la configuració de l'add-on i "
            "enganxa el token que et dona @BotFather."
        )

    gemini_api_key = str(options.get("gemini_api_key") or "").strip()
    if not gemini_api_key:
        raise SystemExit(
            "Falta la clau de l'API de Gemini. Crea'n una a https://aistudio.google.com/apikey "
            "i enganxa-la a la configuració de l'add-on."
        )

    supervisor_token = os.environ.get("SUPERVISOR_TOKEN", "").strip()
    ha_url = (os.environ.get("HA_URL") or ("http://supervisor/core/api" if supervisor_token else "")).strip()
    ha_token = (supervisor_token or os.environ.get("HA_TOKEN", "")).strip()
    if not ha_url or not ha_token:
        raise SystemExit(
            "No puc connectar amb Home Assistant. Dins d'un add-on cal 'homeassistant_api: true'. "
            "Per a proves locals, defineix HA_URL i HA_TOKEN."
        )

    timezone_option = str(options.get("timezone") or "").strip()
    timezone = timezone_option or os.environ.get("TZ", "").strip() or "Europe/Madrid"

    try:
        max_history_turns = max(0, min(50, int(options.get("max_history_turns", 12))))
    except (TypeError, ValueError):
        max_history_turns = 12

    return Settings(
        telegram_token=telegram_token,
        allowed_user_ids=_as_int_set(options.get("allowed_user_ids")),
        gemini_api_key=gemini_api_key,
        gemini_model=str(options.get("gemini_model") or "gemini-2.5-flash").strip(),
        whisper_model=str(options.get("whisper_model") or "small").strip(),
        whisper_compute_type=str(options.get("whisper_compute_type") or "int8").strip(),
        language=str(options.get("language") or "ca").strip(),
        shopping_list_entity=str(options.get("shopping_list_entity") or "todo.shopping_list").strip(),
        calendar_entity=str(options.get("calendar_entity") or "calendar.personal").strip(),
        timezone=timezone,
        max_history_turns=max_history_turns,
        confirm_domains=_as_str_set(options.get("confirm_domains")),
        startup_message=_as_bool(options.get("startup_message", True)),
        debug=_as_bool(options.get("debug", False)),
        ha_url=ha_url,
        ha_token=ha_token,
        timezone_auto=not timezone_option,
    )

"""Eines que el model pot cridar i la seva implementació sobre Home Assistant."""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from google.genai import types

from .config import Settings
from .ha import HAError, HomeAssistant
from .reminders import ReminderStore

log = logging.getLogger(__name__)

# Accions que poden tenir conseqüències físiques i que volem confirmar abans d'executar.
RISKY_ACTIONS = {"unlock", "open", "disarm", "set_position"}

CONTROL_ACTIONS = [
    "turn_on",
    "turn_off",
    "toggle",
    "set_brightness",
    "set_color_temp",
    "open",
    "close",
    "stop",
    "set_position",
    "set_temperature",
    "set_hvac_mode",
    "set_fan_mode",
    "set_volume",
    "play",
    "pause",
    "next",
    "previous",
    "lock",
    "unlock",
    "activate",
    "press",
    "start",
    "return_to_base",
    "select_option",
    "set_value",
]


class ToolError(Exception):
    """Error controlat: el missatge es retorna al model perquè l'expliqui."""


# ---------------------------------------------------------------- confirmacions
@dataclass
class PendingAction:
    id: str
    chat_id: int
    summary: str
    domain: str
    service: str
    data: dict[str, Any]

    @property
    def label(self) -> str:
        return f"{self.domain}.{self.service}"


_PENDING: dict[str, PendingAction] = {}


def register_pending(
    chat_id: int, summary: str, domain: str, service: str, data: dict[str, Any]
) -> PendingAction:
    action = PendingAction(
        id=uuid.uuid4().hex[:10],
        chat_id=chat_id,
        summary=summary,
        domain=domain,
        service=service,
        data=data,
    )
    _PENDING[action.id] = action
    # Evita que el diccionari creixi sense control si l'usuari no respon mai.
    if len(_PENDING) > 200:
        for key in list(_PENDING)[:100]:
            _PENDING.pop(key, None)
    return action


def pop_pending(action_id: str) -> PendingAction | None:
    return _PENDING.pop(action_id, None)


async def execute_pending(ha: HomeAssistant, action: PendingAction) -> None:
    await ha.call_service(action.domain, action.service, action.data)


# --------------------------------------------------------------------- context
@dataclass
class ToolContext:
    ha: HomeAssistant
    settings: Settings
    reminders: ReminderStore
    chat_id: int
    pending: list[PendingAction] = field(default_factory=list)


# --------------------------------------------------------------------- utilitats
def _parse_dt(raw: str, tz_name: str) -> datetime:
    value = (raw or "").strip()
    if not value:
        raise ToolError("Falta la data o l'hora.")
    value = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(value.replace(" ", "T"))
        except ValueError as exc:
            raise ToolError(
                f"No entenc la data '{raw}'. Fes servir format ISO 8601, per exemple 2026-03-14T09:00:00+01:00."
            ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(tz_name))
    return parsed


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="minutes")


async def _resolve_todo(ctx: ToolContext, list_name: str | None) -> str:
    entities = await ctx.ha.by_domain("todo")
    if not entities:
        raise ToolError("No hi ha cap llista de tipus 'todo' creada a Home Assistant.")
    if list_name:
        wanted = list_name.strip().lower()
        for entity in entities:
            short = entity["entity_id"].split(".", 1)[1]
            if (
                entity["entity_id"] == list_name
                or short == wanted
                or entity["name"].lower() == wanted
                or wanted in entity["name"].lower()
                or wanted in short
            ):
                return entity["entity_id"]
        available = ", ".join(item["entity_id"] for item in entities)
        raise ToolError(f"No trobo la llista '{list_name}'. Disponibles: {available}")
    preferred = ctx.settings.shopping_list_entity
    if any(item["entity_id"] == preferred for item in entities):
        return preferred
    return entities[0]["entity_id"]


async def _resolve_calendar(ctx: ToolContext, calendar: str | None) -> str:
    entities = await ctx.ha.by_domain("calendar")
    if not entities:
        raise ToolError(
            "No hi ha cap calendari a Home Assistant. Crea'n un (calendari local) des de la interfície."
        )
    if calendar:
        wanted = calendar.strip().lower()
        for entity in entities:
            short = entity["entity_id"].split(".", 1)[1]
            if (
                entity["entity_id"] == calendar
                or short == wanted
                or entity["name"].lower() == wanted
                or wanted in entity["name"].lower()
            ):
                return entity["entity_id"]
        available = ", ".join(item["entity_id"] for item in entities)
        raise ToolError(f"No trobo el calendari '{calendar}'. Disponibles: {available}")
    preferred = ctx.settings.calendar_entity
    if any(item["entity_id"] == preferred for item in entities):
        return preferred
    return entities[0]["entity_id"]


def _resolve_control(domain: str, action: str, value: str | None) -> tuple[str, str, dict[str, Any]]:
    """Retorna (domini, servei, dades extra) per a l'acció demanada."""
    if action == "activate":
        if domain == "scene":
            return "scene", "turn_on", {}
        if domain == "script":
            return "script", "turn_on", {}
        if domain == "automation":
            return "automation", "trigger", {}
        if domain == "button":
            return "button", "press", {}
        return domain, "turn_on", {}

    if action in {"open", "close", "stop"} and domain == "cover":
        return "cover", f"{action}_cover", {}

    if action in {"turn_on", "turn_off", "toggle", "open", "close", "stop", "lock", "unlock", "press"}:
        return domain, action, {}

    if action == "set_brightness":
        return "light", "turn_on", {"brightness_pct": _number(value, 1, 100)}
    if action == "set_color_temp":
        return "light", "turn_on", {"color_temp_kelvin": int(_number(value, 1000, 10000))}
    if action == "set_position":
        return "cover", "set_cover_position", {"position": int(_number(value, 0, 100))}
    if action == "set_temperature":
        return "climate", "set_temperature", {"temperature": _number(value, 5, 35)}
    if action == "set_hvac_mode":
        return "climate", "set_hvac_mode", {"hvac_mode": _text(value)}
    if action == "set_fan_mode":
        return "climate", "set_fan_mode", {"fan_mode": _text(value)}
    if action == "set_volume":
        return "media_player", "volume_set", {"volume_level": _number(value, 0, 100) / 100}
    if action == "play":
        return "media_player", "media_play", {}
    if action == "pause":
        return "media_player", "media_pause", {}
    if action == "next":
        return "media_player", "media_next_track", {}
    if action == "previous":
        return "media_player", "media_previous_track", {}
    if action == "start":
        return "vacuum", "start", {}
    if action == "return_to_base":
        return "vacuum", "return_to_base", {}
    if action == "select_option":
        return "select", "select_option", {"option": _text(value)}
    if action == "set_value":
        if domain == "input_number":
            return "input_number", "set_value", {"value": _number(value, -1e9, 1e9)}
        return "number", "set_value", {"value": _number(value, -1e9, 1e9)}

    raise ToolError(f"L'acció '{action}' no és compatible amb el domini '{domain}'.")


def _number(value: str | None, minimum: float, maximum: float) -> float:
    if value is None:
        raise ToolError("Aquesta acció necessita un valor numèric.")
    try:
        number = float(str(value).replace(",", "."))
    except ValueError as exc:
        raise ToolError(f"'{value}' no és un número vàlid.") from exc
    if number < minimum or number > maximum:
        raise ToolError(f"El valor ha d'estar entre {minimum} i {maximum}.")
    return number


def _text(value: str | None) -> str:
    if value is None or not str(value).strip():
        raise ToolError("Aquesta acció necessita un valor de text.")
    return str(value).strip()


# ------------------------------------------------------------------------ eines
async def add_shopping_items(
    ctx: ToolContext, items: list[str], list_name: str | None = None
) -> dict[str, Any]:
    cleaned = [str(item).strip() for item in items or [] if str(item).strip()]
    if not cleaned:
        raise ToolError("No has indicat cap producte per afegir.")
    entity_id = await _resolve_todo(ctx, list_name)
    for item in cleaned:
        await ctx.ha.call_service("todo", "add_item", {"entity_id": entity_id, "item": item})
    return {"status": "ok", "list": entity_id, "added": cleaned}


async def remove_shopping_item(
    ctx: ToolContext, item: str, list_name: str | None = None
) -> dict[str, Any]:
    name = _text(item)
    entity_id = await _resolve_todo(ctx, list_name)
    await ctx.ha.call_service("todo", "remove_item", {"entity_id": entity_id, "item": name})
    return {"status": "ok", "list": entity_id, "removed": name}


async def get_shopping_list(
    ctx: ToolContext, list_name: str | None = None
) -> dict[str, Any]:
    entity_id = await _resolve_todo(ctx, list_name)
    response = await ctx.ha.call_service(
        "todo", "get_items", {"entity_id": entity_id}, return_response=True
    )
    payload = (response or {}).get(entity_id, {}) if isinstance(response, dict) else {}
    items = payload.get("items", []) if isinstance(payload, dict) else []
    pending = [item.get("summary") for item in items if item.get("status") != "completed"]
    done = [item.get("summary") for item in items if item.get("status") == "completed"]
    return {"status": "ok", "list": entity_id, "pending": pending, "completed": done}


async def clear_shopping_list(
    ctx: ToolContext, list_name: str | None = None, only_completed: bool = True
) -> dict[str, Any]:
    entity_id = await _resolve_todo(ctx, list_name)
    if only_completed:
        await ctx.ha.call_service(
            "todo", "remove_completed_items", {"entity_id": entity_id}
        )
        return {"status": "ok", "list": entity_id, "cleared": "completed"}

    response = await ctx.ha.call_service(
        "todo", "get_items", {"entity_id": entity_id}, return_response=True
    )
    payload = (response or {}).get(entity_id, {}) if isinstance(response, dict) else {}
    for item in payload.get("items", []) if isinstance(payload, dict) else []:
        await ctx.ha.call_service(
            "todo", "remove_item", {"entity_id": entity_id, "item": item.get("summary")}
        )
    return {"status": "ok", "list": entity_id, "cleared": "all"}


async def create_calendar_event(
    ctx: ToolContext,
    title: str,
    start: str,
    end: str | None = None,
    all_day: bool = False,
    description: str | None = None,
    location: str | None = None,
    calendar: str | None = None,
) -> dict[str, Any]:
    tz_name = ctx.settings.timezone
    start_dt = _parse_dt(start, tz_name)
    end_dt = _parse_dt(end, tz_name) if end else start_dt + timedelta(hours=1)
    if all_day:
        end_dt = end_dt if end_dt.date() > start_dt.date() else start_dt + timedelta(days=1)
    elif end_dt <= start_dt:
        end_dt = start_dt + timedelta(hours=1)

    entity_id = await _resolve_calendar(ctx, calendar)
    data: dict[str, Any] = {
        "entity_id": entity_id,
        "summary": _text(title),
        "description": description or "",
        "location": location or "",
    }
    if all_day:
        data["start_date"] = start_dt.date().isoformat()
        data["end_date"] = end_dt.date().isoformat()
    else:
        data["start_date_time"] = _iso(start_dt)
        data["end_date_time"] = _iso(end_dt)

    await ctx.ha.call_service("calendar", "create_event", data)
    return {
        "status": "ok",
        "calendar": entity_id,
        "title": data["summary"],
        "start": data.get("start_date") or data.get("start_date_time"),
        "end": data.get("end_date") or data.get("end_date_time"),
    }


async def get_calendar_events(
    ctx: ToolContext,
    start: str,
    end: str,
    calendar: str | None = None,
) -> dict[str, Any]:
    tz_name = ctx.settings.timezone
    start_dt = _parse_dt(start, tz_name)
    end_dt = _parse_dt(end, tz_name)
    if end_dt <= start_dt:
        raise ToolError("La data final ha de ser posterior a la inicial.")

    entity_id = await _resolve_calendar(ctx, calendar)
    response = await ctx.ha.call_service(
        "calendar",
        "get_events",
        {
            "entity_id": entity_id,
            "start_date_time": _iso(start_dt),
            "end_date_time": _iso(end_dt),
        },
        return_response=True,
    )
    payload = (response or {}).get(entity_id, {}) if isinstance(response, dict) else {}
    events = payload.get("events", []) if isinstance(payload, dict) else []
    simplified = [
        {
            "title": event.get("summary"),
            "start": (event.get("start") or "")[:16],
            "end": (event.get("end") or "")[:16],
            "location": event.get("location") or "",
        }
        for event in events
    ]
    return {"status": "ok", "calendar": entity_id, "count": len(simplified), "events": simplified}


async def create_reminder(ctx: ToolContext, text: str, when: str) -> dict[str, Any]:
    message = _text(text)
    due = _parse_dt(when, ctx.settings.timezone)
    now = datetime.now(ZoneInfo(ctx.settings.timezone))
    if due <= now:
        raise ToolError(
            "Aquesta hora ja ha passat. Torna a calcular-la a partir de la data i hora actuals."
        )
    reminder = ctx.reminders.add(ctx.chat_id, message, due)
    return {
        "status": "ok",
        "id": reminder.id,
        "text": reminder.text,
        "due": _iso(due),
    }


async def list_reminders(ctx: ToolContext) -> dict[str, Any]:
    items = ctx.reminders.list_for(ctx.chat_id)
    return {
        "status": "ok",
        "count": len(items),
        "reminders": [
            {
                "id": item.id,
                "text": item.text,
                "due": _iso(item.due_local(ctx.settings.timezone)),
            }
            for item in items
        ],
    }


async def cancel_reminder(ctx: ToolContext, reminder_id: str) -> dict[str, Any]:
    removed = ctx.reminders.remove(str(reminder_id).strip(), ctx.chat_id)
    if removed is None:
        raise ToolError(f"No tinc cap recordatori amb l'identificador '{reminder_id}'.")
    return {"status": "ok", "cancelled": removed.id, "text": removed.text}


async def list_entities(
    ctx: ToolContext, query: str | None = None, domain: str | None = None
) -> dict[str, Any]:
    domain = (domain or "").strip().lower() or None
    query = (query or "").strip()

    if not query and not domain:
        counts = Counter(item["domain"] for item in await ctx.ha.entities())
        return {"status": "ok", "domains": dict(sorted(counts.items()))}

    matches = await ctx.ha.find(query, domain=domain, limit=25) if query else (
        await ctx.ha.by_domain(domain)
    )[:60]
    return {
        "status": "ok",
        "count": len(matches),
        "entities": [
            {"entity_id": item["entity_id"], "name": item["name"], "state": item["state"]}
            for item in matches
        ],
    }


async def get_entity_state(ctx: ToolContext, entity_id: str) -> dict[str, Any]:
    entity_id = _text(entity_id)
    state = await ctx.ha.get_state(entity_id)
    if state is None:
        raise ToolError(f"No existeix cap entitat amb l'identificador '{entity_id}'.")
    attributes = state.get("attributes") or {}
    interesting = {
        key: attributes[key]
        for key in (
            "friendly_name",
            "unit_of_measurement",
            "current_temperature",
            "temperature",
            "hvac_mode",
            "brightness",
            "color_mode",
            "media_title",
            "battery_level",
            "device_class",
        )
        if key in attributes
    }
    return {
        "status": "ok",
        "entity_id": entity_id,
        "state": state.get("state"),
        "attributes": interesting,
        "last_changed": state.get("last_changed"),
    }


async def control_entity(
    ctx: ToolContext, entity_id: str, action: str, value: str | None = None
) -> dict[str, Any]:
    entity_id = _text(entity_id)
    if not await ctx.ha.has_entity(entity_id):
        raise ToolError(f"No existeix cap entitat amb l'identificador '{entity_id}'.")

    domain = entity_id.split(".", 1)[0]
    service_domain, service, extra = _resolve_control(domain, action, value)
    data = {"entity_id": entity_id, **extra}
    summary = f"{action} {entity_id}" + (f" ({value})" if value else "")

    if domain in ctx.settings.confirm_domains and action in RISKY_ACTIONS:
        pending = register_pending(ctx.chat_id, summary, service_domain, service, data)
        ctx.pending.append(pending)
        return {
            "status": "confirmation_required",
            "confirmation_id": pending.id,
            "message": "He demanat confirmació a l'usuari abans d'executar l'acció.",
        }

    await ctx.ha.call_service(service_domain, service, data)
    return {"status": "ok", "executed": summary}


async def send_persistent_notification(ctx: ToolContext, message: str) -> dict[str, Any]:
    text = _text(message)
    await ctx.ha.call_service(
        "persistent_notification",
        "create",
        {"message": text, "title": "Hermes"},
    )
    return {"status": "ok", "notified": text}


TOOL_IMPL = {
    "add_shopping_items": add_shopping_items,
    "remove_shopping_item": remove_shopping_item,
    "get_shopping_list": get_shopping_list,
    "clear_shopping_list": clear_shopping_list,
    "create_calendar_event": create_calendar_event,
    "get_calendar_events": get_calendar_events,
    "create_reminder": create_reminder,
    "list_reminders": list_reminders,
    "cancel_reminder": cancel_reminder,
    "list_entities": list_entities,
    "get_entity_state": get_entity_state,
    "control_entity": control_entity,
    "send_persistent_notification": send_persistent_notification,
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


async def execute_tool(ctx: ToolContext, name: str, args: dict[str, Any]) -> dict[str, Any]:
    implementation = TOOL_IMPL.get(name)
    if implementation is None:
        return {"error": f"Eina desconeguda: {name}"}

    clean_args = {key: value for key, value in (args or {}).items() if value is not None}
    try:
        result = await implementation(ctx, **clean_args)
        return _jsonable(result)
    except ToolError as exc:
        return {"error": str(exc)}
    except HAError as exc:
        return {"error": f"Home Assistant ha retornat un error: {exc}"}
    except TypeError as exc:
        return {"error": f"Paràmetres incorrectes per a l'eina {name}: {exc}"}
    except Exception as exc:  # pragma: no cover - xarxa de seguretat
        log.exception("Error executant l'eina %s", name)
        return {"error": f"Error intern executant {name}: {exc}"}


# ------------------------------------------------------------------- esquemes
def _obj(properties: dict[str, types.Schema], required: list[str] | None = None) -> types.Schema:
    schema = types.Schema(type=types.Type.OBJECT, properties=properties)
    if required:
        schema.required = required
    return schema


def _str(description: str, enum: list[str] | None = None) -> types.Schema:
    schema = types.Schema(type=types.Type.STRING, description=description)
    if enum:
        schema.enum = enum
    return schema


def _bool(description: str) -> types.Schema:
    return types.Schema(type=types.Type.BOOLEAN, description=description)


def _arr(items: types.Schema, description: str) -> types.Schema:
    return types.Schema(type=types.Type.ARRAY, items=items, description=description)


def build_tool() -> types.Tool:
    declarations = [
        types.FunctionDeclaration(
            name="add_shopping_items",
            description="Afegeix un o més productes a una llista de la compra de Home Assistant.",
            parameters=_obj(
                {
                    "items": _arr(
                        types.Schema(type=types.Type.STRING),
                        "Productes a afegir, per exemple ['llet', 'pa', 'ous'].",
                    ),
                    "list_name": _str(
                        "Nom o entity_id de la llista. Omet-ho per fer servir la llista per defecte."
                    ),
                },
                ["items"],
            ),
        ),
        types.FunctionDeclaration(
            name="remove_shopping_item",
            description="Treu un producte d'una llista de la compra.",
            parameters=_obj(
                {
                    "item": _str("Nom exacte del producte a treure."),
                    "list_name": _str("Nom o entity_id de la llista. Opcional."),
                },
                ["item"],
            ),
        ),
        types.FunctionDeclaration(
            name="get_shopping_list",
            description="Consulta els productes pendents i els ja comprats d'una llista.",
            parameters=_obj({"list_name": _str("Nom o entity_id de la llista. Opcional.")}),
        ),
        types.FunctionDeclaration(
            name="clear_shopping_list",
            description="Buitja una llista de la compra, només els productes comprats o tota la llista.",
            parameters=_obj(
                {
                    "list_name": _str("Nom o entity_id de la llista. Opcional."),
                    "only_completed": _bool(
                        "Cert per treure només els productes ja marcats com a comprats. Per defecte cert."
                    ),
                }
            ),
        ),
        types.FunctionDeclaration(
            name="create_calendar_event",
            description="Crea una cita o esdeveniment en un calendari de Home Assistant.",
            parameters=_obj(
                {
                    "title": _str("Títol de la cita."),
                    "start": _str(
                        "Inici en ISO 8601 amb desplaçament horari, per exemple 2026-03-14T09:00:00+01:00."
                    ),
                    "end": _str("Fi en ISO 8601. Omet-ho per una cita d'una hora."),
                    "all_day": _bool("Cert si és un esdeveniment de tot el dia."),
                    "description": _str("Descripció o notes. Opcional."),
                    "location": _str("Lloc. Opcional."),
                    "calendar": _str("Nom o entity_id del calendari. Opcional."),
                },
                ["title", "start"],
            ),
        ),
        types.FunctionDeclaration(
            name="get_calendar_events",
            description="Consulta les cites d'un calendari en un interval de dates.",
            parameters=_obj(
                {
                    "start": _str("Inici de l'interval en ISO 8601."),
                    "end": _str("Fi de l'interval en ISO 8601."),
                    "calendar": _str("Nom o entity_id del calendari. Opcional."),
                },
                ["start", "end"],
            ),
        ),
        types.FunctionDeclaration(
            name="create_reminder",
            description=(
                "Crea un recordatori que enviarà un missatge de Telegram a l'hora indicada. "
                "Fes-lo servir per avisos puntuals ('recorda'm trucar al metge demà a les 9')."
            ),
            parameters=_obj(
                {
                    "text": _str("Què cal recordar."),
                    "when": _str("Data i hora en ISO 8601 amb desplaçament horari."),
                },
                ["text", "when"],
            ),
        ),
        types.FunctionDeclaration(
            name="list_reminders",
            description="Llista els recordatoris actius de l'usuari.",
            parameters=_obj({}),
        ),
        types.FunctionDeclaration(
            name="cancel_reminder",
            description="Cancel·la un recordatori pel seu identificador.",
            parameters=_obj({"reminder_id": _str("Identificador del recordatori.")}, ["reminder_id"]),
        ),
        types.FunctionDeclaration(
            name="list_entities",
            description=(
                "Cerca entitats de Home Assistant per nom o domini. Sense paràmetres retorna "
                "un resum de dominis disponibles. Fes-la servir abans de controlar un dispositiu "
                "si no saps el seu entity_id."
            ),
            parameters=_obj(
                {
                    "query": _str("Text a cercar, per exemple 'llum cuina' o 'temperatura saló'."),
                    "domain": _str("Domini a filtrar, per exemple light, switch, sensor, climate."),
                }
            ),
        ),
        types.FunctionDeclaration(
            name="get_entity_state",
            description="Consulta l'estat i els atributs principals d'una entitat.",
            parameters=_obj({"entity_id": _str("entity_id complet, per exemple sensor.temperatura_salo")}, ["entity_id"]),
        ),
        types.FunctionDeclaration(
            name="control_entity",
            description=(
                "Executa una acció sobre una entitat: encendre, apagar, ajustar brillantor o "
                "temperatura, obrir o tancar persianes, activar escenes o scripts, etc."
            ),
            parameters=_obj(
                {
                    "entity_id": _str("entity_id complet de l'entitat."),
                    "action": _str("Acció a executar.", CONTROL_ACTIONS),
                    "value": _str(
                        "Valor opcional segons l'acció: percentatge de brillantor (1-100), "
                        "posició de persiana (0-100), temperatura, mode HVAC, opció, etc."
                    ),
                },
                ["entity_id", "action"],
            ),
        ),
        types.FunctionDeclaration(
            name="send_persistent_notification",
            description="Crea una notificació persistent al tauler de Home Assistant.",
            parameters=_obj({"message": _str("Text de la notificació.")}, ["message"]),
        ),
    ]
    return types.Tool(function_declarations=declarations)

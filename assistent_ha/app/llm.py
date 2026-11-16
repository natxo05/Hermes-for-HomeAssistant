"""Bucle d'agent amb Gemini i function calling manual."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from google import genai
from google.genai import types

from .config import Settings
from .ha import HomeAssistant
from .prompts import system_prompt
from .reminders import ReminderStore
from .tools import PendingAction, ToolContext, build_tool, execute_tool

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6
RETRIES = 3


def is_quota_error(exc: Exception) -> bool:
    """Detecta errors 429/quota (reintentar no ajuda; cal canviar de model)."""
    if getattr(exc, "code", None) == 429:
        return True
    text = str(exc)
    return "RESOURCE_EXHAUSTED" in text or "exceeded your current quota" in text


@dataclass
class AgentReply:
    text: str
    pending: list[PendingAction] = field(default_factory=list)


class Agent:
    def __init__(self, settings: Settings, ha: HomeAssistant, reminders: ReminderStore) -> None:
        self._settings = settings
        self._ha = ha
        self._reminders = reminders
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._tool = build_tool()
        self._histories: dict[int, list[types.Content]] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    # ------------------------------------------------------------------ estat
    def reset(self, chat_id: int) -> None:
        self._histories.pop(chat_id, None)

    def history_size(self, chat_id: int) -> int:
        return len(self._histories.get(chat_id, []))

    def _lock(self, chat_id: int) -> asyncio.Lock:
        lock = self._locks.get(chat_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[chat_id] = lock
        return lock

    # ------------------------------------------------------------------- crida
    async def run(self, chat_id: int, text: str) -> AgentReply:
        async with self._lock(chat_id):
            return await self._run(chat_id, text)

    async def _run(self, chat_id: int, text: str) -> AgentReply:
        context = ToolContext(
            ha=self._ha,
            settings=self._settings,
            reminders=self._reminders,
            chat_id=chat_id,
        )
        contents: list[types.Content] = list(self._histories.get(chat_id, []))
        contents.append(
            types.Content(role="user", parts=[types.Part.from_text(text=text)])
        )

        reply_text = ""
        for _ in range(MAX_TOOL_ROUNDS):
            response = await self._generate(contents)
            calls = list(response.function_calls or [])

            if not calls:
                reply_text = self._extract_text(response)
                break

            candidate = response.candidates[0] if response.candidates else None
            if candidate is not None and candidate.content is not None:
                contents.append(candidate.content)

            parts: list[types.Part] = []
            for call in calls:
                log.info("Eina sol·licitada: %s %s", call.name, call.args)
                result = await execute_tool(context, call.name or "", dict(call.args or {}))
                parts.append(
                    types.Part.from_function_response(
                        name=call.name, response={"result": result}
                    )
                )
            contents.append(types.Content(role="user", parts=parts))
        else:
            reply_text = (
                "No he pogut acabar l'operació en els passos previstos. "
                "Torna-ho a provar o dona'm més detalls."
            )

        if reply_text:
            self._remember(chat_id, text, reply_text)
        return AgentReply(text=reply_text or "Fet.", pending=context.pending)

    async def _generate(self, contents: list[types.Content]) -> types.GenerateContentResponse:
        config = types.GenerateContentConfig(
            system_instruction=system_prompt(self._settings),
            tools=[self._tool],
            temperature=0.2,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        models = [self._settings.gemini_model]
        fallback = (self._settings.fallback_model or "").strip()
        if fallback and fallback != models[0]:
            models.append(fallback)

        last_error: Exception | None = None
        for model in models:
            for attempt in range(RETRIES):
                try:
                    response = await self._client.aio.models.generate_content(
                        model=model,
                        contents=contents,
                        config=config,
                    )
                except Exception as exc:  # errors de xarxa, quota o model
                    last_error = exc
                    quota = is_quota_error(exc)
                    log.warning(
                        "Crida a Gemini fallida amb %s (intent %d/%d): %s",
                        model,
                        attempt + 1,
                        RETRIES,
                        exc,
                    )
                    if quota:
                        # Reintentar no serveix: la quota és per model i projecte.
                        break
                    if attempt < RETRIES - 1:
                        await asyncio.sleep(1.5 * (attempt + 1))
                else:
                    if model != self._settings.gemini_model:
                        log.info(
                            "Resposta obtinguda amb el model alternatiu %s "
                            "(quota esgotada a %s).",
                            model,
                            self._settings.gemini_model,
                        )
                    return response
            else:
                continue

        assert last_error is not None
        raise last_error

    @staticmethod
    def _extract_text(response: types.GenerateContentResponse) -> str:
        try:
            text = response.text
            if text:
                return text.strip()
        except Exception:
            pass

        chunks: list[str] = []
        for candidate in response.candidates or []:
            content = candidate.content
            for part in (content.parts if content else None) or []:
                if getattr(part, "text", None):
                    chunks.append(part.text)
        return "\n".join(chunks).strip()

    def _remember(self, chat_id: int, user_text: str, reply_text: str) -> None:
        max_turns = self._settings.max_history_turns
        if max_turns <= 0:
            self._histories.pop(chat_id, None)
            return

        history = self._histories.setdefault(chat_id, [])
        history.append(types.Content(role="user", parts=[types.Part.from_text(text=user_text)]))
        history.append(types.Content(role="model", parts=[types.Part.from_text(text=reply_text)]))

        limit = max_turns * 2
        if len(history) > limit:
            del history[: len(history) - limit]

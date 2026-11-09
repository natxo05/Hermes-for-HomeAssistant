"""Bot de Telegram: text, veu, comandes i confirmacions."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import Settings
from .ha import HAError, HomeAssistant
from .llm import Agent
from .reminders import ReminderStore
from .stt import SpeechToText, TranscriptionError
from .tools import PendingAction, pop_pending
from .web import create_web_app

log = logging.getLogger(__name__)

MAX_MESSAGE = 4000
MAX_VOICE_SECONDS = 300
WEB_PORT = 8099


# --------------------------------------------------------------------- utilitats
def split_message(text: str, limit: int = MAX_MESSAGE) -> list[str]:
    text = (text or "").strip()
    if not text:
        return ["Fet."]

    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n"):
        candidate = f"{current}\n{paragraph}" if current else paragraph
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(paragraph) > limit:
            chunks.append(paragraph[:limit])
            paragraph = paragraph[limit:]
        current = paragraph
    if current:
        chunks.append(current)
    return chunks or [text[:limit]]


def is_authorized(update: Update, settings: Settings) -> bool:
    user = update.effective_user
    if user is None:
        return False
    return user.id in settings.allowed_user_ids


async def deny(update: Update) -> None:
    user = update.effective_user
    message = update.effective_message
    if message is None:
        return
    identifier = f"{user.id}" if user else "desconegut"
    await message.reply_text(
        f"🔒 No tens accés a aquest assistent.\n\nEl teu ID d'usuari de Telegram és {identifier}.\n"
        "Afegeix-lo a l'opció 'allowed_user_ids' de l'add-on i reinicia'l."
    )


# ---------------------------------------------------------------------- handlers
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    if not is_authorized(update, settings):
        await deny(update)
        return
    user = update.effective_user
    await update.effective_message.reply_text(
        f"Hola {user.first_name or ''}! 👋\n\n"
        "Sóc el teu assistent de Home Assistant. Escriu-me o envia'm una nota de veu i ho faré:\n"
        "· «Afegeix llet i pa a la compra»\n"
        "· «Cita amb el metge dijous a les 10»\n"
        "· «Recorda'm trucar a la Maria demà a les 9»\n"
        "· «Apaga els llums del menjador»\n"
        "· «Què hi ha a la compra?»\n\n"
        "Comandes: /status /reset /id /help"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    if not is_authorized(update, settings):
        await deny(update)
        return
    await update.effective_message.reply_text(
        "Pots parlar-me en llengua natural, per text o veu. Exemples:\n\n"
        "🛒 Compra: «Afegeix dos litres de llet», «Treu el pa», «Buitja el que ja està comprat»\n"
        "📅 Agenda: «Què tinc demà?», «Cita al dentista el 12 a les 17:30»\n"
        "⏰ Recordatoris: «Recorda'm posar la rentadora a les 20:00», «Quins recordatoris tinc?»\n"
        "💡 Casa: «Encén el llum de la cuina», «Posa el saló a 22 graus», «Activa l'escena nit»\n"
        "🌡️ Consultes: «A quina temperatura està el saló?», «Hi ha algú a casa?»\n\n"
        "Comandes: /status /reset /id"
    )


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    await update.effective_message.reply_text(
        f"ID d'usuari: {user.id if user else '?'}\nID de xat: {chat.id if chat else '?'}"
    )


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    if not is_authorized(update, settings):
        await deny(update)
        return
    agent: Agent = context.application.bot_data["agent"]
    agent.reset(update.effective_chat.id)
    await update.effective_message.reply_text("🧠 Conversa reiniciada.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    if not is_authorized(update, settings):
        await deny(update)
        return

    ha: HomeAssistant = context.application.bot_data["ha"]
    reminders: ReminderStore = context.application.bot_data["reminders"]
    stt: SpeechToText = context.application.bot_data["stt"]
    agent: Agent = context.application.bot_data["agent"]

    try:
        config = await ha.get_config()
        ha_line = f"✅ Connectat ({config.get('location_name') or 'Home Assistant'})"
    except HAError as exc:
        ha_line = f"❌ Sense connexió: {exc}"

    await update.effective_message.reply_text(
        f"{ha_line}\n"
        f"🧠 Model: {settings.gemini_model}\n"
        f"🎙️ Veu: faster-whisper {stt.model_name}\n"
        f"🌍 Zona horària: {settings.timezone}\n"
        f"⏰ Recordatoris actius: {reminders.count()}\n"
        f"💬 Missatges en memòria: {agent.history_size(update.effective_chat.id)}"
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    if not is_authorized(update, settings):
        await deny(update)
        return
    text = (update.effective_message.text or "").strip()
    if text:
        await respond(context, update.effective_message, text)


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    if not is_authorized(update, settings):
        await deny(update)
        return

    message = update.effective_message
    media = message.voice or message.audio
    if media is None:
        return

    duration = getattr(media, "duration", 0) or 0
    if duration > MAX_VOICE_SECONDS:
        await message.reply_text(
            f"L'àudio és massa llarg ({int(duration)} s). Envia'n un de menys de "
            f"{MAX_VOICE_SECONDS // 60} minuts."
        )
        return

    stt: SpeechToText = context.application.bot_data["stt"]
    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
    try:
        file = await context.bot.get_file(media.file_id)
        raw = bytes(await file.download_as_bytearray())
        transcript = await stt.transcribe(raw, getattr(media, "mime_type", None))
    except TranscriptionError as exc:
        await message.reply_text(f"No he pogut transcriure l'àudio: {exc}")
        return
    except Exception:
        log.exception("Error transcrivint l'àudio")
        await message.reply_text("No he pogut transcriure l'àudio. Torna-ho a provar.")
        return

    if not transcript:
        await message.reply_text("No he entès res a l'àudio. Torna-ho a enviar o escriu-m'ho.")
        return

    await message.reply_text(f"🎤 {transcript}")
    await respond(context, message, transcript)


async def respond(
    context: ContextTypes.DEFAULT_TYPE, message: Any, text: str
) -> None:
    agent: Agent = context.application.bot_data["agent"]
    runtime = context.application.bot_data["runtime"]

    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
    started = time.monotonic()
    try:
        reply = await agent.run(message.chat_id, text)
    except Exception as exc:
        runtime.errors += 1
        runtime.last_error = str(exc)
        log.exception("Error del model")
        await message.reply_text(
            "Ho sento, ara mateix no puc processar-ho. Torna-ho a provar d'aquí una estona."
        )
        return

    runtime.messages += 1
    log.info("Resposta generada en %.1f s", time.monotonic() - started)

    for chunk in split_message(reply.text):
        await message.reply_text(chunk)
    await send_confirmations(message, reply.pending)


async def send_confirmations(message: Any, pending: list[PendingAction]) -> None:
    for action in pending[:3]:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Sí, fes-ho", callback_data=f"ok:{action.id}"),
                    InlineKeyboardButton("❌ Cancel·la", callback_data=f"no:{action.id}"),
                ]
            ]
        )
        await message.reply_text(
            f"Vols que executi «{action.summary}»?", reply_markup=keyboard
        )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    if update.effective_user is None or update.effective_user.id not in settings.allowed_user_ids:
        await query.edit_message_text("🔒 No tens accés a aquesta acció.")
        return

    action_name, _, action_id = (query.data or "").partition(":")
    action = pop_pending(action_id)
    if action is None:
        await query.edit_message_text("Aquesta acció ja no és vàlida.")
        return

    if action_name != "ok":
        await query.edit_message_text(f"❌ Cancel·lat: {action.summary}")
        return

    ha: HomeAssistant = context.application.bot_data["ha"]
    try:
        await ha.call_service(action.domain, action.service, action.data)
    except HAError as exc:
        await query.edit_message_text(f"❌ No s'ha pogut executar: {exc}")
        return
    await query.edit_message_text(f"✅ Fet: {action.summary}")


# ---------------------------------------------------------------- aplicació
def build_application(
    settings: Settings,
    ha: HomeAssistant,
    agent: Agent,
    reminders: ReminderStore,
    stt: SpeechToText,
    runtime: Any,
) -> Application:
    application = (
        ApplicationBuilder()
        .token(settings.telegram_token)
        .concurrent_updates(True)
        .build()
    )
    application.bot_data.update(
        {
            "settings": settings,
            "ha": ha,
            "agent": agent,
            "reminders": reminders,
            "stt": stt,
            "runtime": runtime,
        }
    )

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("id", cmd_id))
    application.add_handler(CommandHandler("reset", cmd_reset))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, on_voice))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, on_text)
    )
    application.add_handler(CallbackQueryHandler(on_callback))

    application.post_init = _make_post_init(application, settings, ha, reminders, stt, runtime)
    application.post_shutdown = _make_post_shutdown(application, ha, runtime)
    return application


def _make_post_init(
    application: Application,
    settings: Settings,
    ha: HomeAssistant,
    reminders: ReminderStore,
    stt: SpeechToText,
    runtime: Any,
):
    async def post_init(app: Application) -> None:
        try:
            config = await ha.get_config()
            if settings.timezone_auto:
                settings.timezone = str(config.get("time_zone") or settings.timezone)
            log.info(
                "Connectat a Home Assistant '%s' (zona horària %s)",
                config.get("location_name") or "?",
                settings.timezone,
            )
        except HAError:
            log.exception("No puc llegir la configuració de Home Assistant")

        if not settings.allowed_user_ids:
            log.warning(
                "allowed_user_ids és buit: cap usuari no podrà fer servir el bot. "
                "Envia-li un missatge i el bot et dirà el teu ID."
            )

        runner = None
        try:
            from aiohttp import web

            runner = web.AppRunner(create_web_app(runtime.status))
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", WEB_PORT)
            await site.start()
            runtime.web_runner = runner
            log.info("Panell d'estat disponible al port %d", WEB_PORT)
        except Exception:
            log.exception("No he pogut aixecar el servidor web d'estat")

        async def sender(chat_id: int, text: str) -> None:
            await app.bot.send_message(chat_id=chat_id, text=text)

        runtime.reminder_task = asyncio.create_task(reminders.loop(sender))
        asyncio.create_task(stt.preload())

        if settings.startup_message:
            for chat_id in settings.allowed_user_ids:
                try:
                    await app.bot.send_message(
                        chat_id=chat_id,
                        text=f"🤖 Hermes engegat (model {settings.gemini_model}).",
                    )
                except Exception:
                    log.warning("No he pogut enviar el missatge d'inici a %s", chat_id)

    return post_init


def _make_post_shutdown(application: Application, ha: HomeAssistant, runtime: Any):
    async def post_shutdown(app: Application) -> None:
        task = runtime.reminder_task
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        if runtime.web_runner is not None:
            await runtime.web_runner.cleanup()
        await ha.close()

    return post_shutdown

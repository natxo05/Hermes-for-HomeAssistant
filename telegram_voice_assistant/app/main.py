import os
import tempfile
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from transcriber import Transcriber
from classifier import Classifier
from ha_client import HAClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CALENDAR_ENTITY = os.environ["CALENDAR_ENTITY"]
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "tiny")
LANGUAGE = os.environ.get("LANGUAGE", "ca")

SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN")
if SUPERVISOR_TOKEN:
    HA_URL = "http://supervisor/core"
    HA_TOKEN = SUPERVISOR_TOKEN
    logger.info("Usant Supervisor API (add-on mode)")
else:
    HA_URL = os.environ.get("HA_URL", "http://localhost:8123")
    HA_TOKEN = os.environ.get("HA_TOKEN", "")
    logger.info("Usant connexió directa (standalone mode)")

transcriber = Transcriber(
    model_size=WHISPER_MODEL,
    device="cpu",
    compute_type="int8",
)
classifier = Classifier(language=LANGUAGE)
ha = HAClient(
    url=HA_URL,
    token=HA_TOKEN,
    calendar_entity=CALENDAR_ENTITY,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hola! Envia'm una nota de veu i jo m'encarregaré:\n"
        "- Si és per la compra → l'afegiré a la llista de la compra de Home Assistant\n"
        "- Si és una cita mèdica → la crearé al calendari de Home Assistant"
    )


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("Descarregant la nota de veu...")

    voice = update.message.voice
    file = await voice.get_file()

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        await file.download_to_drive(tmp.name)
        audio_path = tmp.name

    try:
        await msg.edit_text("Transcrivint la veu...")
        text = transcriber.transcribe(audio_path)
        logger.info(f"Text transcrit: {text}")

        if not text.strip():
            await msg.edit_text("No he pogut entendre la nota de veu. Prova de nou.")
            return

        await msg.edit_text(f"Analitzant: \"{text}\"")
        result = classifier.classify(text)

        if result.category == "shopping":
            await msg.edit_text(f"Afegint a la llista de la compra: {text}")
            success = await ha.add_shopping_item(text)
            if success:
                await msg.edit_text(f"Afegit a la llista de la compra:\n\"{text}\"")
            else:
                await msg.edit_text("Error en afegir a la llista de la compra")

        elif result.category == "appointment":
            await msg.edit_text(f"Creant cita al calendari: {text}")
            success = await ha.create_calendar_event(
                summary=text,
                dt=result.entities.get("date"),
                place=result.entities.get("place"),
                doctor=result.entities.get("doctor"),
            )
            if success:
                reply = f"Cita creada al calendari:\n\"{text}\""
                if result.entities.get("date"):
                    reply += f"\nData: {result.entities['date'].strftime('%d/%m/%Y %H:%M')}"
                await msg.edit_text(reply)
            else:
                await msg.edit_text("Error en crear la cita al calendari")

    except Exception as e:
        logger.exception("Error processant la nota de veu")
        await msg.edit_text(f"Error: {e}")

    finally:
        try:
            os.unlink(audio_path)
        except Exception:
            pass


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    await update.message.reply_text(f"He rebut: \"{text}\"\n\nEnvia'm una nota de veu per processar-la!")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot iniciat! Esperant missatges...")
    app.run_polling()


if __name__ == "__main__":
    main()

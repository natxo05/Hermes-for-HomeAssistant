from faster_whisper import WhisperModel
import logging

logger = logging.getLogger(__name__)


class Transcriber:
    def __init__(self, model_size: str = "tiny", device: str = "cpu", compute_type: str = "int8"):
        logger.info(f"Carregant model Whisper {model_size} ({device}, {compute_type})...")
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        logger.info("Model carregat correctament")

    def transcribe(self, audio_path: str) -> str:
        segments, info = self.model.transcribe(audio_path, beam_size=5)
        text = " ".join([seg.text.strip() for seg in segments])
        logger.info(f"Transcrit: {text}")
        return text

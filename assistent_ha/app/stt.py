"""Transcripció de veu amb faster-whisper (local, sense API externa)."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from .config import Settings

log = logging.getLogger(__name__)

_EXTENSIONS = {
    "audio/ogg": ".ogg",
    "audio/opus": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/webm": ".webm",
    "video/ogg": ".ogg",
}


class TranscriptionError(RuntimeError):
    pass


def _check_cpu_support() -> None:
    """Avís clar si la CPU no pot executar faster-whisper (típic en VMs amb CPU genèrica)."""
    import platform

    if platform.machine().lower() not in {"x86_64", "amd64"}:
        return
    try:
        cpuinfo = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    flags: set[str] = set()
    for line in cpuinfo.splitlines():
        if line.lower().startswith("flags"):
            flags.update(line.split(":", 1)[1].split())
    if flags and "sse4_1" not in flags:
        raise TranscriptionError(
            "aquest processador no té SSE4.1, que faster-whisper necessita. "
            "Si Home Assistant corre en una màquina virtual, canvia el tipus de CPU a "
            "'host' (Proxmox: Màquina → Maquinari → Processadors → Tipus: host)."
        )


class SpeechToText:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = None
        self._lock = asyncio.Lock()

    @property
    def model_name(self) -> str:
        return self._settings.whisper_model

    async def preload(self) -> None:
        try:
            await self._ensure_model()
            log.info("Model de veu carregat: %s", self.model_name)
        except Exception:
            log.exception(
                "No he pogut carregar el model de veu '%s'. La transcripció fallarà fins que es pugui descarregar.",
                self.model_name,
            )

    async def _ensure_model(self):
        if self._model is not None:
            return self._model
        async with self._lock:
            if self._model is not None:
                return self._model
            self._model = await asyncio.to_thread(self._load_model)
        return self._model

    def _load_model(self):
        _check_cpu_support()
        try:
            from faster_whisper import WhisperModel  # import pesat, només quan cal
        except Exception as exc:  # numpy incompatible, falta una llibreria, etc.
            raise TranscriptionError(
                "no es pot carregar el motor de veu en aquest equip "
                f"({type(exc).__name__}: {exc}). Consulta el registre de l'add-on."
            ) from exc

        log.info(
            "Carregant faster-whisper '%s' (compute_type=%s)...",
            self._settings.whisper_model,
            self._settings.whisper_compute_type,
        )
        return WhisperModel(
            self._settings.whisper_model,
            device="cpu",
            compute_type=self._settings.whisper_compute_type,
            download_root=str(self._settings.models_dir),
        )

    async def transcribe(self, audio: bytes, mime_type: str | None = None) -> str:
        if not audio:
            raise TranscriptionError("L'àudio és buit.")
        model = await self._ensure_model()
        suffix = _EXTENSIONS.get((mime_type or "").lower(), ".ogg")

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(audio)
            temp_path = Path(handle.name)

        try:
            return await asyncio.to_thread(self._run, model, temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

    def _run(self, model, path: Path) -> str:
        segments, info = model.transcribe(
            str(path),
            language=self._settings.language or None,
            vad_filter=True,
            beam_size=5,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        log.info(
            "Transcripció (%.1f s d'àudio, llengua %s): %s",
            getattr(info, "duration", 0.0),
            getattr(info, "language", "?"),
            text[:200],
        )
        return text

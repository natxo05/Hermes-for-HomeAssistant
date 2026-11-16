"""Hermes: bot de Telegram amb veu i LLM per a Home Assistant."""

import os

# Versió del codi. Dins del contenidor mana HERMES_VERSION, que el Dockerfile
# omple amb la versió real de l'add-on (BUILD_VERSION del Supervisor).
__version__ = "0.1.3"


def get_version() -> str:
    """Versió real de l'add-on en execució."""
    return os.environ.get("HERMES_VERSION", "").strip() or __version__

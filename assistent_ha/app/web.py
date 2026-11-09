"""Petit servidor web per a l'estat de l'add-on i el watchdog."""

from __future__ import annotations

import html
from typing import Any, Callable

from aiohttp import web


def _render(status: dict[str, Any]) -> str:
    rows = "\n".join(
        f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>"
        for key, value in status.items()
    )
    return f"""<!doctype html>
<html lang="ca">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hermes</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; margin: 0; padding: 24px; }}
  h1 {{ font-size: 1.3rem; margin: 0 0 16px; }}
  table {{ border-collapse: collapse; width: 100%; max-width: 640px; }}
  th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid rgba(128,128,128,.3); }}
  th {{ font-weight: 600; width: 40%; }}
  p {{ color: #888; font-size: .85rem; }}
</style>
</head>
<body>
<h1>🤖 Hermes</h1>
<table>{rows}</table>
<p>Envia missatges al bot de Telegram per fer-lo servir.</p>
</body>
</html>"""


def create_web_app(status_provider: Callable[[], dict[str, Any]]) -> web.Application:
    app = web.Application()

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def index(_: web.Request) -> web.Response:
        try:
            status = status_provider()
        except Exception as exc:  # pragma: no cover
            return web.Response(status=500, text=f"Error: {exc}")
        return web.Response(text=_render(status), content_type="text/html")

    app.router.add_get("/health", health)
    app.router.add_get("/", index)
    return app

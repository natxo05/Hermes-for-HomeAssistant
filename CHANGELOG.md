# Changelog

## 0.1.2

- Fix de la transcripció en CPUs antics o màquines virtuals: NumPy es fixa a `<2.4`,
  perquè les versions 2.4+ exigeixen `x86-64-v2` (SSE4.2 + POPCNT) i fallen amb
  `RuntimeError: NumPy was built with baseline optimizations: (X86_V2)`.
- Missatge d'error de veu més clar quan el model no es pot carregar.

## 0.1.1

- Model per defecte actualitzat a `gemini-3.8-flash`: `gemini-2.5-flash` està obsolet i
  a partir de l'1 de desembre de 2026 les peticions es redirigeixen automàticament.
- Imatge precompilada de GHCR activada per defecte (actualitzacions molt més ràpides).

## 0.1.0

Primera versió.

- Bot de Telegram amb text i notes de veu (transcripció local amb faster-whisper).
- Interpretació en llengua natural amb Gemini i *function calling*.
- Llista de la compra: afegir, treure, consultar i buidar llistes `todo`.
- Agenda: crear i consultar esdeveniments als calendaris de Home Assistant.
- Recordatoris propis persistents amb avís per Telegram.
- Control d'entitats: llums, interruptors, clima, persianes, escenes, scripts i media players.
- Consultes d'estat i cerca d'entitats.
- Confirmació amb botons per a accions sensibles (`lock`, `alarm_control_panel`, `cover`).
- Panell d'estat via ingress i endpoint `/health` per al watchdog.

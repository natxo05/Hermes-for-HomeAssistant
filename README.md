# Hermes · repositori d'add-ons

[![Obre la teva instància de Home Assistant i mostra el diàleg per afegir un repositori d'add-ons amb una URL concreta.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fnatxo05%2FHermes-for-HomeAssistant)

Repositori d'add-ons de Home Assistant que conté **Hermes**: un assistent personal per
Telegram (text i veu) que entén llengua natural i executa accions reals a casa.

| Add-on | Descripció |
| --- | --- |
| [`assistent_ha`](assistent_ha/) | Assistent per Telegram amb Gemini, faster-whisper local, llista de la compra, agenda, recordatoris i control de dispositius. |

## Instal·lació

1. Clica el badge de dalt (o ves a **Configuració → Add-ons → Botiga → ⋮ → Repositoris** i afegeix
   `https://github.com/natxo05/Hermes-for-HomeAssistant`).
2. Instal·la **Hermes** des de la secció *Hermes* de la botiga.
3. Obre **Configuració** i omple `telegram_token`, `gemini_api_key` i `allowed_user_ids`.
4. Inicia l'add-on.

Detalls complets a [`assistent_ha/README.md`](assistent_ha/README.md).

## Actualitzar l'add-on

El repositori és la font de la veritat: Home Assistant clona aquest repo i, si no hi ha cap
imatge publicada, **compila l'add-on al dispositiu** amb el `Dockerfile`.

1. Fes els canvis dins `assistent_ha/`.
2. **Puja la versió** a `assistent_ha/config.yaml` (per exemple `version: "0.2.0"`).
3. Fes commit i push a `main`.
4. A Home Assistant: **Configuració → Add-ons → Botiga → ⋮ → Comprova les actualitzacions**.
5. L'add-on mostrarà **Actualitza**. No cal reiniciar Home Assistant.

La versió és el que Home Assistant compara: **si no la puges, no veurà cap actualització**.
També és l'etiqueta de la imatge, així que mai reutilitzis una versió ja publicada.

### Imatges precompilades (opcional, més ràpid)

Compilar al dispositiu funciona, però en una Raspberry Pi cada actualització triga uns minuts.
El workflow [`.github/workflows/build.yaml`](.github/workflows/build.yaml) compila la imatge per a
`amd64` i `aarch64` i la publica a GitHub Container Registry.

Per activar-lo:

1. Fes push del repositori a GitHub (el workflow s'executa sol en tocar `assistent_ha/**`).
2. Espera que acabi l'acció **Build add-on image**.
3. A GitHub: **Packages → hermes → Package settings → Change visibility → Public**.
   Sense això Home Assistant no podrà descarregar-la.
4. Descomenta `image:` a `assistent_ha/config.yaml` i posa el teu usuari:

   ```yaml
   image: "ghcr.io/natxo05/hermes"
   ```

   O executa `.\scripts\configure.ps1 -Owner EL_TEU_USUARI -UsePrebuiltImages`.

A partir d'aquí, Home Assistant descarrega la imatge en comptes de compilar-la. Les
actualitzacions segueixen el mateix flux: puja la versió, push, i *Comprova les actualitzacions*.

## Estructura

```text
repository.yaml              defineix aquest repositori d'add-ons
.github/workflows/build.yaml compila i publica les imatges multi-arquitectura
scripts/configure.ps1        omple els placeholders natxo05 / hermes-for-homeassistant
assistent_ha/
  config.yaml                definició de l'add-on (opcions i esquema)
  Dockerfile                 imatge python:3.12-slim + dependències
  requirements.txt
  DOCS.md                    documentació que es veu a Home Assistant
  app/                       codi de l'assistent
  translations/              textos de la configuració (ca, en)
```

## Desenvolupament

El codi és Python pur; no cal Home Assistant per provar la lògica:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r assistent_ha/requirements.txt

set TELEGRAM_TOKEN=...
set GEMINI_API_KEY=...
set HA_URL=http://192.168.1.10:8123/api
set HA_TOKEN=...
set ASSISTANT_DATA_DIR=.\data
python -m app.main
```

`HA_URL` i `HA_TOKEN` només calen fora de l'add-on; dins de Home Assistant s'utilitza el
`SUPERVISOR_TOKEN` intern.

## Llicència

Fes servir el codi com vulguis. Els models de Gemini i les API de Telegram tenen les seves
pròpies condicions.

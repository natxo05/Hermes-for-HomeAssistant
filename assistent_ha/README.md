# Hermes

Assistent personal per a **Home Assistant** que s'utilitza des de **Telegram**, per text o per veu.
Entén llengua natural (català, castellà, anglès…) i executa accions reals a casa teva.

```
Telèfon ──► Telegram ──► Add-on ──► Gemini (decideix l'acció)
                                   ├─► Home Assistant (llista de la compra, calendaris, llums, sensors…)
                                   └─► Recordatoris propis ──► Telegram
                          ▲
                   faster-whisper (àudio → text, local)
```

## Què sap fer

| Àrea | Exemples |
| --- | --- |
| 🛒 Llista de la compra | «Afegeix llet i pa», «Treu els ous», «Què falta?», «Buitja el que ja està comprat» |
| 📅 Agenda | «Cita amb el metge dijous a les 10», «Què tinc demà?», «Mou la cita de divendres a les 16» |
| ⏰ Recordatoris | «Recorda'm trucar a la Maria demà a les 9», «Quins recordatoris tinc?» |
| 💡 Control | «Encén el llum de la cuina», «Posa el saló a 22 graus», «Activa l'escena nit», «Baixa la persiana al 30%» |
| 🌡️ Consultes | «A quina temperatura està el saló?», «Hi ha algú a casa?», «Quant marca el comptador?» |

També entén **notes de veu**: es transcriuen al mateix dispositiu amb `faster-whisper`, sense enviar
l'àudio a cap servei extern.

## Requisits

- Home Assistant **OS** o **Supervised** (els add-ons no existeixen a HA Container/Core).
- Un bot de Telegram (2 minuts amb [@BotFather](https://t.me/BotFather)).
- Una clau de l'API de Gemini, gratuïta a [Google AI Studio](https://aistudio.google.com/apikey).
- ~1 GB de RAM lliures per al model de veu `small` (amb `base` en va amb la meitat).

## Instal·lació

1. Afegeix aquest repositori a Home Assistant: **Configuració → Add-ons → Botiga → ⋮ → Repositoris**
   i enganxa la URL del repositori (o clica el badge del `README.md` principal).
2. Instal·la **Hermes** i obre la pestanya **Configuració**.
3. Omple com a mínim `telegram_token`, `gemini_api_key` i `allowed_user_ids`.
4. **Inicia** l'add-on i mira el registre: ha de dir «Connectat a Home Assistant».

### Treure el teu ID de Telegram

Si encara no el saps: deixa `allowed_user_ids` buit, envia un missatge al bot i et respondrà
amb el teu ID. Afegeix-lo a la configuració i reinicia l'add-on.

### Crear el bot

1. Obre [@BotFather](https://t.me/BotFather) → `/newbot` → tria nom i usuari.
2. Copia el token (`123456789:AAF...`) a l'opció `telegram_token`.
3. Obre el xat amb el teu bot i envia `/start`.

## Actualitzacions

Home Assistant comprova el repositori quan li ho demanes. Per actualitzar:

1. Es publica una versió nova al repositori (o la publiques tu, si és el teu fork).
2. A Home Assistant: **Botiga → ⋮ → Comprova les actualitzacions**.
3. Apareix el botó **Actualitza** a l'add-on.

Les dades de `/data` (configuració, recordatoris i models de veu) es conserven entre actualitzacions.

## Configuració

| Opció | Per defecte | Descripció |
| --- | --- | --- |
| `telegram_token` | — | Token de @BotFather (obligatori). |
| `allowed_user_ids` | `[]` | IDs de Telegram autoritzats. **Si és buit, ningú no hi pot accedir.** |
| `gemini_api_key` | — | Clau de Gemini (obligatòria). |
| `gemini_model` | `gemini-3.8-flash` | `gemini-3.5-flash-lite` és més barat; `gemini-4-hydrogen` raona millor i costa més. |
| `whisper_model` | `small` | `tiny`, `base`, `small`, `medium`, `large-v3`. |
| `whisper_compute_type` | `int8` | `int8` (ràpid), `float32` (precís i lent). |
| `language` | `ca` | Idioma de la transcripció; buit = detecció automàtica. |
| `shopping_list_entity` | `todo.shopping_list` | Llista per defecte. |
| `calendar_entity` | `calendar.personal` | Calendari per defecte. |
| `timezone` | buit | Buit = la de Home Assistant. |
| `max_history_turns` | `12` | Intercanvis recordats per xat (0 = sense memòria). |
| `confirm_domains` | `lock`, `alarm_control_panel`, `cover` | Dominis on obrir/desbloquejar demana confirmació. |
| `startup_message` | `true` | Avisa per Telegram quan arrenca. |
| `debug` | `false` | Registre detallat. |

### Si els noms per defecte no existeixen

No cal encertar-los: si `shopping_list_entity` o `calendar_entity` no existeixen, l'assistent
agafa la primera llista o calendari disponible. També pots dir-li «afegeix-ho a la llista del
mercat» i triarà la llista que coincideixi pel nom.

## Seguretat

- El bot **només** respon als IDs de `allowed_user_ids`. Qualsevol altre usuari rep el seu ID i res més.
- Les accions potencialment perilloses sobre els dominis de `confirm_domains`
  (`unlock`, `open`, `set_position`…) es confirmen amb un botó ✅/❌ abans d'executar-se.
- El token de Home Assistant no es desa enlloc: l'add-on fa servir el `SUPERVISOR_TOKEN` intern.
- L'àudio no surt de casa; només el text transcrit s'envia a Gemini.

## Desenvolupament local

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

`HA_URL` i `HA_TOKEN` substitueixen el `SUPERVISOR_TOKEN` quan s'executa fora de l'add-on. El token
de llarga durada es crea a **Perfil → Seguretat → Tokens d'accés de llarga durada**.

Estructura del projecte:

```
config.yaml          definició de l'add-on (opcions i esquema)
Dockerfile           imatge python:3.12-slim + dependències
app/config.py        opcions, validació i rutes de dades
app/ha.py            client REST de Home Assistant
app/tools.py         eines del model + confirmacions
app/llm.py           bucle d'agent amb Gemini
app/telegram_bot.py  handlers de text, veu, comandes i botons
app/reminders.py     planificador de recordatoris persistent
app/stt.py           transcripció amb faster-whisper
app/web.py           /health i panell d'estat (ingress)
```

## Limitacions conegudes

- Els recordatoris viuen a `/data/reminders.json` de l'add-on: si el desinstal·les, es perden.
- Els calendaris amb esdeveniments de tot el dia depenen del backend de calendari que facis servir.
- El desbloqueig de panys que demanen codi numèric no està implementat (caldria desar el codi).
- La memòria de conversa és en RAM: es perd en reiniciar l'add-on.

## Properes passes possibles

- Enviar fotos i preguntar què hi ha a la nevera (Gemini Vision).
- Resum diari de l'agenda i la compra a una hora fixa.
- Integració amb Assist per veu des dels altaveus de casa.
- Suport de codi PIN per a panys i alarmes.

# Hermes

Assistent personal per Telegram (text i veu) connectat a Home Assistant.

## Instal·lació

1. Afegeix aquest repositori a Home Assistant (**Botiga → ⋮ → Repositoris**) i instal·la
   **Hermes**.
2. Obre **Configuració** i omple `telegram_token`, `gemini_api_key` i `allowed_user_ids`.
3. Inicia l'add-on.

Per obtenir el teu ID de Telegram: deixa `allowed_user_ids` buit, envia un missatge al bot
i et respondrà amb el número que has d'afegir.

## Configuració ràpida

```yaml
telegram_token: "123456789:AAF..."
allowed_user_ids:
  - 123456789
gemini_api_key: "AIza..."
gemini_model: gemini-3.8-flash
whisper_model: small
language: ca
shopping_list_entity: todo.shopping_list
calendar_entity: calendar.personal
```

La resta d'opcions tenen valors raonables per defecte.

## Ús

Escriu o envia una nota de veu al bot:

- «Afegeix llet, pa i ous a la compra»
- «Cita amb el dentista el 12 de març a les 17:30»
- «Recorda'm posar la rentadora a les 20:00»
- «Apaga tots els llums del menjador»
- «Què tinc demà a l'agenda?»

Comandes: `/start`, `/help`, `/status`, `/reset`, `/id`.

Les accions sensibles (obrir persianes, desbloquejar panys) demanen confirmació amb un botó.

## Resolució de problemes

**El bot no respon**
Comprova que `allowed_user_ids` conté el teu ID i mira el registre de l'add-on.

**«No he pogut transcriure l'àudio»**
La primera transcripció descarrega el model (diversos minuts). Si falla, prova `whisper_model: base`
o revisa l'espai lliure.

**«No trobo la llista/calendari»**
Revisa que l'entitat existeixi a Home Assistant i que el nom a `shopping_list_entity` /
`calendar_entity` sigui l'`entity_id` complet (`todo.xxx`, `calendar.xxx`).

**Gemini retorna error 429**
Has superat la quota gratuïta. Espera una estona o canvia de model a `gemini-3.5-flash-lite`.

**El panell lateral no carrega**
L'add-on ha d'estar iniciat; el panell escolta al port intern 8099 i es publica via ingress.

**L'add-on no s'actualitza**
La versió de `config.yaml` ha d'haver pujat. A la botiga, fes **⋮ → Comprova les actualitzacions**.

## Registre

El registre de l'add-on mostra cada eina que el model decideix executar, la transcripció de la
veu i els errors. Activa `debug: true` per a més detall.

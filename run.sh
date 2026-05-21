#!/usr/bin/with-contenv bashio

CONFIG_PATH=/data/options.json

TELEGRAM_TOKEN=$(bashio::config 'telegram_token')
CALENDAR_ENTITY=$(bashio::config 'calendar_entity')
WHISPER_MODEL=$(bashio::config 'whisper_model')
LANGUAGE=$(bashio::config 'language')

export TELEGRAM_TOKEN
export CALENDAR_ENTITY
export WHISPER_MODEL
export LANGUAGE

exec python3 /app/main.py

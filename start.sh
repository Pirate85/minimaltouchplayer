#!/usr/bin/env bash
# Startet den Musik-Player.
# Optionales Audio-Gerät erzwingen (falls leise/stumm):
#   MUSIKPLAYER_DEVICE=pipewire ./start.sh
cd "$(dirname "$0")"
exec python3 musicplayer.py

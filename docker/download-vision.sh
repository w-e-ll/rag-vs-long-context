#!/bin/sh
set -eu
# Dedicated one-off downloader: public weights only, no application data or keys.
ollama serve >/dev/null 2>&1 &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true' EXIT INT TERM
attempt=0
until ollama list >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    [ "$attempt" -lt 30 ] || exit 1
    sleep 1
done
ollama pull qwen2.5vl:3b

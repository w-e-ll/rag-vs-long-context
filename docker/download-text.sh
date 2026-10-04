#!/bin/sh
set -eu
# Only public weights and the dedicated model volume are accessible here.
ollama serve >/dev/null 2>&1 &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true' EXIT INT TERM
attempt=0
until ollama list >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    [ "$attempt" -lt 30 ] || exit 1
    sleep 1
done
ollama pull llama3.2:3b
ollama pull nomic-embed-text

#!/usr/bin/env bash
set -euo pipefail
cd /opt/lifehub
if ! curl --fail --silent --show-error --max-time 15 http://127.0.0.1:8000/health >/dev/null; then
  echo 'Health check failed; restarting the LifeHub container.'
  docker compose restart lifehub
  sleep 10
  curl --fail --silent --show-error --max-time 15 http://127.0.0.1:8000/health >/dev/null
fi

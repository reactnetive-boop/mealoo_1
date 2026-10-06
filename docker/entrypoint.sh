#!/bin/sh
# api        - run migrations once, then serve (RUN_SCHEDULER should be false)
# scheduler  - run the background jobs only (exactly one replica)
set -eu

case "${1:-api}" in
  api)
    if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
      alembic upgrade head
    fi
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
      --workers "${WEB_CONCURRENCY:-2}" --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
      --no-server-header
    ;;
  scheduler)
    # The FastAPI lifespan starts the scheduler when RUN_SCHEDULER=true; the
    # app is bound to localhost only, it never takes public traffic.
    export RUN_SCHEDULER=true
    exec uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}" --workers 1 --no-server-header
    ;;
  *)
    exec "$@"
    ;;
esac

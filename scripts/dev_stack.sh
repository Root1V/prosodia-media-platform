#!/usr/bin/env bash
# Levanta, para o inspecciona el stack de desarrollo de Prosodia Web
# (postgres + redis + API + worker + frontend) en una maquina local.
#
# POR QUE EXISTE ESTE SCRIPT, y no un par de comandos sueltos en el README:
#
# 1. Las identidades de telemetria se pasan POR PROCESO, no en .env. La API y
#    el worker comparten codigo y solo se distinguen al arrancar, asi que
#    OTEL_SERVICE_NAME/OTEL_RESOURCE_ATTRIBUTES no pueden vivir en el fichero
#    de entorno. Olvidarlas no da ningun error: los dos servicios exportan
#    igual, bajo el nombre "unknown-service", y solo se nota mirando la linea
#    de argus.init del arranque. Ya costo una corrida de doblaje entera.
#
# 2. Los procesos quedan DESLIGADOS de la terminal (nohup + disown; `setsid`
#    no existe en macOS). Lanzados desde una terminal que luego se cierra --
#    o desde un panel que los recicla -- se mueren sin avisar, y el sintoma es confuso: la pagina
#    carga pero el login falla, porque el frontend sigue en pie y proxea /api
#    a una API que ya no esta.
#
# 3. Los puertos no son los de por defecto. 5432 y 6379 se los lleva el primer
#    proyecto que arranca en la maquina, asi que este usa los de .env
#    (POSTGRES_PORT/REDIS_PORT) y la API el 8001, que es a donde apunta el
#    proxy de vite (ver frontend/vite.config.ts).
#
# Uso:
#   ./scripts/dev_stack.sh start     # levanta todo y espera a que responda
#   ./scripts/dev_stack.sh stop      # para API, worker y frontend
#   ./scripts/dev_stack.sh status    # que esta vivo y que no
#   ./scripts/dev_stack.sh logs api  # sigue el log de api|worker|frontend
#
# "stop" NO para postgres ni redis a proposito: son contenedores, tardan en
# arrancar y no estorban. Para pararlos: docker compose stop postgres redis

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT/.work/dev_stack"
API_PORT=8001
WEB_PORT=5173

mkdir -p "$RUN_DIR"

# --- helpers ---------------------------------------------------------------

puerto_ocupado() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

pid_de() { [ -f "$RUN_DIR/$1.pid" ] && cat "$RUN_DIR/$1.pid" || echo ""; }

vivo() {
  local pid
  pid="$(pid_de "$1")"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

# Arranca un servicio desligado de esta terminal: `nohup` lo hace inmune al
# SIGHUP del cierre y `disown` lo saca de la tabla de trabajos de la shell, asi
# que al salir este script el proceso queda adoptado por launchd en vez de
# morir con quien lo lanzo. (`setsid`, que seria lo limpio, no existe en macOS.)
arranca() {
  local nombre="$1"; shift
  if vivo "$nombre"; then
    echo "  $nombre ya estaba corriendo (pid $(pid_de "$nombre"))"
    return
  fi
  cd "$ROOT"
  nohup "$@" >"$RUN_DIR/$nombre.log" 2>&1 &
  local pid=$!
  echo "$pid" >"$RUN_DIR/$nombre.pid"
  disown "$pid" 2>/dev/null || true
  echo "  $nombre arrancado (pid $pid) -> .work/dev_stack/$nombre.log"
}

# Mata un proceso y toda su descendencia. Hace falta porque `uv run` y
# `npm run` no SON el servidor: lanzan un hijo que si lo es. Matar solo al
# padre deja al servidor real escuchando, el puerto ocupado, y el siguiente
# "start" fallando por un motivo que no se parece a la causa.
mata_arbol() {
  local pid="$1" hijo
  for hijo in $(pgrep -P "$pid" 2>/dev/null); do
    mata_arbol "$hijo"
  done
  kill -TERM "$pid" 2>/dev/null || true
}

espera_puerto() {
  local puerto="$1" nombre="$2" intentos=60
  while [ $intentos -gt 0 ]; do
    puerto_ocupado "$puerto" && { echo "  $nombre responde en :$puerto"; return 0; }
    sleep 1
    intentos=$((intentos - 1))
  done
  echo "  AVISO: $nombre no respondio en :$puerto -- mira .work/dev_stack/$nombre.log" >&2
  return 1
}

# --- comandos --------------------------------------------------------------

cmd_start() {
  echo "Base de datos y cola:"
  docker compose start postgres redis >/dev/null 2>&1 || docker compose up -d postgres redis >/dev/null
  echo "  postgres y redis arriba"

  echo "Procesos:"
  # Las dos identidades de telemetria, que es el motivo nº1 de este script.
  arranca api env \
    OTEL_SERVICE_NAME=prosodia-api \
    OTEL_RESOURCE_ATTRIBUTES=service.namespace=prosodia,argus.component.role=api,service.version=dev \
    uv run --env-file .env uvicorn video_translator.web.main:app --port "$API_PORT"

  arranca worker env \
    OTEL_SERVICE_NAME=prosodia-worker \
    OTEL_RESOURCE_ATTRIBUTES=service.namespace=prosodia,argus.component.role=worker,service.version=dev \
    uv run --env-file .env celery -A video_translator.web.tasks.celery_app worker \
    --loglevel=info --pool=solo

  arranca frontend npm --prefix frontend run dev

  echo "Esperando:"
  espera_puerto "$API_PORT" api || true
  espera_puerto "$WEB_PORT" frontend || true

  echo
  cmd_status
  echo
  echo "Abre http://localhost:$WEB_PORT"
}

cmd_stop() {
  for nombre in api worker frontend; do
    if vivo "$nombre"; then
      mata_arbol "$(pid_de "$nombre")"
      echo "  $nombre parado"
    else
      echo "  $nombre no estaba corriendo"
    fi
    rm -f "$RUN_DIR/$nombre.pid"
  done
  echo
  echo "postgres y redis siguen arriba. Para pararlos:"
  echo "  docker compose stop postgres redis"
}

cmd_status() {
  for nombre in api worker frontend; do
    if vivo "$nombre"; then
      printf '  %-9s vivo   (pid %s)\n' "$nombre" "$(pid_de "$nombre")"
    else
      printf '  %-9s CAIDO\n' "$nombre"
    fi
  done
  puerto_ocupado "$API_PORT" && printf '  :%s       responde\n' "$API_PORT" || printf '  :%s       SIN RESPUESTA\n' "$API_PORT"
  puerto_ocupado "$WEB_PORT" && printf '  :%s       responde\n' "$WEB_PORT" || printf '  :%s       SIN RESPUESTA\n' "$WEB_PORT"

  # La identidad de telemetria, que es lo que no avisa cuando falta.
  if [ -f "$RUN_DIR/api.log" ]; then
    local servicio
    servicio="$(grep -o '"service": "[^"]*"' "$RUN_DIR/api.log" | tail -1 | cut -d'"' -f4 || true)"
    [ -n "$servicio" ] && printf '  telemetria   la API arranco como "%s"\n' "$servicio"
  fi
}

cmd_logs() {
  local nombre="${1:-api}"
  tail -f "$RUN_DIR/$nombre.log"
}

case "${1:-}" in
  start)  cmd_start ;;
  stop)   cmd_stop ;;
  status) cmd_status ;;
  logs)   shift; cmd_logs "${1:-api}" ;;
  *)      echo "uso: $0 {start|stop|status|logs [api|worker|frontend]}" >&2; exit 2 ;;
esac

#!/usr/bin/env bash
# =============================================================================
# dev.sh — sobe backend (FastAPI/uvicorn) + frontend (Next.js) num único terminal.
#
# Uso:
#   ./dev.sh              # sobe os dois
#   Ctrl+C                # mata os dois e sai
#
# - Backend roda com --reload (recarrega ao salvar arquivos .py)
# - Frontend roda com next dev (turbopack)
# - Saídas misturadas no terminal, prefixadas por [BACKEND] / [FRONTEND]
# - Garante que ambos os processos sejam encerrados ao sair (trap EXIT)
# =============================================================================

set -u  # erro em var não definida (mas não -e: queremos seguir mesmo se um falhar)

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
VENV_BIN="$BACKEND_DIR/.venv/bin"

# Cores para os prefixos de log.
COLOR_BACKEND='\033[36m'   # ciano
COLOR_FRONTEND='\033[35m'  # magenta
COLOR_INFO='\033[33m'      # amarelo
COLOR_RESET='\033[0m'

log_info()    { echo -e "${COLOR_INFO}[dev.sh]${COLOR_RESET} $*"; }
log_error()   { echo -e "${COLOR_INFO}[dev.sh]${COLOR_RESET} \033[31mERRO:${COLOR_RESET} $*" >&2; }

# -----------------------------------------------------------------------------
# Pré-checks
# -----------------------------------------------------------------------------
if [ ! -d "$BACKEND_DIR" ] || [ ! -d "$FRONTEND_DIR" ]; then
  log_error "rodar a partir da raiz do projeto (que tem /backend e /frontend)"
  exit 1
fi
if [ ! -x "$VENV_BIN/uvicorn" ]; then
  log_error "venv do backend não encontrado em $VENV_BIN"
  log_error "rode: cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  log_info "node_modules ausente — rodando 'npm install' no frontend (1ª vez)"
  (cd "$FRONTEND_DIR" && npm install --no-audit --no-fund) || {
    log_error "npm install falhou"
    exit 1
  }
fi

# Libera portas se houver processos antigos travados (uvicorn em :8000 e
# next dev em :3000). Se sobrar um Next órfão de uma sessão anterior, o
# Next 16 detecta "another dev server in same dir" e aborta com exit=0,
# o que faria o `wait -n` matar o backend novo logo após subir.
for port in 8000 3000; do
  old_pids="$(lsof -ti:$port 2>/dev/null || true)"
  if [ -n "$old_pids" ]; then
    log_info "matando processo antigo na porta $port (PIDs: $old_pids)"
    echo "$old_pids" | xargs -r kill -9 2>/dev/null || true
  fi
done
# Mata também qualquer next-server órfão que tenha "esquecido" da porta
# (acontece quando o Ctrl+C anterior não pegou o grupo inteiro).
pkill -9 -f "next-server" 2>/dev/null || true
pkill -9 -f "next dev"   2>/dev/null || true
sleep 1

# -----------------------------------------------------------------------------
# Cleanup centralizado: trap encerra os dois processos ao sair de qualquer forma.
# -----------------------------------------------------------------------------
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  log_info "encerrando processos (Ctrl+C)..."
  # mata o grupo inteiro de cada processo (pega filhos descendentes também)
  if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill -TERM -- "-$BACKEND_PID" 2>/dev/null || kill -TERM "$BACKEND_PID" 2>/dev/null
  fi
  if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill -TERM -- "-$FRONTEND_PID" 2>/dev/null || kill -TERM "$FRONTEND_PID" 2>/dev/null
  fi
  # último recurso: garantir que a porta 8000 fica livre
  sleep 1
  lsof -ti:8000 2>/dev/null | xargs -r kill -9 2>/dev/null || true
  log_info "tchau"
}
trap cleanup EXIT INT TERM

# -----------------------------------------------------------------------------
# Sobe o backend (uvicorn com --reload, em novo grupo de processo)
# -----------------------------------------------------------------------------
log_info "subindo BACKEND  (FastAPI + uvicorn) em :8000 ..."
(
  cd "$BACKEND_DIR"
  # setsid coloca o processo num grupo próprio → cleanup mata o grupo inteiro
  exec setsid "$VENV_BIN/uvicorn" app.main:app --port 8000 --reload 2>&1 \
    | sed -u "s/^/$(printf "${COLOR_BACKEND}[BACKEND]${COLOR_RESET} ")/"
) &
BACKEND_PID=$!

# Aguarda o backend ficar pronto (até 15s)
log_info "aguardando backend em http://localhost:8000 ..."
for i in $(seq 1 30); do
  if curl -sS -o /dev/null -m 1 http://localhost:8000/api/v1/properties; then
    log_info "backend pronto"
    break
  fi
  sleep 0.5
  if [ "$i" = 30 ]; then
    log_error "backend não respondeu em 15s — verifique os logs acima"
    exit 1
  fi
done

# -----------------------------------------------------------------------------
# Sobe o frontend (Next.js)
# -----------------------------------------------------------------------------
log_info "subindo FRONTEND (Next.js) em :3000 ..."
(
  cd "$FRONTEND_DIR"
  exec setsid npm run dev 2>&1 \
    | sed -u "s/^/$(printf "${COLOR_FRONTEND}[FRONTEND]${COLOR_RESET} ")/"
) &
FRONTEND_PID=$!

log_info "tudo no ar — abra http://localhost:3000 (Ctrl+C para encerrar)"
START_TS=$(date +%s)

# -----------------------------------------------------------------------------
# Espera. Se QUALQUER um dos dois sair, o trap cleanup mata o outro e a gente sai.
# -----------------------------------------------------------------------------
wait -n "$BACKEND_PID" "$FRONTEND_PID"
exit_code=$?
elapsed=$(( $(date +%s) - START_TS ))

# Diagnóstico mais útil quando algo morre rápido (< 5s ⇒ provável falha de boot,
# não um Ctrl+C do usuário).
if [ "$elapsed" -lt 5 ]; then
  if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    log_error "frontend morreu em ${elapsed}s (exit=$exit_code) — provavelmente outro 'next dev' já estava rodando."
    log_error "rode: pkill -9 -f 'next' && ./dev.sh"
  elif ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    log_error "backend morreu em ${elapsed}s (exit=$exit_code) — confira o stack trace acima."
  fi
else
  log_info "um dos processos saiu (exit=$exit_code) — derrubando o outro"
fi
exit "$exit_code"

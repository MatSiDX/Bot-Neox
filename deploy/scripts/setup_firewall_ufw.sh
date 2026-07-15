#!/usr/bin/env bash
set -euo pipefail

SSH_PORT="${SSH_PORT:-22}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: ejecuta este script como root, por ejemplo: sudo $0" >&2
  exit 1
fi

if ! command -v ufw >/dev/null 2>&1; then
  echo "ERROR: UFW no esta instalado. Instala ufw antes de continuar." >&2
  exit 1
fi

echo "Configuracion propuesta de UFW:"
echo "- Denegar trafico entrante por defecto"
echo "- Permitir trafico saliente por defecto"
echo "- Permitir SSH en ${SSH_PORT}/tcp"
echo "- Permitir HTTP en 80/tcp"
echo "- Permitir HTTPS en 443/tcp"
echo "- No abrir 8000/tcp ni puertos internos del bot"
echo
echo "Si SSH usa otro puerto, cancela y ejecuta: sudo env SSH_PORT=2222 $0"
echo

read -r -p "Confirma que ${SSH_PORT}/tcp es tu puerto SSH actual antes de activar UFW [y/N]: " confirm
case "${confirm}" in
  y|Y|yes|YES) ;;
  *)
    echo "Cancelado. No se aplicaron cambios."
    exit 0
    ;;
esac

ufw default deny incoming
ufw default allow outgoing
ufw allow "${SSH_PORT}/tcp"
ufw allow 80/tcp
ufw allow 443/tcp

echo
echo "Reglas antes de activar UFW:"
ufw status verbose || true

echo
echo "Activando UFW..."
ufw --force enable

echo
echo "Reglas activas:"
ufw status numbered
ufw status verbose

echo
echo "Puertos escuchando relevantes:"
ss -ltnp | grep -E ":(${SSH_PORT}|80|443|8000)\b" || true

echo
echo "Listo. Verifica que 8000/tcp no aparezca como ALLOW y que el dashboard escuche solo en 127.0.0.1:8000."

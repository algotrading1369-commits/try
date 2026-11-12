#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Ejecuta como root: sudo bash install.sh"
  exit 1
fi

echo "== OGame Bot — instalación en VPS =="

if ! command -v docker >/dev/null 2>&1; then
  echo ">> Instalando Docker..."
  apt-get update -qq
  apt-get install -y -qq docker.io docker-compose-plugin git >/dev/null
  systemctl enable --now docker
fi

if [ ! -d /opt/ogame-bot/.git ]; then
  git clone https://github.com/algotrading1369-commits/try.git /opt/ogame-bot
fi
cd /opt/ogame-bot

read -rp "Dominio (ej. bot.tudominio.com o mibot.duckdns.org, vacío para usar solo IP:puerto): " DOMAIN
DOMAIN=$(echo "${DOMAIN}" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]' | sed -E 's#^https?://##; s#/.*$##')
if echo "${DOMAIN}" | grep -q 'duckdns.org'; then
  echo ">> Recuerda: en duckdns.org el subdominio se crea solo con el prefijo (minúsculas, números y guiones, sin puntos ni espacios)"
  echo ">> y la IP en 'current ip' debe ser la de este VPS. El token de DuckDNS no hace falta aquí."
fi
read -rsp "Contraseña del panel (Enter para generar una aleatoria): " WEB_PASSWORD || true
echo
if [ -z "${WEB_PASSWORD}" ]; then
  WEB_PASSWORD=$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)
  echo ">> Contraseña generada: ${WEB_PASSWORD}"
fi

cat > .env <<EOF
DOMAIN=${DOMAIN}
WEB_PASSWORD=${WEB_PASSWORD}
EOF
chmod 600 .env

if [ -z "${DOMAIN}" ]; then
  cat > docker-compose.override.yml <<'EOF'
services:
  ogame-bot:
    ports:
      - "8300:8300"
EOF
  echo ">> Sin dominio: el panel se servirá por http en el puerto 8300"
  docker compose up -d --build
  SERVER_IP=$(curl -4 -s ifconfig.me || curl -6 -s ifconfig.me || echo TU_IP)
  echo
  echo "✅ Listo: http://${SERVER_IP}:8300"
else
  rm -f docker-compose.override.yml
  echo ">> Arrancando con HTTPS (Caddy pedirá el certificado automáticamente)..."
  docker compose --profile https up -d --build
  SERVER_IP=$(curl -4 -s ifconfig.me || curl -6 -s ifconfig.me || echo TU_IP)
  echo
  echo "✅ Listo: https://${DOMAIN}"
  echo "   (${DOMAIN} debe apuntar a ${SERVER_IP}; el certificado tarda 1-2 minutos)"
  echo "   Si Caddy no consigue el certificado, mira: docker compose logs caddy"
fi
echo
echo "Contraseña del panel guardada en /opt/ogame-bot/.env (cat .env para verla)"
echo "Comandos útiles: docker compose logs -f | docker compose restart | docker compose down"

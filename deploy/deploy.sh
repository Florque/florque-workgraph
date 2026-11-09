#!/usr/bin/env bash
# Pull and (re)start the stack, publish the CLI wheels, wait until ready.
#   cd /srv/florque && FLORQUE_TAG=v0.2.0 ./deploy.sh
set -euo pipefail
cd "$(dirname "$0")"
if [ -n "${FLORQUE_TAG:-}" ]; then
  sed -i "s/^FLORQUE_TAG=.*/FLORQUE_TAG=${FLORQUE_TAG}/" .env
fi
set -a; . ./.env; set +a
for var in FLORQUE_DOMAIN NEO4J_PASSWORD RESEND_API_KEY FLORQUE_EMAIL_FROM; do
  if [ -z "${!var:-}" ]; then echo "error: $var is empty in .env" >&2; exit 1; fi
done

compose="docker compose -f docker-compose.prod.yml"
$compose pull
$compose up -d --remove-orphans

# wheels for `uv tool install florque-cli --find-links https://$FLORQUE_DOMAIN/dist/`
rm -f dist/*.whl
$compose cp service:/app/dist/. dist/
ls dist

for i in $(seq 1 60); do
  if curl -fsS "https://${FLORQUE_DOMAIN}/readyz" >/dev/null 2>&1; then
    curl -fsS "https://${FLORQUE_DOMAIN}/readyz"; echo
    echo "deployed ${FLORQUE_TAG:-latest}"
    exit 0
  fi
  sleep 5
done
echo "error: service not ready; see: $compose logs service" >&2
exit 1

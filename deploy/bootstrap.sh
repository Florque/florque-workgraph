#!/usr/bin/env bash
# First-time setup of a fresh Ubuntu 24.04 Hetzner server. Run as root from a checkout of deploy/:
#   scp -r deploy root@SERVER:/root/florque-deploy && ssh root@SERVER /root/florque-deploy/bootstrap.sh
# Idempotent: re-running keeps .env and data.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT=/srv/florque

if ! command -v docker >/dev/null; then
  apt-get update -y
  apt-get install -y ca-certificates curl
  curl -fsSL https://get.docker.com | sh
fi
apt-get install -y ufw unattended-upgrades
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable

mkdir -p "$ROOT"/{data,neo4j/data,neo4j/logs,backups,dist}
# the service container runs as uid 10001
chown -R 10001:10001 "$ROOT/data"
install -m 0644 "$HERE/docker-compose.prod.yml" "$HERE/Caddyfile" "$HERE/litestream.yml" "$ROOT/"
install -m 0755 "$HERE/deploy.sh" "$HERE/backup-neo4j.sh" "$ROOT/"

if [ ! -f "$ROOT/.env" ]; then
  install -m 0600 "$HERE/.env.example" "$ROOT/.env"
  sed -i "s/^NEO4J_PASSWORD=$/NEO4J_PASSWORD=$(openssl rand -hex 24)/" "$ROOT/.env"
  echo "Wrote $ROOT/.env with a random NEO4J_PASSWORD. Fill in the rest, then run:"
  echo "  cd $ROOT && ./deploy.sh"
fi
chmod 600 "$ROOT/.env"

# nightly Neo4j dump at 03:30 server time
cat > /etc/cron.d/florque-backup <<CRON
30 3 * * * root $ROOT/backup-neo4j.sh >> /var/log/florque-backup.log 2>&1
CRON
echo "bootstrap done"

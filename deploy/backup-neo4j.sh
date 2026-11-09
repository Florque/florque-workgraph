#!/usr/bin/env bash
# Nightly Neo4j dump (Community edition dumps need the database stopped: ~1 min downtime),
# kept for 14 days locally and copied to object storage when LITESTREAM_* credentials are set.
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ./.env; set +a
compose="docker compose -f docker-compose.prod.yml"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"

$compose stop service neo4j
trap '$compose start neo4j service' EXIT
$compose run --rm --no-deps neo4j \
  neo4j-admin database dump neo4j --to-path=/backups --overwrite-destination=true
mv backups/neo4j.dump "backups/neo4j-${stamp}.dump"
$compose start neo4j service
trap - EXIT

if [ -n "${LITESTREAM_ACCESS_KEY_ID:-}" ]; then
  docker run --rm -v "$PWD/backups:/backups:ro" \
    -e AWS_ACCESS_KEY_ID="$LITESTREAM_ACCESS_KEY_ID" \
    -e AWS_SECRET_ACCESS_KEY="$LITESTREAM_SECRET_ACCESS_KEY" \
    -e AWS_DEFAULT_REGION="$LITESTREAM_REGION" \
    amazon/aws-cli:2.17.0 s3 cp "/backups/neo4j-${stamp}.dump" \
    "s3://${LITESTREAM_BUCKET}/${BACKUP_S3_PREFIX:-florque/neo4j}/neo4j-${stamp}.dump" \
    --endpoint-url "$LITESTREAM_ENDPOINT"
fi
find backups -name 'neo4j-*.dump' -mtime +14 -delete
echo "backup neo4j-${stamp}.dump done"

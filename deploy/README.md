# Deploying the closed beta (one Hetzner server)

```
agent ─ fwg CLI ──HTTPS──▶ Caddy (TLS, :443) ─▶ florque-service (:8000, internal)
                                                 ├─ Neo4j (bolt, internal)       ./neo4j/data
                                                 └─ SQLite files                  ./data/*.sqlite
                                                       └─ Litestream ─▶ Object Storage
```

Everything runs from `/srv/florque` on one server with Docker Compose. Only ports 22, 80 and
443 are open. Neo4j and the service have no published ports.

| File | Purpose |
| --- | --- |
| `docker-compose.prod.yml` | caddy, service, neo4j, litestream |
| `Caddyfile` | TLS for `FLORQUE_DOMAIN`, hides `/metrics`, serves CLI wheels at `/dist/` |
| `litestream.yml` | continuous replication of `service`, `hub` and `ontologies` SQLite files |
| `.env.example` | every setting; copied to `/srv/florque/.env` (0600) |
| `bootstrap.sh` | first-time server setup (Docker, firewall, folders, cron) |
| `deploy.sh` | pull, restart, publish wheels, wait for `/readyz` |
| `backup-neo4j.sh` | nightly Neo4j dump to `./backups` and object storage |

## 1. Prepare

1. **Server:** Hetzner Cloud CX32 or CPX31 (4 vCPU, 8 GB), Ubuntu 24.04, your SSH key.
   Turn on Hetzner backups for the server as a second safety net.
2. **DNS:** an `A` record (and `AAAA`) for e.g. `wg.example.com` pointing at the server.
3. **Object storage:** a Hetzner Object Storage bucket (e.g. `florque-backups` in `fsn1`)
   and an access key pair.
4. **Resend:** verify the sender domain at resend.com and create an API key with "sending access".
5. **Image access:** the GHCR image is private while the repository is. On the server,
   log in once with a GitHub token that has `read:packages`:
   `echo $TOKEN | docker login ghcr.io -u <github-user> --password-stdin`.

## 2. First install

```bash
scp -r deploy root@SERVER:/root/florque-deploy
ssh root@SERVER /root/florque-deploy/bootstrap.sh
ssh root@SERVER
vi /srv/florque/.env          # FLORQUE_DOMAIN, RESEND_*, FLORQUE_EMAIL_FROM, FLORQUE_CLI_INSTALL, LITESTREAM_*
cd /srv/florque && FLORQUE_TAG=v0.2.0 ./deploy.sh
```

`deploy.sh` refuses to start without the domain, the Neo4j password and the Resend settings.
The service itself also refuses to start without Resend when `FLORQUE_ENV=production`.

## 3. Invite the first users

The operator commands run inside the service container:

```bash
cd /srv/florque
alias fs='docker compose -f docker-compose.prod.yml exec service florque-service'
fs invite create --email alice@example.com          # new tenant, emails the code
fs invite create --email bob@example.com --tenant-id tenant_...   # join Alice's tenant
fs invite list
fs tenant list
fs user list
```

The invitee gets an email with the code and the install line from `FLORQUE_CLI_INSTALL`:

```bash
uv tool install florque-cli --find-links https://wg.example.com/dist/
fwg --api-url https://wg.example.com register --invite XXXX-XXXX-XXXX --email alice@example.com --tenant-name "Acme"
fwg whoami
```

After that `fwg` talks to the server by default. Members invite colleagues with `fwg invite EMAIL`.
On a new machine: `fwg --api-url https://wg.example.com login --email ...` (a 6-digit code is emailed).
Agents and CI use `fwg token create --label ci --agent` and set `FLORQUE_API_URL` and `FLORQUE_TOKEN`.

The Claude Code plugin (skills and commands) installs from the repository's marketplace:
`/plugin marketplace add Florque/florque-workgraph`, then `/plugin install florque-workgraph@florque`.
The repository must be readable by the user while it is private.

## 4. Upgrades

Tag a release (`git tag v0.2.1 && git push --tags`): CI tests, attaches wheels and pushes the
image. Then deploy with Actions → release → Run workflow (tag), or on the server:
`cd /srv/florque && FLORQUE_TAG=v0.2.1 ./deploy.sh`. Raise `FLORQUE_MIN_CLIENT` when the CLI
must be upgraded; older clients then print an upgrade warning.

Rollback: `FLORQUE_TAG=v0.2.0 ./deploy.sh`. SQLite schemas migrate forward only, so take a copy
of `data/` before rolling back over a schema change.

## 5. Backups and restore

* **SQLite** (accounts, tokens, hub, ontology extensions): Litestream replicates every second.
  Check with `docker compose -f docker-compose.prod.yml exec litestream litestream snapshots /data/service.sqlite`.
* **Neo4j:** `backup-neo4j.sh` runs at 03:30 (cron). Neo4j Community can dump only a stopped
  database, so the service is down for about a minute. Dumps stay 14 days in `backups/` and are
  copied to the bucket.

Restore on a new server (after `bootstrap.sh` and filling in `.env`):

```bash
cd /srv/florque
compose="docker compose -f docker-compose.prod.yml"
for db in service hub ontologies; do
  $compose run --rm --no-deps litestream restore -o /data/$db.sqlite /data/$db.sqlite
done
chown -R 10001:10001 data
cp /path/to/neo4j-YYYYMMDDTHHMMSSZ.dump backups/neo4j.dump
$compose run --rm --no-deps neo4j neo4j-admin database load neo4j --from-path=/backups --overwrite-destination=true
./deploy.sh
```

## 6. Operations

* Logs: `docker compose -f docker-compose.prod.yml logs -f service` (JSON lines).
* Metrics: `docker compose -f docker-compose.prod.yml exec service python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/metrics').read().decode())"`.
* Revoke a leaked token: `fs token list`, `fs token revoke TOKEN_ID` (users can also run `fwg token revoke`).
* Rate limits: `FLORQUE_RATE_LIMIT` (per token or IP, per minute) and `FLORQUE_AUTH_RATE_LIMIT`
  (per IP on `/v1/auth`). The limiter is in memory, which is fine for one service process.

## Limits of the beta

* **No RBAC:** every member of a tenant administers all of its projects, and agent tokens have the same rights.
* **One process:** the service runs with one worker (rate limits and caches live in memory).
* **Restarts:** a Neo4j backup restarts the service every night.

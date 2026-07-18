# MetroDrip staging deployment

## Purpose

This stack runs MetroDrip on one provider-neutral Linux host with three isolated
services: Caddy terminates HTTPS, Gunicorn serves Django, and MySQL stores durable
data on a private network. Only Caddy publishes host ports.

## Host prerequisites

- Linux host with at least 1 vCPU, 2 GB RAM, and persistent SSD storage.
- Docker Engine plus the Docker Compose v2 plugin.
- Inbound TCP 80 and TCP/UDP 443 allowed by the host and provider firewall.
- A staging DNS name whose A record (and AAAA record, if used) resolves to the host.
- Repository checkout and SSH access for the release operator.

Do not continue until `dig +short staging.example.com` returns the staging host's
public address. Caddy can issue a trusted certificate only after DNS and inbound
ports are working.

## First deployment

Run these commands from the repository root on the staging host:

```sh
cp deploy/.env.staging.example deploy/.env.staging
chmod 600 deploy/.env.staging
```

Edit `deploy/.env.staging`, replace every example value, and make the three host
values agree:

- `STAGING_HOST=staging.your-domain.example`
- `DJANGO_ALLOWED_HOSTS=staging.your-domain.example`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://staging.your-domain.example`

`STAGING_HOST` and every `DJANGO_ALLOWED_HOSTS` member must be a literal DNS
hostname without a wildcard, scheme, path, or port. The CSRF value is the matching
complete HTTPS origin. Only local smoke tests may use `localhost` or `127.0.0.1`.

Generate secrets with hexadecimal output so Compose parsing is unambiguous:

```sh
openssl rand -hex 48  # DJANGO_SECRET_KEY
openssl rand -hex 32  # MYSQL_PASSWORD
openssl rand -hex 32  # MYSQL_ROOT_PASSWORD (generate a separate value)
```

Validate interpolation before changing running services, then build and start the
stack:

```sh
docker compose --env-file deploy/.env.staging -f deploy/compose.staging.yml config --quiet
docker compose --env-file deploy/.env.staging -f deploy/compose.staging.yml up -d --build
docker compose --env-file deploy/.env.staging -f deploy/compose.staging.yml ps
```

The entrypoint collects static files, applies migrations, and runs the idempotent
demo seed only when `STAGING_SEED_DEMO=1`. After the first successful seed, set
that flag to `0` and apply the environment change with `up -d`; existing data is
preserved.

## Acceptance smoke checks

Replace the hostname in the commands below with the deployed staging name:

```sh
curl -fsS https://staging.your-domain.example/healthz/live/
curl -fsS https://staging.your-domain.example/healthz/ready/
curl -fsS https://staging.your-domain.example/staging/seed/
curl -fsSI https://staging.your-domain.example/admin/
curl -fsSI https://staging.your-domain.example/static/admin/css/base.css
```

Expected results:

- Both health endpoints return HTTP 200 with `{"status":"ok"}`.
- The temporary seed preview is HTTP 200 and lists 5 products / 180 variants.
- Django admin redirects to its login page and the admin stylesheet is HTTP 200.
- `docker compose ... exec app id` reports UID and GID `10001`.
- `docker compose ... ps` shows public bindings only for Caddy; MySQL and the app
  have no host-published ports.

Force-recreate every container once and repeat the readiness/preview checks to
verify replacement does not erase the `dbdata` volume:

```sh
docker compose --env-file deploy/.env.staging -f deploy/compose.staging.yml \
  up -d --force-recreate --wait --wait-timeout 120
```

## Logs and routine operations

```sh
# Follow all service logs.
docker compose --env-file deploy/.env.staging -f deploy/compose.staging.yml logs -f --tail=200

# Inspect only application startup, migrations, and request failures.
docker compose --env-file deploy/.env.staging -f deploy/compose.staging.yml logs -f --tail=200 app

# Rebuild after checking out a reviewed release revision.
docker compose --env-file deploy/.env.staging -f deploy/compose.staging.yml up -d --build
```

Keep exactly one `app` container. Startup migrations and MetroDrip's v1 in-process
APScheduler design are single-process operational assumptions; scaling the app or
raising Gunicorn above one worker can race migrations and duplicate scheduled jobs.
Move both concerns to dedicated release/worker processes before horizontal scaling.
Compose also rotates each service's local JSON logs at three 10 MiB files; external
log shipping can replace this bounded baseline later without risking disk exhaustion.

## Backup and rollback

Create a database backup before every migration-bearing release:

```sh
umask 077
install -d -m 0700 backups
docker compose --env-file deploy/.env.staging -f deploy/compose.staging.yml exec -T db \
  sh -c 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; exec mysqldump --single-transaction -u root "$MYSQL_DATABASE"' \
  > "backups/metrodrip-$(date -u +%Y%m%dT%H%M%SZ).sql"
```

The restrictive umask and directory mode keep dumps operator-readable only, and
`MYSQL_PWD` avoids placing the root password in the `mysqldump` argument list.

For an application-only rollback, check out the last known-good immutable Git tag
or commit and run `up -d --build` again. If the failed release changed the schema,
first review whether its Django migration is safely reversible. Restore the matching
pre-release dump when it is not; never run `docker compose down -v`, because `-v`
permanently deletes the MySQL and Caddy named volumes.

To stop containers without deleting data:

```sh
docker compose --env-file deploy/.env.staging -f deploy/compose.staging.yml down
```

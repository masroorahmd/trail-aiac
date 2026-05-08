# Plane backup (Ansible)

Ad-hoc backup of a running Plane v1.3.0 stack. Captures the two
stateful services — Postgres and MinIO — into a single tar.gz on the
controller. Both containers stay running. Designed for the homelab /
single-host case; not a substitute for a managed-service backup
strategy.

```bash
cd ansible/
ansible-playbook backup.yml
```

The bundle lands in `ansible/out/` (gitignored, mode 0600):

```
plane-backup-<inventory_hostname>-<UTC-timestamp>.tar.gz
└── plane-backup-<inventory_hostname>-<UTC-timestamp>/
    ├── postgres.dump   # pg_dump -F c plane (custom format)
    └── minio.tar       # tar of the MinIO `uploads` volume contents
```

Outer tar.gz handles compression; the inner `minio.tar` is left
uncompressed so MinIO uid/gid are preserved verbatim for restore. The
Postgres custom-format dump is already gzip-compressed by `pg_dump`
itself.

## What is in the bundle

| Component | How captured | Why this method |
|---|---|---|
| Postgres `plane` database | `docker compose exec -T plane-db pg_dump -h /var/run/postgresql -U plane -F c plane` | Custom format compresses internally and supports selective `pg_restore` (single table, schema-only, etc.). The explicit `-h /var/run/postgresql` forces the local Unix socket — without it, pg_dump picks up `PGHOST=plane-db` from the container's env and connects over TCP, where the postgres image enforces `scram-sha-256`. The local socket is `trust`-authenticated by default, so no password handling. |
| MinIO `uploads` volume (`/export` inside the container) | `docker run --rm --volumes-from <plane-minio-cid> alpine:3 tar -C /export -cf - .` | The MinIO image is UBI-minimal and ships no `tar`, so a sidecar Alpine container inherits the volume via `--volumes-from` and tars from there. This still avoids guessing the host-side volume path (compose project-prefix vs raw volume name). uid/gid are preserved so a restore into a fresh container reproduces the permissions MinIO originally wrote. |

## What is deliberately NOT in the bundle

| Component | Why excluded |
|---|---|
| Redis / Valkey (`redisdata` volume) | Cache + ephemeral session state. A fresh Redis on restore is fine — Plane regenerates whatever it needs. |
| RabbitMQ (`rabbitmq_data` volume) | Transient task queues. Restoring stale messages would replay long-finished work; a clean queue is the right state. |
| Plane logs (`logs_*` volumes) | Application logs, not data. Capture via your normal log-shipping path if you need them. |
| Compose config + secrets (`/opt/stacks/plane/.env`, `compose.yaml`) | Reproducible from the playbook + `vault/secrets.yml`. Re-render with `ansible-playbook plane.yml --tags plane` against the same vault. |
| Caddy site snippet | Same — re-rendered by `ansible-playbook plane.yml --tags caddy`. |

For a full disaster-recovery story you also need the encrypted
`vault/secrets.yml` (kept in this repo) and the controller's vault
password file (`~/.config/ansible/aac-coding-vault-pass`). Without
them you can re-deploy a working Plane but not re-attach the existing
agent tokens or admin credentials.

## Consistency model

The dump and the MinIO tar both run against running containers. There
is no global snapshot, so an upload that lands between the two steps
will be in MinIO without a matching Postgres row, or vice versa. For
the personal homelab this is acceptable: skew is bounded to the
duration of the dump (seconds to minutes), and Plane tolerates a
missing-attachment row by serving a "file not found" placeholder.

For coordinated point-in-time recovery — e.g. before a risky migration
— stop the workload-side containers around the dump:

```bash
ssh plane-host
cd /opt/stacks/plane
docker compose stop api worker beat-worker live web admin space proxy
# return to the controller and run the backup
ansible-playbook backup.yml
# then bring everything back
ssh plane-host 'cd /opt/stacks/plane && docker compose start \
  api worker beat-worker live web admin space proxy'
```

`plane-db` and `plane-minio` are deliberately left running — both must
be alive to dump from.

## Restore

Against a freshly provisioned, **empty** Plane stack on the same Plane
release (`v1.3.0`):

```bash
# 0. Provision a fresh Plane (creates the DB + MinIO bucket schemas).
cd ansible/
ansible-playbook plane.yml

# 1. Stop the workload containers but leave plane-db + plane-minio up.
ssh plane-host 'cd /opt/stacks/plane && docker compose stop \
  api worker beat-worker live web admin space proxy'

# 2. Unpack the bundle on the host.
scp out/plane-backup-<host>-<ts>.tar.gz plane-host:/tmp/
ssh plane-host 'cd /tmp && tar xzf plane-backup-<host>-<ts>.tar.gz'

# 3. Restore Postgres (clean + recreate schema, then load).
#    `-h /var/run/postgresql` forces the trust-auth Unix socket;
#    without it, PGHOST=plane-db (set in the container env) routes
#    pg_restore over TCP and it asks for a password.
ssh plane-host 'cd /opt/stacks/plane && \
  docker compose exec -T plane-db pg_restore \
    -h /var/run/postgresql \
    -U plane -d plane --clean --if-exists \
    < /tmp/plane-backup-<host>-<ts>/postgres.dump'

# 4. Restore MinIO contents (overwrites /export inside the container).
#    Same reason as the dump side: the MinIO image has no `tar`, so we
#    run a sidecar that inherits the volume and untars from stdin.
ssh plane-host 'cd /opt/stacks/plane && \
  MINIO_CID=$(docker compose ps -q plane-minio) && \
  docker run --rm -i --volumes-from "$MINIO_CID" alpine:3 \
    tar -C /export -xf - \
    < /tmp/plane-backup-<host>-<ts>/minio.tar'

# 5. Bring the workload back up.
ssh plane-host 'cd /opt/stacks/plane && docker compose start \
  api worker beat-worker live web admin space proxy'

# 6. Clean up the unpacked bundle on the host.
ssh plane-host 'rm -rf /tmp/plane-backup-<host>-<ts>*'
```

`pg_restore --clean --if-exists` drops and recreates every object the
dump defines, which is what you want for a from-scratch restore. For a
selective restore (a single table, only the schema, etc.) drop
`--clean` and pass `-t <table>` / `--schema-only`.

## Variables

All defaults live in `roles/plane_backup/defaults/main.yml` and are
fine for the standard provisioning. Override only when:

| Variable | Default | Override when |
|---|---|---|
| `plane_backup_dir` | `{{ stacks_dir }}/plane` | Plane was installed somewhere other than `/opt/stacks/plane`. |
| `plane_backup_remote_workdir` | `/tmp/plane-backup` | `/tmp` is too small or you want the scratch in a specific FS. |
| `plane_backup_keep_remote` | `false` | Debugging — keeps the host-side bundle in place after fetch so you can inspect / re-fetch. |
| `plane_backup_out_dir` | `{{ playbook_dir }}/out` | You want bundles somewhere other than `ansible/out/`. |

## Scheduling (out of scope for this playbook)

The playbook is ad-hoc by design; it does not install a cron job. If
you want recurring backups, wire the same command into systemd
timers, cron, or a CI runner — whatever you already use for
controller-side automation. A typical line:

```cron
# Every Sunday at 02:30 UTC, keep four weeks of backups.
30 2 * * 0  cd /home/<you>/projects/homelab/trail-aiac/ansible && \
            ansible-playbook backup.yml >> /var/log/plane-backup.log 2>&1
30 3 * * 0  find /home/<you>/projects/homelab/trail-aiac/ansible/out \
            -name 'plane-backup-*.tar.gz' -mtime +28 -delete
```

The bundles do not encrypt themselves. Pipe through `age`, `gpg`, or
your preferred at-rest encryption before shipping them off-host.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `Required service plane-db is not in the running set` | The compose stack is down. Start it: `docker compose -f /opt/stacks/plane/compose.yaml up -d`. |
| `pg_dump: error: connection to server on socket … failed` | The `plane-db` container's Postgres isn't accepting connections yet (e.g. just-restarted, mid-startup). Wait 10 s and retry. |
| `pg_dump: error: connection to server at "plane-db" … failed: fe_sendauth: no password supplied` | `-h /var/run/postgresql` is missing on the `pg_dump` (or `pg_restore`) line. Without it, `PGHOST=plane-db` in the container's env routes the connection over TCP, which requires a password. The playbook above sets the flag; if you're invoking pg_dump by hand, add it. |
| `tar: ./<file>: file changed as we read it` (warning, not failure) | A user uploaded an attachment while MinIO was being tarred. The bundle is still valid for everything that wasn't actively changing. Re-run if you need a fresher snapshot, or use the consistency-model recipe above. |
| MinIO step exits with `rc 127` and empty output | The MinIO image lacks `tar`, and the sidecar fallback isn't being used. The playbook above runs `docker run --volumes-from plane-minio alpine:3 tar …`; if you're invoking the tar by hand, add the same sidecar wrapper instead of `docker compose exec plane-minio tar …`. |
| Bundle size much larger than expected | MinIO has accumulated old uploads (Plane retains attachments forever). Compaction is a separate operation outside this playbook's scope. |

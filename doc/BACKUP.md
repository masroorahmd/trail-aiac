# Plane backup (Ansible)

Backup of a running Plane v1.3.0 stack. Captures the two stateful
services — Postgres and MinIO — into a single tar.gz. Both containers
stay running. Designed for the homelab / single-host case; not a
substitute for a managed-service backup strategy.

Two delivery paths, same mechanics:

| Path | Trigger | Where the bundle lands | When to use |
|---|---|---|---|
| **Ad-hoc** (`ansible/backup.yml`) | Manual: `ansible-playbook backup.yml` from the controller | `ansible/out/` on the controller | Before a risky migration; when you want a bundle on your laptop to inspect or take with you. |
| **Recurring** (`ansible/backup-cron.yml`) | Cron on the Plane host, daily | Wherever `plane_backup_cron_target_dir` points — typically an external mount (NFS / CIFS / S3-fuse) | The continuous safety net. Install once per host. |

```bash
cd ansible/
ansible-playbook backup.yml          # ad-hoc, one-shot
ansible-playbook backup-cron.yml     # install the recurring schedule
```

The ad-hoc bundle lands in `ansible/out/` (gitignored, mode 0600):

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

## Recurring backups (`ansible/backup-cron.yml`)

The recurring path runs cron **on the Plane host itself**, not on the
controller — so the backup keeps firing when your laptop is closed.
The `plane_backup_cron` role renders three files on the host:

| File | Purpose |
|---|---|
| `/usr/local/sbin/plane-backup.sh` | Self-contained shell script. Same dump mechanics as the ad-hoc playbook (pg_dump over the Postgres Unix socket + alpine sidecar tar of the MinIO volume), plus a single-instance `flock` guard, a `mountpoint -q` pre-flight when targeting an external share, and atomic-rename publishing (no half-written `.tar.gz` ever appears under its final name). |
| `/etc/cron.d/plane-backup` | The schedule. Runs as `root` (docker compose requires it) and pipes stdout/stderr to the logfile. Cron honours `/etc/localtime`. |
| `/etc/logrotate.d/plane-backup` | Weekly rotation, eight weeks kept, compressed. |

Bundle naming and content are identical to the ad-hoc path —
`plane-backup-<inventory_hostname>-<UTC>.tar.gz` containing
`postgres.dump` + `minio.tar` — so a restore procedure written for one
works for the other.

Configure the target in `host_vars/<host>.yml`:

```yaml
# Send bundles to an already-mounted external share, fail loudly when
# the share is offline. The mount itself is provisioned out-of-band.
plane_backup_cron_target_dir: /mnt/backups/plane
plane_backup_cron_mount_root: /mnt/backups
plane_backup_cron_retention_days: 28
plane_backup_cron_hour: "2"
plane_backup_cron_minute: "30"
```

The framework default (`/var/backups/plane`, no mount check) is
deliberately weak — landing backups on the same disk as the workload
is a homelab anti-pattern. Override it.

Install once per host:

```bash
ansible-playbook backup-cron.yml
```

Inspect the live schedule and the most recent runs:

```bash
ssh plane-host 'cat /etc/cron.d/plane-backup'
ssh plane-host 'tail -50 /var/log/plane-backup.log'
ssh plane-host 'ls -lh $(awk -F= "/target_dir/ {print \$2}" /usr/local/sbin/plane-backup.sh | head -1)'
```

The bundles do not encrypt themselves. Pipe through `age`, `gpg`, or
your preferred at-rest encryption before shipping them off-site (or
extend the script to do so before the atomic-rename step).

### Removing the schedule

The role has no `state: absent` knob. To uninstall by hand:

```bash
ssh plane-host 'sudo rm -f /etc/cron.d/plane-backup \
                          /etc/logrotate.d/plane-backup \
                          /usr/local/sbin/plane-backup.sh \
                          /var/log/plane-backup.log'
```

Existing bundles at `plane_backup_cron_target_dir` are not touched.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `Required service plane-db is not in the running set` | The compose stack is down. Start it: `docker compose -f /opt/stacks/plane/compose.yaml up -d`. |
| `pg_dump: error: connection to server on socket … failed` | The `plane-db` container's Postgres isn't accepting connections yet (e.g. just-restarted, mid-startup). Wait 10 s and retry. |
| `pg_dump: error: connection to server at "plane-db" … failed: fe_sendauth: no password supplied` | `-h /var/run/postgresql` is missing on the `pg_dump` (or `pg_restore`) line. Without it, `PGHOST=plane-db` in the container's env routes the connection over TCP, which requires a password. The playbook above sets the flag; if you're invoking pg_dump by hand, add it. |
| `tar: ./<file>: file changed as we read it` (warning, not failure) | A user uploaded an attachment while MinIO was being tarred. The bundle is still valid for everything that wasn't actively changing. Re-run if you need a fresher snapshot, or use the consistency-model recipe above. |
| MinIO step exits with `rc 127` and empty output | The MinIO image lacks `tar`, and the sidecar fallback isn't being used. The playbook above runs `docker run --volumes-from plane-minio alpine:3 tar …`; if you're invoking the tar by hand, add the same sidecar wrapper instead of `docker compose exec plane-minio tar …`. |
| Bundle size much larger than expected | MinIO has accumulated old uploads (Plane retains attachments forever). Compaction is a separate operation outside this playbook's scope. |

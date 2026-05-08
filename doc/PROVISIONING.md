# Plane provisioning (Ansible)

Brings up a **Plane Community v1.3.0** stack on an SSH-reachable host
that already has docker + a Caddy reverse-proxy, then configures the
workspace, projects, agents, modules, labels, ticket states, avatars,
and per-agent API tokens the framework expects. Tested only against
Plane v1.3.0 — the docker-exec ORM steps reach into Plane internals
(model paths, signal behavior) that a future release may rename.

> Quick path: don't run any of this manually — invoke the
> `install-helper` agent and let it drive the playbook for you. See
> [`INSTALLATION.md`](INSTALLATION.md). The detail below is the
> reference the agent works from, and what you'd touch when something
> goes sideways.

Agents authenticate **exclusively via API token**. Per-agent passwords
are generated as random unrecoverable values; the only password that
gets persisted (encrypted in `vault/secrets.yml`) is the human admin's.

## Host pre-conditions

The play targets an apt-based host (Debian / Ubuntu / Raspberry Pi
OS). Pre-tasks at the top of the host play probe and, if missing,
install:

| Pre-condition | Auto-installed? | Notes |
|---|---|---|
| Docker engine + compose plugin (`docker.io`, `docker-compose-v2`) | yes, via apt when `docker compose version` fails | Plus `python3-docker` + `python3-requests` so `community.docker.*` modules work. Skipped if a working Docker is already present (e.g. docker-ce from Docker's own repo). |
| External docker network (default `web`) | yes, via `community.docker.docker_network state=present` | Override the name with `docker_network` if your existing network is called something else. Plane's proxy joins it as `plane-proxy`. |
| apt-installed, systemd-managed Caddy | yes, via apt when `caddy.service` is not found | Base `/etc/caddy/Caddyfile` must `import /etc/caddy/sites.d/*.caddy` (the caddy role appends this line via `lineinfile` if missing). TLS source is auto-picked — see "TLS strategies" below. |
| `/etc/caddy/sites.d/` directory | yes, via `file state=directory` | Trivial mkdir. |

To front Plane with a different reverse proxy entirely, run with
`--skip-tags caddy`; Plane stays reachable on the host at
`127.0.0.1:8081` (the value of `plane_proxy_host_port`).

### TLS strategies (`plane_caddy_tls_strategy`)

The site block this role drops picks its TLS source per
`plane_caddy_tls_strategy`:

| Value | When picked / when to set | What the site block emits |
|---|---|---|
| `auto` (default) | Heuristic. If Caddy was already installed when the play started (i.e. another ansible project on the host has set it up and presumably defined a `(tls_files)` snippet), resolves to `tls_files`. If pre_tasks had to apt-install Caddy fresh, resolves to `internal`. | (resolved per row below) |
| `tls_files` | Set explicitly when your base Caddyfile defines a `(tls_files)` snippet (e.g. private-PKI cert provisioned by another ansible project). | `import tls_files` |
| `internal` | Set explicitly for LAN/private hosts where you'd rather skip failed ACME attempts. Default on freshly-installed Caddy. | `tls internal` (Caddy's self-signed CA — browsers warn on first hit). |
| `acme` | Set explicitly for a publicly resolvable hostname with ports 80+443 reachable from the public internet. | No tls directive — Caddy's auto-https tries Let's Encrypt and falls back to internal if ACME fails. |

Plus a Boolean knob `plane_caddy_offer_http` (default `auto`):
auto-enabled when the strategy resolves to `internal`, so you can
`curl http://<host>/` without trust prompts. Caddy still serves the
HTTPS site block alongside.

When the host is already managed by another ansible project that
owns docker, caddy, and the `web` network, every pre-task probe
succeeds and the install/create tasks all skip — the play only adds
Plane on top.

## What you supply

A controller machine with `ansible` ≥ 2.15, `ssh`, and an editor — and:

| Input             | Where                                                       | Required | Notes                                                                                                  |
|-------------------|-------------------------------------------------------------|----------|--------------------------------------------------------------------------------------------------------|
| Target host       | `inventory.yml` (`ansible_host`)                            | yes      | DNS or IP that resolves to the host                                                                    |
| SSH user + key    | `inventory.yml` + your SSH agent                            | yes      | Needs sudo (the play uses `become: true` — pre-tasks may apt-install docker/caddy)                     |
| Public FQDN       | `host_vars/<host>.yml` (`domain_plane`)                     | yes      | The hostname the existing Caddy will serve Plane under                                                 |
| Admin identity    | `host_vars/<host>.yml` (`plane_admin`)                      | yes      | Email + full name of the human admin. Password is auto-generated into the vault — see "First login".   |
| Workspace         | `host_vars/<host>.yml` (`plane_workspace`)                  | yes      | `slug` (URL fragment, immutable) + `name` (human label) the agents are invited into                    |
| Projects          | `host_vars/<host>.yml` (`plane_projects`)                   | yes      | List of `{name, identifier, description, [members], [modules], [labels]}`. `identifier` is the work-item prefix. `name` must be alphanumeric + spaces (Plane rejects parens, brackets, etc. with HTTP 400 "Project name cannot contain special characters"). |
| Agent email TLD   | `host_vars/<host>.yml` (`plane_agent_email_domain`)         | yes      | Each persona gets `<persona-username>@<this-domain>` as login. SMTP isn't required.                    |
| Vault password    | `~/.config/ansible/aac-coding-vault-pass` (one-time)| yes      | Outside the repo so multiple ansible projects on the same controller can share it. `ansible.cfg` reads it. |

## Kickoff — fresh host, full turn-key

```bash
cd ansible/
cp inventory.yml.example inventory.yml                # edit ansible_host, ansible_user
cp host_vars/plane.yml.example host_vars/plane.yml    # fill domain_plane (and a few defaults)

# One-time vault password setup. plane_secrets uses this file to
# encrypt the auto-generated vault/secrets.yml during the first run.
mkdir -p ~/.config/ansible
openssl rand -hex 24 > ~/.config/ansible/aac-coding-vault-pass
chmod 600 ~/.config/ansible/aac-coding-vault-pass

ansible-playbook plane.yml
```

That's it. The playbook in order:

1. Generates and encrypts every Plane secret (`plane_secrets`).
2. Brings up the Plane stack and waits for the migrator to finish
   (~8-10 min on a fresh DB) and for the api container to land its
   `Instance` row (`plane`).
3. Creates the instance admin + workspace + bootstrap API token, and
   sets `ENABLE_SIGNUP=0` (`plane_admin`).
4. Provisions all ten agent accounts, auto-accepts their invitations
   (bots can't click email links), mints per-agent API tokens,
   uploads avatars, and disables their email notifications
   (`plane_users`).
5. Creates the configured projects + members (`plane_projects`).
6. Reconciles workflow states + phase modules + story labels per
   project (`plane_bootstrap`).
7. Drops `sites.d/plane.caddy` into the host's existing Caddy stack
   and reloads it (`caddy`).

**First-run wall-clock**: 10-15 minutes (most of it spent on
Plane's 121 sequential DB migrations). Subsequent runs return in
well under a minute.

## First login

After the play returns, two pieces of state on the controller hold
everything you need:

- **Admin login** — email is what you put in `host_vars/<host>.yml`
  under `plane_admin.email`. The auto-generated password is in the
  vault:

  ```bash
  ansible-vault view ansible/vault/secrets.yml | grep admin_password
  # → admin_password: <24-char string>
  ```

  Open `https://<domain_plane>/`, sign in with that email + password,
  and you'll land in the `<plane_workspace.slug>` workspace with all
  ten agents already members and all configured projects already
  created.

- **Agent API tokens** — one workspace-scoped token per persona,
  written to `ansible/out/plane-agent-tokens-<host>.yml` on the
  controller (gitignored). The `install-helper` agent copies these
  into the consumer project's `.claude/credentials.yaml`
  automatically; if you're driving by hand, copy them yourself.

- **No persisted UI password.** Agent accounts are API-only. The
  `plane_users` role hashes a random `uuid4()` to satisfy Postgres'
  NOT-NULL `password` column, but the plaintext is discarded inside
  the Python process — nothing reaches the controller. If a human
  ever needs to inspect Plane as a specific agent, reset that
  account's password via Plane's admin UI (*Workspace Settings →
  Members → password reset*).

The instance is also locked down by default: `ENABLE_SIGNUP=0` means
no one else can register on this Plane via the public sign-up form.
Add humans by inviting them from *Workspace Settings → Members*.

## Kickoff — already have Plane, only need agent accounts

If you run Plane elsewhere and just want this framework to provision
the ten persona accounts (with avatars, API tokens, notification
opt-out), skip everything host-related and decorate the existing
workspace:

```bash
cd ansible/
cp inventory.yml.example inventory.yml                # ansible_host = your existing Plane host
cp host_vars/plane.yml.example host_vars/plane.yml    # domain_plane + plane_workspace.slug

# Bootstrap token: one workspace API token belonging to a workspace
# Admin. Mint one in the Plane UI under Workspace Settings → API
# tokens, then put it in vault/secrets.yml as plane.admin_token.
cp vault/secrets.example.yml vault/secrets.yml
mkdir -p ~/.config/ansible
openssl rand -hex 24 > ~/.config/ansible/aac-coding-vault-pass
chmod 600 ~/.config/ansible/aac-coding-vault-pass
ansible-vault encrypt vault/secrets.yml
ansible-vault edit vault/secrets.yml --ask-vault-pass   # paste your admin_token

ansible-playbook plane.yml --tags plane_users,plane_bootstrap
```

`plane_users` (members + tokens + avatars + notifications) and
`plane_bootstrap` (states + modules + labels) are both safe to run
against an existing workspace — they GET-then-create-missing for
every resource.

## Idempotency

Re-running `ansible-playbook plane.yml` against an up-and-running
Plane is a no-op modulo the agent decoration:

- `plane` — Docker compose state reconciliation; the api-readiness
  probe returns on the first attempt.
- `caddy` — re-renders the snippet; reload handler fires only when
  the snippet content actually changes.
- `plane_secrets` — short-circuits when every required key is already
  present in the encrypted vault.
- `plane_admin` — every step is `get_or_create` / `filter+create`;
  re-emits the existing token instead of minting a new one.
- `plane_users` — GETs existing workspace members + invitations, only
  POSTs missing ones; re-uses existing API tokens looked up by
  `(user, workspace, label)`; skips avatars whose `avatar_asset_id`
  is already set; skips notification rows already opted out.
- `plane_projects` — GETs existing projects by `identifier`, only
  creates missing ones; only PATCHes drifted fields. Note: Plane
  auto-adds the API-token owner (the workspace admin) as a project
  member on create — so the admin lands on every project regardless
  of the `members:` list, which is the framework's expected behaviour
  (the admin owns the workspace anyway).
- `plane_bootstrap` — verifies states, creates missing modules and
  labels.

Adding a new agent to `agents` (in `group_vars/plane_hosts.yml`):
re-run, and only that agent gets invited / accepted / token-minted /
project-added / avatar-uploaded.

## Inspecting & rotating secrets

`vault/secrets.yml` is encrypted with the password in
`~/.config/ansible/aac-coding-vault-pass`. To open it on a
controller that doesn't have that file (or to enter the password
interactively):

```bash
ansible-vault view ansible/vault/secrets.yml --ask-vault-pass
ansible-vault edit ansible/vault/secrets.yml --ask-vault-pass
```

`ansible-vault` will prompt for the password each invocation. The
playbook itself reads it from the path configured in `ansible.cfg`
(`vault_password_file = ~/.config/ansible/aac-coding-vault-pass`),
so the file is only required at provisioning time.

Agent accounts have no persisted UI password — see *Per-agent
identities* above. Reset via Plane's admin UI if a human ever needs
to log in as one.

API tokens are in `ansible/out/plane-agent-tokens-<host>.yml` (mode
0600, gitignored). To rotate a token: delete the `APIToken` row in
Plane (UI under Workspace Settings → API tokens, or via the api
container shell), then re-run `ansible-playbook plane.yml --tags
plane_users`. The role will mint a new token, overwrite the entry
in `out/`, and the `install-helper` (or your re-run of
`bin/install.py`) propagates it into the consumer's credentials.

## Optional features deliberately left manual

- **SMTP.** Bots don't have inboxes — `plane_users` accepts each
  agent's invitation directly via ORM, so SMTP isn't needed for the
  framework to work. If you want *human* collaborators to receive
  invite mails, configure SMTP manually under
  `https://<domain_plane>/god-mode/`.
- **Backups.** Out of scope. The Plane data lives in named Docker
  volumes (`plane_pgdata`, `plane_uploads`, `plane_rabbitmq_data`) on
  the host — back those up however you back up the rest of the host.

## Tear-down

```bash
ssh <user>@<host>
cd /opt/stacks/plane && docker compose down -v
sudo rm -rf /opt/stacks/plane/
# Drop the Plane site-block snippet. apt-Caddy, the base Caddyfile,
# and the `web` network are pre-conditions owned by something else
# on the host — leave them alone.
sudo rm -f /etc/caddy/sites.d/plane.caddy
sudo systemctl reload caddy
```

The `-v` flag drops all of Plane's data volumes — irreversible without
a backup.

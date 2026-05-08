# ansible/ — Plane provisioning

This directory provisions a **Plane Community v1.3.0** stack on an
SSH-reachable host and configures the workspace, projects, ten agent
accounts, modules, labels, ticket states, avatars, and per-agent API
tokens the framework expects.

> **Don't run this by hand.** Open the framework repo in Claude Code
> and invoke the `install-helper` agent — it drives the playbook for
> you, ingests the generated secrets into the consumer project, and
> runs `bin/install.py`. See [`../doc/INSTALLATION.md`](../doc/INSTALLATION.md).
>
> Full reference for what the playbook does, the host pre-conditions,
> TLS strategies, idempotency notes, secret rotation, and tear-down:
> [`../doc/PROVISIONING.md`](../doc/PROVISIONING.md).

## Directory layout

| Path | Purpose |
|---|---|
| `plane.yml` | Top-level playbook; targets the `plane_hosts` group. |
| `inventory.yml.example` | Inventory template — copy to `inventory.yml` (gitignored). |
| `host_vars/plane.yml.example` | Per-host config template — copy to `host_vars/plane.yml` (gitignored). |
| `group_vars/all.yml`, `group_vars/plane_hosts.yml` | Framework-wide and group defaults (10 personas, etc.). |
| `vault/secrets.example.yml` | Vault template — copy to `vault/secrets.yml` (gitignored, ansible-vault encrypted). |
| `roles/` | `plane_secrets`, `plane`, `plane_admin`, `plane_users`, `plane_projects`, `plane_bootstrap`, `caddy`. All idempotent. |
| `out/` | Generated per-host artefacts (gitignored, mode 0600): API tokens + invitation log. Agent accounts are API-only — no UI passwords are persisted. |

## One-line invocations

```bash
# Greenfield — fresh Plane on a fresh host.
ansible-playbook plane.yml

# Existing Plane — only add / reconcile agents + workflow scaffolding.
ansible-playbook plane.yml --tags plane_users,plane_bootstrap

# Skip Caddy (you front Plane with something else).
ansible-playbook plane.yml --skip-tags caddy
```

For everything else — what the input vars mean, when the play
short-circuits, how to inspect or rotate secrets, what gets created
in the host's `/opt/stacks/plane/`, how TLS is selected, how to tear
the stack down — see [`../doc/PROVISIONING.md`](../doc/PROVISIONING.md).

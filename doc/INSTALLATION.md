# Installation

The recommended path is to let the **`install-helper`** agent walk
you through it interactively, dispatched via the `/trail-install-helper`
slash command:

```bash
cd /path/to/trail-aiac
claude
```

Then in the Claude Code session:

```
> /trail-install-helper /path/to/my-project
```

The agent figures out which scenario applies, sets up the
prerequisites it can (`uv`, `ansible`, vault password, `~/.config/ansible/`),
asks the handful of inputs it can't (Plane URL, host SSH details,
admin email), runs the Ansible playbook (with confirmation) where
relevant, ingests the generated tokens + UI passwords into the
consumer project's `.claude/config.yaml` + `credentials.yaml`, runs
`bin/install.py`, and prints a usage card showing how to log in,
where to find your secrets, and how to fire the first agent. Total:
about 15 minutes on a fresh host, under a minute when Plane is
already up.

The remainder of this document is the manual reference — what the
install-helper actually does under the hood, in case you want to
drive by hand or troubleshoot.

## Three scenarios

| Scenario | Plane already running? | Agent accounts already created? | What the install does |
|---|---|---|---|
| **1. Greenfield** | no | no | Provisions Plane v1.4.0 on a host you supply via Ansible, mints all secrets, copies them into the consumer's `.claude/`, runs `install.py`. |
| **2. Existing Plane, no agents** | yes | no | Skips the Plane stack rollout; runs `--tags plane_users,plane_bootstrap` to add the eleven persona accounts + workflow states/modules/labels; copies the resulting tokens + UI passwords into the consumer's `.claude/`, runs `install.py`. |
| **3. Existing Plane, agents already there** | yes | yes | Pure framework install: you provide the eleven API tokens + UI passwords (from your own provisioning), they go into `.claude/credentials.yaml`, then `install.py`. |

## Prerequisites

Whatever scenario applies, the controller needs:

- **Python 3.11+** with `pyyaml`. `bin/install.py` imports `yaml`;
  the helper installs it via `apt`/`pip` if missing.
- **`uv`** (Astral's Python tool runner). The multi-tenant `plane`
  MCP server in the consumer's `.mcp.json` is launched via `uv run`.
  One-line install:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
  Drops `uv` and `uvx` into `~/.local/bin/`.
- **`rtk`** (optional, recommended) — [rtk-ai/rtk](https://github.com/rtk-ai/rtk),
  a single Rust binary that condenses what a Bash command prints
  before the persona reads it (a test run to its failures, `git log`
  to its lines, no progress bars, no ANSI). The framework's
  `rtk-rewrite.py` hook calls it on every Bash tool call, controlled
  by `hooks.bash_output_trim` in the consumer's `config.yaml`; with no
  `rtk` on PATH the hook does nothing, so install order does not
  matter. One-line install:
  ```bash
  curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh
  ```
  (also `brew install rtk`; or the release tarball into
  `~/.local/bin/`). Do **not** also run `rtk init` in a consumer:
  it writes its own hook into `settings.json`, which `install.py`
  overwrites on the next run. The framework's hook is that hook.
- **[herdr](https://herdr.dev)** (optional) — a terminal app for coding
  agents. Trail does not need it. When you run your persona sessions
  in herdr, Trail labels them, shows them in a side panel, and signals
  handovers; see *Optional: herdr* below. Nothing to install up front:
  `install.py` sets up the herdr part when it finds herdr.
- **`ansible` ≥ 2.15** and **`ssh`** (for scenarios 1 & 2 only).
- **Private-CA Plane** trust configuration: if your Plane sits
  behind a self-signed or internal-PKI certificate (Caddy `tls
  internal`, your own private CA, the Ansible playbook's default for
  Pi / homelab installs), point Python's TLS at your system trust
  bundle:
  ```bash
  # Add to ~/.bashrc or ~/.zshrc:
  export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
  export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
  ```
  Python (used by both MCP servers) defaults to the `certifi` bundle
  baked into the Python install and ignores the system trust store.
  Without these env vars, MCP calls to your Plane fail with SSL verify
  errors *even though `curl` (which uses the system store) works
  fine*. The bundle path above is the standard Debian / Ubuntu / WSL
  location populated by `update-ca-certificates`; adjust for other
  distros. Skip this entirely if your Plane uses a public CA (Plane
  Cloud, Let's Encrypt, etc.).

## Scenario 1 — Greenfield Ansible install

```bash
cd /path/to/trail-aiac/ansible
cp inventory.yml.example inventory.yml
cp host_vars/plane.yml.example host_vars/plane.yml
$EDITOR inventory.yml host_vars/plane.yml

# One-time vault password (lives outside the repo so multiple ansible
# projects on the same controller can share it).
mkdir -p ~/.config/ansible
openssl rand -hex 24 > ~/.config/ansible/aac-coding-vault-pass
chmod 600 ~/.config/ansible/aac-coding-vault-pass

ansible-playbook plane.yml
```

After ~12 minutes, the controller has:

- `ansible/vault/secrets.yml` — encrypted; contains the admin
  password.
- `ansible/out/plane-agent-tokens-<host>.yml` — eleven API tokens.

Agent accounts are API-only — no UI password is persisted. If you
ever need to log in as a specific agent (e.g. to inspect what it
sees in Plane), reset that account's password via Plane's admin UI.

Copy these into the consumer project's `.claude/`:

```bash
cd /path/to/my-project
/path/to/trail-aiac/bin/install.py .         # seeds .claude/

# Edit .claude/config.yaml:
#   plane.base-url      → https://<domain_plane>/
#   plane.workspace     → <plane_workspace.slug>
#   plane.projects.dev  → <identifier of dev project>
#   agents.<name>.email → <persona-username>@<plane_agent_email_domain>
#
# Edit .claude/credentials.yaml:
#   plane.agent-tokens.<persona>           ← from plane-agent-tokens-<host>.yml

/path/to/trail-aiac/bin/install.py .         # re-run, this time
                                                       # also renders MCP wiring
```

For full Ansible reference (TLS strategies, idempotency, tear-down,
secret rotation): [`PROVISIONING.md`](PROVISIONING.md).

## Scenario 2 — Existing Plane, no agent accounts

Same as scenario 1 but skip the Plane stack rollout:

```bash
cd /path/to/trail-aiac/ansible
cp inventory.yml.example inventory.yml                # ansible_host = your existing Plane host
cp host_vars/plane.yml.example host_vars/plane.yml    # domain_plane + plane_workspace.slug

# Bootstrap token: one workspace API token belonging to a workspace
# Admin. Mint it in the Plane UI under Workspace Settings → API
# tokens, paste into vault/secrets.yml as plane.admin_token.
cp vault/secrets.example.yml vault/secrets.yml
mkdir -p ~/.config/ansible
openssl rand -hex 24 > ~/.config/ansible/aac-coding-vault-pass
chmod 600 ~/.config/ansible/aac-coding-vault-pass
ansible-vault encrypt vault/secrets.yml
ansible-vault edit vault/secrets.yml --ask-vault-pass

ansible-playbook plane.yml --tags plane_users,plane_bootstrap
```

The rest is identical to scenario 1: copy `out/*.yml` into the
consumer's `.claude/`, run `bin/install.py`.

## Scenario 3 — Existing Plane with agent accounts

You already have the eleven persona accounts in your Plane (any way you
got there — manual UI, your own provisioning, an earlier run of this
playbook). All you need is to bring the framework into a consumer
project:

```bash
cd /path/to/my-project
/path/to/trail-aiac/bin/install.py .
```

Edit `.claude/config.yaml` and `.claude/credentials.yaml` by hand
(the format is documented inline in the `.example` siblings). Then:

```bash
/path/to/trail-aiac/bin/install.py .
```

The second run renders `settings.local.json`, `.mcp.json`, and
templates the per-persona `.claude/agents/*.md` with the inlined
tokens.

## What `install.py` does

| Path in `<consumer>/.claude/`                                 | Re-install behaviour                                          |
|---------------------------------------------------------------|---------------------------------------------------------------|
| `agents/`, `skills/`, `commands/`, `mcp/`, `settings.json`    | overwritten on every run (framework updates)                  |
| `config.yaml`, `credentials.yaml`                             | seeded once, never overwritten thereafter                     |
| `context/`                                                    | seeded once; preserved unless `--force-seed`                  |
| `agent-memory/`                                               | seeded once, **never** overwritten (even with `--force-seed`) |
| `<consumer>/.mcp.json`, rendered `agents/*.md`                | re-rendered on every re-install when config + credentials are populated (mode 0600) |
| `settings.local.json`                                         | its `env` key is re-rendered; every other key you put there is preserved (mode 0600) |

That last row is what makes `settings.local.json` the right home for a
consumer's own Claude Code settings. `.claude/settings.json` is a
framework deliverable and is overwritten on every run, so anything you
add there is lost. Local scope survives — which is where
`claude plugin install --scope local` writes `enabledPlugins`, the way
to give one consumer a plugin such as an LSP server for its stack.

Rendering also expands the framework's **shared prompt partials**
(`claude/partials/`) into every persona and command file that carries a
`<!-- TRAIL:INCLUDE <name> -->` marker — one source, N rendered copies.
Partials are not copied into the consumer; only their expanded text
appears. See [`PERSONAS.md`](PERSONAS.md) § *Shared prompt partials*.

`agent-memory/` is permanent: once an agent has accumulated memory,
re-installing the framework — including `--force-seed` for context —
never touches those files. To reset memory, remove the directory
manually and re-run.

## Optional: herdr

Trail works without [herdr](https://herdr.dev). Inside a herdr terminal
its hooks label each session (persona, ticket, handovers), `/autopilot`
can run each stage as its own herdr session, and a herdr-app **mod**
shows all of it in the window: tabs named after their persona, a side
panel, and a toast for each handover. Everything is switched in the
`herdr:` block of `config.yaml`.

The mod lives on the computer that shows the herdr window. Pick the
case that fits:

- **Window and repos on the same computer** (the usual case): nothing
  to do. `install.py` installs the mod when it finds a herdr-app home
  (`$HERDR_APP_HOME` or `~/.config/herdr-app`), and updates it on every
  re-run. It prints one `herdr mod:` line. Opt out with `herdr.mod: off`
  or `--no-herdr-mod`.
- **Window on another computer** (herdr attached over SSH): run once
  from the framework checkout, and again after framework updates:

  ```bash
  python3 bin/herdr_mod.py --ssh <window-host>
  ```

  It needs only `ssh` and `python3` on that host. Nothing else is
  copied or installed there.
- **Window on a computer you cannot ssh *into*** (a Windows laptop that
  attaches herdr to your Linux box, for example): pull instead. On the
  window's computer, where `ssh <repo-host>` works because herdr uses
  it too:

  ```bat
  cmd /c "ssh <repo-host> python3 <path-to>/trail-aiac/bin/herdr_mod.py --emit | python -"
  ```

  `--emit` prints a self-contained installer; `python -` runs it
  against the local herdr-app home (`%APPDATA%\herdr-app` on Windows
  when `~/.config/herdr-app` is not there; `HERDR_APP_HOME` overrides).
  Use `cmd /c` from PowerShell so the pipe stays byte-exact. It needs
  Python on that computer.

Both paths share `bin/herdr_mod.py`, so they behave the same:

- A mod you edited, or another mod already named `trail`, is never
  overwritten. You get one line saying so; `--force` replaces it.
- If `herdr-app` is on PATH, the new version must pass
  `herdr-app check`. If it fails, the previous version is put back.
- `--uninstall` removes the mod, with the same protection.

Details on the labels and the mod: [`herdr/README.md`](../herdr/README.md).

## After install

```bash
cd /path/to/my-project
claude
> /kickoff   # one-time bootstrap of .claude/context/*.md from the project
> /ba ...    # start your first Story
```

`/kickoff` is a slash command that drafts the 12 context files
(`product`, `roadmap`, `stack`, `architecture`, …) by reading your
project's `README.md`, `pyproject.toml` / `package.json`, and top-level
docs. It runs in the main Claude Code loop (not a subagent) so you can
confirm or edit each draft as it lands.

After kickoff, dispatch the personas via slash commands or `@<name>`:
`/gm`, `/ba`, `/re`, `/sa`, `/sr`, `/bd`, `/ud`, `/tm`, `/tw`, `/rm`, `/mm`.
See [`WORKFLOW.md`](WORKFLOW.md) for the full ticket lifecycle and
[`PERSONAS.md`](PERSONAS.md) for what each agent does.

# Security Policy

## Reporting a vulnerability

Please do **not** open a public GitHub issue for security problems.

Use **GitHub Private Vulnerability Reporting**:

https://github.com/mahmadhuebsch/trail-aiac/security/advisories/new

This routes the report through GitHub's encrypted advisory flow.
If you do not have a GitHub account, contact the project maintainer
[@mahmadhuebsch](https://github.com/mahmadhuebsch) and we'll arrange
an alternative channel.

Please include:

- A short description of the issue.
- The shortest reproduction you can produce.
- The component(s) affected — installer, persona prompts, Ansible
  roles, supplementary MCP, or something else.
- Your assessment of severity and blast radius, if you have one.

You should expect an acknowledgement within **5 business days**. We
aim to share an initial triage (accept / need-more-info / out-of-scope)
within **10 business days** of acknowledgement.

## Supported versions

Trail is in early beta. There is no LTS line yet — security fixes
are made on `main` and released as point versions. If you are running
the framework in production, track `main` and re-install via
`bin/install.py` after each release.

## Scope

In scope:

- The framework deliverables under `claude/` (persona prompts,
  skills, slash commands, supplementary MCP).
- The installer `bin/install.py` and the multi-consumer linker
  `bin/link-shared.py`.
- The Ansible playbook and roles under `ansible/`.

Out of scope:

- Issues in third-party software the framework integrates with —
  Plane, Anthropic's Claude Code CLI, Ansible itself. Please report
  those upstream.
- Findings that require a malicious operator with full host access
  (Ansible playbooks already grant the operator root on the target
  host — that's by design).

## Disclosure

We coordinate disclosure with the reporter. Default policy is a
public advisory after a fix has shipped to `main` and tagged
release; a longer embargo is possible by mutual agreement when
downstream consumers need time to upgrade.

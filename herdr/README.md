# herdr integration

Trail runs fine without [herdr](https://herdr.dev). Inside a herdr
terminal, two hooks in `claude/hooks/` label each Claude Code session,
and the mod in this folder shows those labels in the herdr window.

| Label | Set by | Meaning |
|---|---|---|
| `trail.persona` | `persona-pin.py`, on every `/<command>` | the persona (or lane) the session is in |
| `trail.ticket` | `persona-pin.py` | the work-item that command named, cleared when it named none |
| `trail.handover` | `handover-signal.py`, after a Plane reassignment | `<to> <ID> <unix time>`, on the sending terminal |
| `trail.lane` | `/autopilot` with `herdr.autopilot_sessions: on` | `autopilot` on each stage session |

All of it is switched in the consumer's `config.yaml`, block `herdr:`
(see `claude/config.yaml.example`).

## The `trail` mod

`mods/trail/` is a herdr-app mod. It is **not** installed by
`bin/install.py`, because it belongs on the computer that shows the
herdr window, which may not be the one the consumer repos live on.

What it does:

- names an **unnamed** tab after its persona (`BA`, `RE`, …) and an
  unnamed space after its ticket. Names someone gave stay.
- shows a side panel with pending handovers and each space's persona
  sessions with their status. A click goes to that session.
- posts one toast per handover. Clicking it goes to the receiving
  persona's tab in the same space, or opens one with `/<cmd> <ID>`.
  That click is USER starting the turn. The mod never types into a
  session.

Install it on the window's computer:

```sh
mkdir -p ~/.config/herdr-app/mods
cp -r herdr/mods/trail ~/.config/herdr-app/mods/
herdr-app check ~/.config/herdr-app/mods/trail
```

Herdr picks it up on save and docks it on the right the first time.
To update, copy the folder again. To remove it, delete the folder.

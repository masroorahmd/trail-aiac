# Trail

A side panel for Trail persona sessions (a spec-driven multi-agent
framework for Claude Code and Plane). Each
Claude Code session that runs a Trail persona (`/ba`, `/re`, …) shows up
under its space with its status and ticket. When a persona hands a
work-item on in Plane, a toast says who got it, and one click goes to
that persona's tab or opens it. Unnamed tabs are named after their
persona and unnamed spaces after their ticket.

## What you see

- A panel docked on the right, 240px wide, on the theme's `surface`.
- A `Trail` heading in the theme's foreground, semibold.
- **Pending handovers**, newest first: one row each on `raised`,
  `BA → RE` in `accent`, the work-item ID in `muted`, truncated.
- Then one group per space: the space name in `muted`, then one row per
  persona session: an 8px status dot (theme `working`, `blocked`,
  `done`, `idle`), the persona code (`BA`, `RE`, `SA`, `SR`, `BD`, `UD`,
  `TM`, `TW`, `RM`, `GM`, `MM`; a lane like `/autopilot` shows `AUTOPILOT`)
  in a 44px column, and the session's ticket in `dim`.
- With no persona sessions: "No persona sessions yet. Start one with
  /ba, /re, …" in `dim`.

## How it behaves

- Status dots follow the agent's status live.
- A session row click runs `agent.focus` on that terminal.
- A handover row click, or the toast's click: if the receiver is `user`,
  focus the sending session; if a session with the receiving persona is
  in the sender's space, focus it (one with the same ticket first);
  otherwise `tab.new` in that space, named after the persona, in the
  sender's folder, with `argv: ["claude", "/<cmd> <ID>"]`. The row then
  disappears for this viewer.
- One toast per handover: title `BA → RE · CRTHVN-198`, level `warning`
  when it is for the user, else `info`.
- An unnamed tab holding a persona session is renamed to the persona
  code; an unnamed space whose sessions all name one ticket is renamed
  to it. Named tabs and spaces are never touched.

## Built from

- `View` + `div` from gpui-kit, `v_flex` / `h_flex` from gpui-base.
- herdr: `agents()`, `spaces()`, `panes()`, `hc()`, `run()`, `notify()`,
  `theme()`; commands `agent.focus`, `tab.new`, `tab.rename`,
  `space.rename`.
- Data comes from terminal labels written by Trail's Claude Code hooks:
  `trail.persona`, `trail.ticket`, and `trail.handover` =
  `<to> <ID> <unix time>` on the **sending** terminal. `agents()` has no
  labels, so the mod runs `hc get <address> --json` (qualified as
  `<machine>/<address>` for a space on another machine), but only for
  agents whose `seq` changed since the last read; a 4-second timer
  compares `seq` in memory and makes no calls when nothing changed.
- `localStorage` keeps the handovers a viewer already followed
  (`trail.dismissed`, last 200).

## Watch out

- Runs programs: `hc get` on every changed agent. No network access, no
  files outside its folder.
- A handover only shows after the sending session's status changes
  again, because that is what bumps its `seq`.
- Labels are written by Trail's hooks; without Trail the panel stays
  empty.
- `tab.new` starts the persona with its slash command as a launch
  argument, never with a typed message: `hc send` wraps text in
  `<hc>` tags, and the slash command would not run.

## Done when

- `herdr-app check` passes.
- Starting `/ba DEV-1` in an unnamed tab renames it `BA` and lists it
  under its space with a status dot.
- A Plane reassignment from that session to the requirements engineer
  posts one `BA → RE · DEV-1` toast; clicking it focuses the RE tab in
  that space, or opens one running `/re DEV-1`.

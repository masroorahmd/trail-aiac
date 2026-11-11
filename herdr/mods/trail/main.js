// Trail — persona sessions and handovers in the herdr window.
//
// Reads the labels Trail's hooks put on each Claude Code terminal:
//   trail.persona   the persona the last /<command> started (persona-pin)
//   trail.ticket    the work-item that command named (persona-pin)
//   trail.handover  "<to> <ID> <unix time>" after a Plane reassignment
//                   (handover-signal), set on the SENDING terminal
//
// and does three things with them:
//   1. names an unnamed tab after its persona (BA, RE, …) and an unnamed
//      space after its ticket. A name someone gave stays.
//   2. shows a panel: pending handovers first, then each space's
//      persona sessions with their status.
//   3. posts one toast per handover. Clicking it, or the panel row,
//      goes to the receiving persona's tab in the same space, or opens
//      one with `/<cmd> <ID>`. Starting that turn stays USER's click.
//
// Labels are not in `agents()`, so the mod asks `hc get` for them, but
// only for an agent whose `seq` moved since the last ask. A quiet
// window costs no calls.

import { View, div } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { agents, spaces, panes, hc, run, notify, theme } from "herdr";

const CMD = {
  "general-manager": "gm",
  "business-analyst": "ba",
  "requirements-engineer": "re",
  "software-architect": "sa",
  "security-reviewer": "sr",
  "backend-developer": "bd",
  "ui-developer": "ud",
  "test-manager": "tm",
  "technical-writer": "tw",
  "release-manager": "rm",
  "marketing-manager": "mm",
};

const short = (persona) =>
  persona === "user" ? "you" : (CMD[persona] ?? persona).toUpperCase().slice(0, 8);

const POLL_MS = 4000;
const STORE_KEY = "trail.dismissed";
const KEEP_DISMISSED = 200;

export default class Trail extends View {
  init(_props, cx) {
    this.labels = {}; // agent address -> its labels
    this.asked = {}; // agent address -> seq we last read labels at
    this.toasted = new Set(); // handover keys already toasted
    this.dismissed = this.load();
    this.busy = false;
    cx.timer.every(POLL_MS, (cx) => this.refresh(cx));
    this.refresh(cx);
  }

  load() {
    try {
      return new Set(JSON.parse(localStorage.getItem(STORE_KEY) ?? "[]"));
    } catch {
      return new Set();
    }
  }

  save() {
    try {
      const keep = [...this.dismissed].slice(-KEEP_DISMISSED);
      localStorage.setItem(STORE_KEY, JSON.stringify(keep));
    } catch {
      // per-viewer convenience only
    }
  }

  // An address `hc` on this computer can reach: `machine/t7` for a
  // terminal whose space lives on another machine.
  reachable(agent) {
    if (agent.address.includes("/")) return agent.address;
    const space = spaces().find((s) => s.id === agent.space);
    return space?.machine ? `${space.machine}/${agent.address}` : agent.address;
  }

  refresh(cx) {
    if (this.busy) return;
    const live = agents();
    const stale = live.filter((a) => this.asked[a.address] !== a.seq);
    if (!stale.length) return;
    this.busy = true;
    cx.spawn(async (cx) => {
      try {
        for (const a of stale) {
          try {
            const r = await hc(["get", this.reachable(a), "--json"]);
            if (r.code === 0) this.labels[a.address] = JSON.parse(r.stdout).labels ?? {};
          } catch {
            // unreachable machine or a terminal that just ended
          }
          this.asked[a.address] = a.seq;
        }
        const gone = new Set(live.map((a) => a.address));
        for (const addr of Object.keys(this.labels)) {
          if (!gone.has(addr)) delete this.labels[addr];
        }
        this.nameThings();
        this.toastHandovers();
      } finally {
        this.busy = false;
      }
      cx.notify();
    });
  }

  // Trail sessions: agents with a persona label, plus their space/tab.
  sessions() {
    return agents()
      .map((a) => ({ agent: a, labels: this.labels[a.address] ?? {} }))
      .filter((s) => s.labels["trail.persona"]);
  }

  nameThings() {
    const all = spaces();
    for (const s of this.sessions()) {
      const space = all.find((p) => p.id === s.agent.space);
      const tab = space?.tabs.find((t) => t.id === s.agent.tab);
      if (tab && !tab.named) {
        run("tab.rename", { id: tab.id, name: short(s.labels["trail.persona"]) });
      }
    }
    for (const space of all) {
      if (space.named) continue;
      const tickets = new Set(
        this.sessions()
          .filter((s) => s.agent.space === space.id && s.labels["trail.ticket"])
          .map((s) => s.labels["trail.ticket"]),
      );
      if (tickets.size === 1) run("space.rename", { id: space.id, name: [...tickets][0] });
    }
  }

  // Pending handovers, newest first, each with where to send USER.
  handovers() {
    const list = [];
    const sessions = this.sessions();
    for (const a of agents()) {
      const raw = (this.labels[a.address] ?? {})["trail.handover"];
      if (!raw) continue;
      const [to, item, ts] = raw.split(" ");
      if (!to || !item) continue;
      const key = `${a.address} ${raw}`;
      if (this.dismissed.has(key)) continue;
      const from = (this.labels[a.address] ?? {})["trail.persona"] ?? "?";
      const inSpace = sessions.filter(
        (s) => s.agent.space === a.space && s.labels["trail.persona"] === to,
      );
      const target =
        inSpace.find((s) => s.labels["trail.ticket"] === item) ?? inSpace[0] ?? null;
      list.push({ key, from, to, item, ts: Number(ts) || 0, sender: a, target });
    }
    return list.sort((x, y) => y.ts - x.ts);
  }

  // The command a click runs: focus the receiver, or open its tab.
  action(h) {
    if (h.to === "user") return { name: "agent.focus", args: { terminal: h.sender.address } };
    if (h.target) return { name: "agent.focus", args: { terminal: h.target.agent.address } };
    const cmd = CMD[h.to];
    if (!cmd) return { name: "agent.focus", args: { terminal: h.sender.address } };
    const pane = panes().find((p) => p.pane === h.sender.pane);
    return {
      name: "tab.new",
      args: {
        space: h.sender.space,
        name: short(h.to),
        folder: pane?.cwd ?? undefined,
        argv: ["claude", `/${cmd} ${h.item}`],
      },
    };
  }

  toastHandovers() {
    for (const h of this.handovers()) {
      if (this.toasted.has(h.key)) continue;
      this.toasted.add(h.key);
      const where = h.to === "user" ? "needs you" : h.target ? "tab is ready" : "click to open its tab";
      notify({
        title: `${short(h.from)} → ${short(h.to)} · ${h.item}`,
        body: where,
        level: h.to === "user" ? "warning" : "info",
        action: this.action(h),
      });
    }
  }

  go(h) {
    const a = this.action(h);
    run(a.name, a.args);
    this.dismissed.add(h.key);
    this.save();
  }

  render(_cx) {
    const t = theme();
    const pending = this.handovers();
    const bySpace = new Map();
    for (const s of this.sessions()) {
      const name = s.agent.space_name;
      if (!bySpace.has(name)) bySpace.set(name, []);
      bySpace.get(name).push(s);
    }

    const dot = (status) => div().w(8).h(8).rounded(4).flex_none().bg(t[status] ?? t.dim);

    return v_flex()
      .size_full()
      .bg(t.surface)
      .p(10)
      .gap(8)
      .text_size(13)
      .overflow_y_scrollbar()
      .child(div().font_semibold().text_color(t.foreground).child("Trail"))
      .when(pending.length > 0, (el) =>
        el.child(
          v_flex().gap(4).children(
            pending.map((h) =>
              h_flex()
                .id(`h-${h.key}`)
                .gap(6)
                .px(6)
                .py(4)
                .rounded(4)
                .bg(t.raised)
                .hover((s) => s.bg(t.hover))
                .on_click(() => this.go(h))
                .child(div().text_color(t.accent).child(`${short(h.from)} → ${short(h.to)}`))
                .child(div().flex_1().truncate().text_color(t.muted).child(h.item)),
            ),
          ),
        ),
      )
      .when(bySpace.size === 0, (el) =>
        el.child(div().text_color(t.dim).child("No persona sessions yet. Start one with /ba, /re, …")),
      )
      .children(
        [...bySpace.entries()].map(([space, list]) =>
          v_flex()
            .gap(2)
            .child(div().text_color(t.muted).truncate().child(space))
            .children(
              list.map((s) =>
                h_flex()
                  .id(`s-${s.agent.address}`)
                  .gap(6)
                  .px(6)
                  .py(2)
                  .rounded(4)
                  .items_center()
                  .hover((el) => el.bg(t.hover))
                  .on_click(() => run("agent.focus", { terminal: s.agent.address }))
                  .child(dot(s.agent.status))
                  .child(div().w(44).flex_none().text_color(t.foreground).child(short(s.labels["trail.persona"])))
                  .child(div().flex_1().truncate().text_color(t.dim).child(s.labels["trail.ticket"] ?? "")),
              ),
            ),
        ),
      );
  }
}

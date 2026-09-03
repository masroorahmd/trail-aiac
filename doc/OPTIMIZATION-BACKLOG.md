# Optimization backlog

Candidate improvements to the framework, captured from a brainstorming
session on 2026-08-20. Nothing here is committed work — this is a
holding pen so the reasoning survives, including the reasoning for the
ideas that were judged *not* worth their cost.

Entries are grouped by the lever they pull, not by priority. The
recommended order is at the bottom.


## 1. Enforce instead of prompt

The framework currently relies almost entirely on personas *obeying*
rules: description-once, English artefacts, the work-item ID in every
commit subject, the order of the state spine. Every one of those is
mechanically checkable, and every one of them today costs prompt
tokens on every turn in every file it appears in.

Moving them into Claude Code hooks wins twice: the rule holds harder,
and the prompt gets smaller. That is the direct answer to the ratchet
problem CLAUDE.md already names — a persona whose prompt reads as a
compliance checklist starts behaving like a compliance clerk.

Candidates:

- **PreToolUse on `plane__*__update_work_item`** — block any call that
  carries a `description` change. Description-once stops being a
  sentence in `plane-handover` and becomes a property of the system.
- **`commit-msg` hook** — enforce the work-item ID prefix.
  `claude/partials/git-history.md` shrinks to the rationale.
- **State-transition check** — validate a state change against the
  spine before it is written, instead of describing the spine in
  every persona prompt.
- **Language guard** on Plane bodies/comments and on files under
  `context/` and `agent-memory/`. This deployment runs `chat_language:
  German` with English artefacts, which is precisely the configuration
  that produces language leakage.

Hard checks are scripts. Only the fuzzy ones (is this actually English
prose, does this DoD comment really restate the acceptance criteria)
need a model, and a small local one suffices — see §3.


## 2. A conformance suite for the framework itself

Install into a throwaway consumer repo, run headless
(`claude -p "/ba …"`) against a disposable Plane project, assert on the
resulting work items.

The point is not regression-catching for its own sake. It is what makes
the **deletion pass** safe: today a rule can only be added, because
removing one is a bet with no way to observe the outcome. With a
golden-path harness you can delete a rule and see whether behaviour
actually degrades. Without it the ratchet only ever turns one way.

Related: Claude Code's `claude plugin eval` already provides a suite
format and runner; worth checking whether it fits before building
something bespoke.


## 3. A local small model (Qwen3 8B, 100k context)

Expectation management first. A 100k window at 8B is not 100k usable
tokens — realistically 10–30k before reliability degrades. And as a
**sparring partner for architecture or strategy it is not viable**: it
produces plausible-sounding shallow objections, and the triage cost
lands on the scarcest resource in the setup, which is human attention.

It earns its keep wherever the job is **classification against a fixed
rubric** rather than open judgement:

- **Router, not critic.** Before `/sr`: given the CM-N guardrails from
  `control-manifest.md` and a diff, answer YES/NO/UNSURE per guardrail.
  UNSURE routes to SR, the rest does not. Same shape for autopilot's
  `max_risk_lane` classification, for the `/quick`-vs-full-spine call,
  and for routing an incoming idea to HQ / BIZ / DEV / MKT. A wrong
  answer there is cheap; a right one saves a full-lane turn.
- **Handover compression.** The largest hidden cost in Trail is that
  every persona re-reads a ticket's comment thread. A locally generated
  "state of the story" digest cached under `.claude/cache/` takes that
  from ~6k tokens to ~800. Constraint: compress only the *narrative*
  comments. Normative ones (acceptance criteria, DoD, handover blocks)
  must survive verbatim or the spine drifts.
- **Privacy pre-stage for the HQ track.** The strongest case. The
  General Manager works with Behörden, Notar, Steuern and staffing —
  real personal data in real documents. A local model that extracts
  structured, anonymised fields from those PDFs before anything moves
  toward a cloud model is the correct design, not merely the cheap one.
- **Transcript mining.** CLAUDE.md mandates a periodic deletion pass
  but gives no evidence base for it. A local batch run over session
  transcripts — which rules ever actually fired, where personas asked
  the same question repeatedly — supplies one. Human review follows
  anyway, so 8B is sufficient.

Explicitly *not* worth it: code generation, test-fixture synthesis,
open-ended review of Opus output.


## 4. Embeddings

Not worth it for "RAG over the repo". The corpus is small (about 20
context files, 11 memory files) and grep plus the agent's own search
beats vector search at that scale.

Two genuine embedding problems remain:

- **Work-item dedup.** Eleven personas file `Follow-up:` items.
  Semantically identical tickets with zero keyword overlap are exactly
  what keyword search misses. A similarity check against a local index
  of open items, run before `create_work_item`, prevents board rot.
- **Traceability.** Requirement ↔ code ↔ test ↔ doc. "Which acceptance
  criterion does this test cover?" / "Which doc does this diff
  falsify?" Embeddings propose candidates, the large model verifies.
  This sharpens RE and TM, and across a linked multi-consumer setup it
  surfaces drift between `product.md` and the two websites before it
  compounds.

Agent-memory retrieval becomes a candidate once the per-persona
MEMORY.md files grow large. Not yet.


## 5. Smaller items

- **Local read-model for Plane.** `plane-id-cache` removed the UUID
  round-trips. The next step is a script-refreshed local mirror of the
  work-item tree: personas read locally, write only through MCP. Saves
  latency and tokens on every turn.
- **Autopilot run log as a file.** An autopilot run is currently one
  long turn. A structured per-run log (SKIP-N decisions, repair
  iterations, where the risk lane triggered) makes the hand-back
  reviewable and yields statistics on which spine stages actually pay.
- **Per-turn cost accounting.** Which persona burns the most tokens,
  where autopilot loops. Feeds the deletion pass with data instead of
  intuition.
- **Cross-repo release train.** In a multi-consumer setup the Release
  Manager coordinates per repo, but application, MCP server, UI tests,
  docs and both websites ship together. A release manifest spanning the
  repos is the logical extension of `bin/link-shared.py`.


## Done

- **§1, the MCP tool surface (2026-08-21).** Identity moved out of the
  tool name into a `persona` argument: 286 tools → 26, 179 KB of schema
  → 23 KB, ~39k tokens off every request in every session. The
  guarantee the prefix only *looked* like it gave is now two hooks —
  `persona-pin.py` records which `/<persona>` USER started,
  `plane-persona-guard.py` denies a Plane call that disagrees. Knob:
  `hooks.persona_identity`.
- **Parallel reads (2026-08-21).** The `reading` partial (renamed from
  `reading-large-files`) now says independent reads go out in one
  message. A pickup step's numbered list says *what* to read, not in
  what order, and each solo read re-sends the whole prompt before it.

Neither was on this list as a *latency* item, which is the gap the list
still has: it was written against tokens and correctness. For wall-clock
the dominant term is round-trips × context size, and the ranking that
follows from it is different from the one below — the tool surface and
parallel reads come first, and a composite `pickup` MCP call (item §5's
local read-model, in a much smaller form) ranks above the local model.

## Recommended order

1. **Hooks (§1)** — lowest cost, hardest guarantee, and the only item
   that makes the prompts *smaller* rather than larger.
2. **Local model at the CM-N router (§3)** — highest value per line of
   code once the hook surface exists to host it.
3. **Conformance suite (§2)** — unlocks safe deletion, which is what
   keeps 1 and 2 from silently rotting.
4. **Embeddings for dedup (§4)**, then traceability.

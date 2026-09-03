## Shared context lives in a second repo — you finish the write there

In a multi-consumer setup (`bin/link-shared.py`) `.claude/context/*.md`
and `.claude/agent-memory/**` are symlinks into a sibling
`claude-context` repo. `Edit` refuses a symlink, so resolve the path and
edit the target — and resolve the owning repo from a path you actually
wrote:

```
ctx=$(git -C "$(dirname "$(readlink -f .claude/context/product.md)")" \
        rev-parse --show-toplevel)
```

A write there lands in a **second repository's** working tree. This
repo's `git status` never shows it and this repo's commit never carries
it, so an uncommitted write there reaches nobody: not the other
consumers, not the next clone, not you tomorrow. It reads as work you
never did. **The write is not finished until it is committed and pushed
in that repo**, at the end of the turn that wrote it:

```
git -C "$ctx" add <the files you wrote this turn>   # never -A, never -a
git -C "$ctx" commit -m "<subject>"
git -C "$ctx" push
```

- **This needs no separate USER trigger.** The trigger you wait for is
  the one that authorises the *write*; the commit is that write's tail.
  Leaving it uncommitted is the failure mode, not the commit.
- **Stage only the paths you wrote this turn.** Another consumer's
  session may have edits in flight in that same tree, and `-A` would
  sweep them into your commit under your reasoning.
- **Never stage `credentials.yaml`.** It is symlinked into that same
  tree and carries every persona's Plane token, so the shared repo
  gitignores it. If `git -C "$ctx" status` shows it anyway, leave it and
  tell USER — that is a gitignore bug there, not a file for you to
  commit. `config.yaml` may well be tracked in that repo, but it is not
  yours to change either: a dirty one is somebody else's edit.
- **The commit-subject rule holds there too**: the work-item ID leads
  the subject when the write serves one. When it serves none, do not
  invent one — `TRAIL_SKIP_COMMIT_GUARD=1 git -C "$ctx" commit …` if the
  consumer's guard is set to `strict`.
- **A rejected push is a rebase, not a force.** `git -C "$ctx" pull
  --rebase` once, then push again. If that conflicts, or the repo has no
  upstream, leave the commit standing and say so — never `--force`.
- **Say what you did.** Name the shared file and the repo you committed
  it to in your reply, and when a Story's scope is fenced to this repo,
  say in your handover that the write happened outside the fence.

None of this applies when the path is an ordinary file: in a
single-consumer install these live in this repo and travel with its
commits under the normal rules — the `ctx` command above printing *this*
repo's root is the tell. And a persona subagent running under
`AUTOPILOT-MODE` touches no git at all — it names the shared file it
wrote in its handover, and the orchestrator's git step commits it.

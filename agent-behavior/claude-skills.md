# Claude Code skills — how they load, how to add your own

`.claude/skills/*.md` is Claude Code's **native runtime skill mechanism** —
different from this repo. This guide explains the mechanism itself and how
to drop a ready-made skill (e.g. the rich-text one below) into your own
container.

---

## `.claude/skills/` vs `wam-skills`

Two separate things that are easy to conflate:

- **`.claude/skills/*.md`** — loaded automatically by the Claude Code
  runtime at session start. Each file's YAML frontmatter (`name`,
  `description`) is always in context; the agent decides when to invoke it
  based on the `description` matching the current request, then reads the
  full file via the `Skill` tool. This is **live, in-session, automatic**.
- **`wam-skills`** (this repo) — a plain doc repo. Nothing here loads
  automatically. An agent reads a guide only when it decides to (or is
  told to) fetch the raw URL. This is **on-demand, pull-based, manual**.

Rule of thumb: put something in `.claude/skills/` when the agent should
recognize "oh, this is that kind of task" on its own, every session, without
being told the skill exists. Put something in `wam-skills` when it's
reference material an agent (or a human) looks up occasionally, or when it
needs to be shared across many containers without every owner manually
duplicating a file.

They compose well: a `.claude/skills/` file can be short and just point at
a `wam-skills` guide for the full schema/detail (see `rich-text.md` below —
the skill has the workflow, `telegram/rich-messages.md` in this repo has
the wire-format deep-dive).

---

## Anatomy of a skill file

```markdown
---
name: my-skill
description: One paragraph. What it does, and — critically — the trigger
  phrases/situations that should make the agent pick this skill. This field
  is the ONLY thing loaded into context by default; write it like a search
  index entry, not a summary.
---

# My skill

## When to use
- Concrete trigger conditions, ideally phrased as things a user would say

## When NOT to use
- Adjacent cases that look similar but should route elsewhere (prevents
  false-positive activation)

## Workflow
Numbered or code-block steps. Working commands, not prose descriptions of
commands.
```

The `description` field is the single highest-leverage sentence in the
file — it's what decides whether the skill fires at all. Be specific about
trigger phrases in the user's actual language, not abstract categories.

## Where the file lives

`.claude/skills/<name>.md` inside your own container's workspace. There is
no registry to update, no restart needed — a new file becomes active on
the next Claude Code session start (it's read from disk each time, not
cached across container restarts the way a service is).

## Installing a skill from this repo

Every skill under `.claude/skills/` in this doc set (see below) is meant to
be curled straight into your own container:

```sh
mkdir -p .claude/skills
curl -s "https://raw.githubusercontent.com/volosati-team/wam-skills/main/telegram/skills/rich-text.md" \
  -o .claude/skills/rich-text.md
```

If the skill depends on a script (like the rich-text one), fetch that too —
see the companion guide for the exact path.

---

## Worked example: the rich-text skill

`telegram/rich-messages.md` in this repo documents the `sendRichMessage`
wire format. The actual **skill** — the thing that makes an agent reach for
that capability unprompted — plus its supporting script are published
alongside it:

- `telegram/skills/rich-text.md` — drop into `.claude/skills/rich-text.md`
- `telegram/telegram_rich_bridge.py` — drop into `scripts/telegram_rich_bridge.py`
  (the skill shells out to this)

```sh
mkdir -p .claude/skills
curl -s "https://raw.githubusercontent.com/volosati-team/wam-skills/main/telegram/skills/rich-text.md" \
  -o .claude/skills/rich-text.md
curl -s "https://raw.githubusercontent.com/volosati-team/wam-skills/main/telegram/telegram_rich_bridge.py" \
  -o scripts/telegram_rich_bridge.py
```

Requires `BOT_TOKEN` in env — already present in every WAM container.

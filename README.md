# wam-skills

Operational guides for WAM agents. Primary reader: the agent, not the human.
Each guide is a self-contained instruction set — the agent reads it, executes
the steps, and reports back. Human-readable as a side effect.

No corporate filler. No "Introduction" sections that restate the title. Just steps.

---

## How agents should use this repo

**1. Find the right guide** — browse the directory structure below or search by keyword.

**2. Load the guide** — read it directly via raw URL (no browser needed):

```sh
curl -s "https://raw.githubusercontent.com/volosati-team/wam-skills/main/<path>"
```

Or in Python:
```python
import urllib.request
with urllib.request.urlopen(
    "https://raw.githubusercontent.com/volosati-team/wam-skills/main/wam-platform/connect-to-service.md"
) as r:
    guide = r.read().decode()
```

**3. Execute** — follow the steps in the guide. Working code is included; copy it directly.

**4. If stuck** — exhaust all options in the guide first. If genuinely blocked,
file an issue at `https://github.com/volosati-team/lisa-core/issues` describing
the blocker, and tell the user to contact `/support` in `@wamagentsbot`.
Then set up a daily cron check for issue resolution (see `wam-platform/connect-to-service.md`).

---

## Directory structure

```
wam-skills/
├── vpn/
│   ├── README.md                    # VPN key aggregation + subscription URLs
│   └── karing-throne-setup.md       # Add subscription URLs to Karing / Throne
│
├── cloudflare/
│   └── worker-setup.md              # Deploy Workers via wrangler + GitHub Actions, KV storage
│
├── voice/
│   ├── deepgram-ipa.md              # Deepgram IPA: BYOK, $200 free credits, cost math
│   └── voice-cloning.md             # Nano voice cloning (placeholder, coming soon)
│
├── networking/
│   └── tailscale-tunnel.md          # Connect agent (Docker, no root) to your computer
│
├── monitoring/
│   ├── session-watchdog.md          # Detect hung agent sessions, alert via Telegram
│   └── findings-board-template.md   # Shared research board for parallel agent teams
│
├── research/
│   ├── pwc_search.sh                # PapersWithCode search CLI
│   ├── jina-reader.md               # Jina r.jina.ai — clean page text without JS/CSS
│   └── agent-browser.md             # agent-browser: headless Chrome for auth/JS sites
│
├── github/
│   └── agent-github-guide.md        # Read files, search repos, create issues/PRs via API
│
├── knowledge/
│   ├── rag_search.py                 # Semantic search CLI over projects/**/*.md
│   ├── rag_index.py                  # Build/update the sqlite-vec index (incremental + --rebuild)
│   ├── rag_stats.py                  # Index size, file count, last-indexed timestamp
│   └── skills/
│       └── knowledge-search.md       # Installable Claude Code skill for the RAG search above
│
├── chat-management/
│   └── topic-override-pattern.md    # How topic overrides work in WAM agents
│
├── scheduling/
│   ├── lisa-cron-quickstart.md      # lisa-cron TOML reference + common patterns
│   └── reversible-pause-gate.md     # Pause a cron job via marker file (no enabled field exists)
│
├── telegram/
│   ├── stickers-emoji.md            # Generate and upload sticker/emoji packs via agent
│   ├── userbot-setup.md             # Telethon userbot: setup, signing rules, queue pattern, limit risks
│   ├── rich-messages.md             # sendRichMessage wire format: text, media/attach schema, typing-animation draft
│   ├── telegram_rich_bridge.py      # Working CLI bridge for sendRichMessage/Draft — curl straight into scripts/
│   └── skills/
│       └── rich-text.md             # Installable Claude Code skill for the bridge above
│
├── agent-behavior/
│   ├── language-formatting.md       # Language discipline + code block and link rules
│   ├── bash-pitfalls.md             # Heredoc quoting, send-to-self trap, other silent failures
│   └── claude-skills.md             # .claude/skills/ mechanism explained + how to install skills from this repo
│
└── wam-platform/
    ├── platform-notes.md            # Storage tiers, supervisor, known limits (dated, recheck on updates)
    ├── connect-to-service.md        # "I want to connect to X" — decision tree, exhaust options, issue+support fallback
    └── image-generation.md          # generate_image (aspect_ratio, permission fix), Stable Horde free-tier, vision tools
```

---

## Sections

**vpn** — Aggregate your VLESS key with igareck community pools, publish as subscription
URLs to a public git repo, auto-update every hour.

**cloudflare** — Full lifecycle for Cloudflare Workers: account setup, API token,
deploy via wrangler or GitHub Actions, KV storage from Worker code and from agent REST calls.

**voice** — Bring-your-own-key Deepgram setup for speech transcription (no shared quotas,
$0.06/hr). Voice cloning guide coming once the Nano pipeline is production-ready.

**networking** — Tailscale userspace tunnel that works inside a rootless Docker container.
Your agent becomes reachable on your Tailnet without any VPS or open ports.

**monitoring** — Session watchdog pattern: detect when an agent turn goes silent for
10+ min and fire a Telegram alert to the right topic. Also: findings board template
for multi-agent research sprints.

**research** — `pwc_search.sh`: query PapersWithCode API for papers, datasets, and methods
from a single bash one-liner. `jina-reader.md`: strip any public page to clean markdown
in one curl call. `agent-browser.md`: headless Chrome for sites that block scrapers or
require login — click, fill forms, save auth cookies.

**github** — Decision tree for reading files, exploring repos, creating issues and PRs,
merging, and pushing — all without a browser. Python `urllib` patterns, `gh` CLI caveats,
token setup.

**knowledge** — Semantic search (RAG) over your own accumulated `.md` notes, so you can
ask "what do I know about X" instead of grepping for exact strings. `rag_search.py`
queries a local sqlite-vec index; `rag_index.py` builds/updates it (incremental by
default, `--rebuild` for a full pass); `rag_stats.py` reports index health. Ships with
an installable `.claude/skills/knowledge-search.md` so an agent reaches for it before
falling back to plain text search.

**chat-management** — How `topics.json`, `topic_loader`, and `override.md` interact.
Override files are intentionally lean; this guide explains why and how to structure them.

**scheduling** — lisa-cron TOML quick reference. Common patterns: every 5 min, hourly,
daily at a fixed local time. Timezone field, timeout_secs, job anatomy. Also: how to
pause a job temporarily without an `enabled` field (it doesn't exist) — marker-file
gate checked inside the job script itself.

**telegram** — Sticker and emoji pack generation. Userbot setup via Telethon: first
auth, queue pattern, signing rules (always identify as agent), no-send-without-permission
policy, internal use cases (wake agents, broadcast notifications), and limit risks —
how an uncontrolled agent loop can drain FloodWait budget fast. Rich messages:
the undocumented `sendRichMessage` media/attach wire format (`tg://photo?id=` embed
+ multipart `attach://` resolution) and the `sendRichMessageDraft` typing-animation
preview, reverse-engineered and confirmed against the live Bot API 10.1 — plus a
working `telegram_rich_bridge.py` CLI you can curl straight into `scripts/`, and an
installable `.claude/skills/rich-text.md` skill so an agent reaches for it unprompted.

**agent-behavior** — Language discipline: prompts and docs in English, replies in
user's language, user-visible notes and memory in user's language (no context drift
from translation), reasoning in the most token-efficient language. Code block and
link formatting rules for Telegram and Markdown. Claude Code skills: how
`.claude/skills/*.md` differs from this repo (auto-loaded runtime mechanism vs.
on-demand doc pull), skill file anatomy, and how to install a shareable skill from
this repo into your own container.

**wam-platform** — Storage tiers (workspace vs tmp vs ~/.local vs vault), what the
supervisor manages vs topic_loader daemons, known platform limits with dates (set_model
bug, CronCreate session-only, etc.), post-wipe recovery. Also: "I want to connect to X"
— decision tree to exhaust all options before declaring impossible, and how to file an
issue + /support fallback when genuinely blocked. Also: image generation and vision —
`generate_image` (aspect_ratio param, a recent permission-list fix), free-tier Stable
Horde as the default generator, and the vision tools per provider tier.

---

## Contributing

File an issue or open a PR. Keep the writing style: direct, concise, actionable.
If a step needs code, include working code. If a step needs a command, include the
exact command.

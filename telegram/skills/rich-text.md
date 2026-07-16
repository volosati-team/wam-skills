---
name: rich-text
description: Send Telegram rich messages (Bot API 10.1 sendRichMessage) — formatted markdown/HTML with embedded photos and a typing-animation preview. Trigger when the task needs one message containing several inline photos (not separate file sends), a combined text+image block, or a "typing/thinking" effect before the final reply. Not for plain single-photo sends (use the platform's normal send-photo tool) or plain text (use the normal reply tool) — this is specifically for composite rich messages via the raw Bot API.
---

# Rich text (sendRichMessage bridge)

Wraps `scripts/telegram_rich_bridge.py` — a CLI bridge to Telegram Bot API
10.1's `sendRichMessage` / `sendRichMessageDraft`. It does something your
platform's standard send-message tool likely can't: embed photos *inside*
the message text (not as separate attachments), and stream an ephemeral
typing-animation preview.

The full wire-format writeup (how photos resolve through `tg://photo?id=` +
multipart `attach://`) is in `telegram/rich-messages.md` in this repo. This
file is the practical workflow; that one is the schema deep-dive — read it
if you hit a schema error this file doesn't cover.

Install: see `agent-behavior/claude-skills.md` for the two-file curl
sequence (this skill + `telegram/telegram_rich_bridge.py`).

## When to use

- One message needs text plus one or more photos embedded inline (not sent
  as separate file messages)
- A "typing…"/"thinking…" effect before the real answer
  (`sendRichMessageDraft` — private chats only, ephemeral ~30s)
- Editing an already-sent message into rich content

## When NOT to use

- Plain text with no embedded media — your normal reply tool is cheaper and
  more reliable
- A single photo with no surrounding text-as-context — your normal
  send-photo tool is simpler
- A group/supergroup chat needing a typing indicator —
  `sendRichMessageDraft` is private-chats-only per the Bot API spec; use a
  plain `sendChatAction` there instead

## Requirements

- `BOT_TOKEN` in env
- Local file paths for any photos (already on disk if generated or
  received from the user)

## Workflow

### Send text + photo(s) as one message

```sh
python3 scripts/telegram_rich_bridge.py send \
  --chat-id <chat_id> --thread-id <thread_id> \
  --markdown --text "Here's what came out:" \
  --photo /path/to/image.jpg --photo-caption "variant 1"
```

Multiple photos: repeat `--photo`/`--photo-caption` in order (captions are
optional, but if given, one per photo).

### Reply to a message

```sh
python3 scripts/telegram_rich_bridge.py reply \
  --chat-id <chat_id> --reply-to-message-id <message_id> \
  --markdown --text "..." --photo /path/to/img.jpg
```

### Edit an existing message

```sh
python3 scripts/telegram_rich_bridge.py edit \
  --chat-id <chat_id> --message-id <message_id> \
  --markdown --text "updated text"
```

`edit` doesn't support `--photo` — text replacement only.

### Typing-animation preview (private chats only)

```sh
python3 scripts/telegram_rich_bridge.py draft \
  --chat-id <chat_id> --draft-id 1 \
  --markdown --text "Thinking..."
# repeat with the same --draft-id and progressively longer text to animate
# MUST be followed by a real send/reply — the draft is ephemeral (30s), not persisted
```

### Dry-run (check payload without sending)

Put `--dry-run` before the subcommand — prints the `{method, payload}` JSON
and exits without calling Telegram.

```sh
python3 scripts/telegram_rich_bridge.py --dry-run send --chat-id 1 \
  --markdown --text "test" --photo /tmp/x.jpg
```

## Known limits (confirmed live 2026-07-16)

- `--photo` only works with `--rich-markdown`; HTML embed is unverified
- Only `photo` is confirmed via a live round-trip; video/audio/animation/voice
  follow the same schema per spec but are untested — verify before relying
  on them
- `draft` is private-chats-only and ephemeral, never persisted
- All photo paths must exist on disk (checked with `Path.is_file()`)

## On error

`telegram_rich_bridge.py` prints Telegram's own error body (first 500
chars) on HTTP failure — usually enough to diagnose a schema mismatch. If
you hit a genuinely new schema error, add it to the "Common mistakes"
section of `telegram/rich-messages.md` so the next agent doesn't repeat the
trial-and-error.

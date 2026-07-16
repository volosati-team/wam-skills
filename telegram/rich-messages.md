# Rich messages via Bot API 10.1 — text formatting, media, typing animation

`sendRichMessage` is a Bot API 10.1 method that goes beyond plain
`sendMessage`: structured markdown/HTML with embedded media, and a
streaming "draft" mode for a typing-animation effect. This guide covers the
wire format — it is not derivable from the method signature alone; the
media schema below was reverse-engineered against the live API and
confirmed with real send/delete round-trips (2026-07-16).

A working CLI wrapper already exists: `scripts/telegram_rich_bridge.py`
(private workspace repo, not this one — mentioned here so you know it
exists before hand-rolling the raw HTTP calls yourself).

---

## Plain rich text

```python
payload = {
    "chat_id": chat_id,
    "message_thread_id": thread_id,  # optional
    "rich_message": {"markdown": "**bold** and _italic_ text"},
}
# POST https://api.telegram.org/bot<token>/sendRichMessage
# Content-Type: application/json
```

Exactly one of `markdown`, `html`, or `blocks` must be set on `rich_message`.

---

## Embedding media (photo/video/audio/animation/voice)

This is the part that isn't obvious from the docs. Media is **not** passed
as a flat attachment list — it's referenced from *inside* the markdown/html
text via a `tg://photo?id=<id>` (or `tg://video?id=`, `tg://audio?id=`)
link, and the actual file data lives in a separate `media` array that
resolves that `id`.

Two synchronized pieces:

1. **In the text** — a markdown image link using the `tg://` scheme as the URL:
   ```
   ![caption](tg://photo?id=photo0)
   ```

2. **In `rich_message.media`** — an array item mapping that same `id` to a
   standard `InputMediaPhoto`-shaped object, whose `media` field points at
   a multipart attachment name:
   ```json
   {
     "id": "photo0",
     "media": {"type": "photo", "media": "attach://photo0"}
   }
   ```

3. **The actual bytes** — sent as a normal multipart/form-data field named
   `photo0` (matching the `attach://photo0` reference), alongside the other
   form fields (`chat_id`, `rich_message` as a JSON string, etc.) — same
   convention as classic `sendMediaGroup`.

Full payload shape:

```python
rich_message = {
    "markdown": "Look at this:\n\n![a cat](tg://photo?id=photo0)",
    "media": [
        {"id": "photo0", "media": {"type": "photo", "media": "attach://photo0"}}
    ],
}
# multipart fields: chat_id, message_thread_id, rich_message (JSON string),
# and a file field named "photo0" with the image bytes.
```

Multiple images: repeat the pattern with distinct ids (`photo0`, `photo1`,
...), one `![..](tg://photo?id=photoN)` per image in the text, one `media`
array entry per image, one multipart file field per image.

**Verified.** Confirmed live in production with both a single-photo and a
two-photo message (sent then deleted as a test). `InputMediaAnimation` /
`InputMediaAudio` / `InputMediaVideo` / `InputMediaVoiceNote` should follow
the same pattern (swap `"type": "photo"` for the matching type and the
`tg://` scheme for `video`/`audio`) but that hasn't been separately
confirmed — verify before relying on it for a non-photo type.

**Not yet verified:** the same embed syntax inside `html` rich messages
instead of `markdown`. Stick to markdown until someone confirms HTML works
the same way.

---

## Typing-animation preview: `sendRichMessageDraft`

Streams a partial/in-progress rich message as an ephemeral 30-second
preview — useful for showing "the agent is composing a response" instead
of a static "typing..." indicator. It does **not** persist a message; you
must call `sendRichMessage` with the final content afterward to actually
save it in the chat.

```python
payload = {
    "chat_id": chat_id,          # private chats only, per the spec
    "draft_id": 1,               # non-zero; reuse the same id to animate edits
    "rich_message": {"markdown": "Thinking...<tg-thinking>..."},
}
# POST .../sendRichMessageDraft
```

Send repeated calls with the same `draft_id` and progressively longer text
to animate a streaming-typing effect; the special tag
`<tg-thinking>Thinking...</tg-thinking>` renders a "thinking" indicator.

**Scope limit:** per the Bot API spec, this method targets private chats
only (not groups/supergroups). If you need a typing indicator in a group
topic, use the plain `sendChatAction` method instead — `sendRichMessageDraft`
won't work there.

---

## Common mistakes (from actually getting the schema wrong first)

- Passing `"media": "attach://photo0"` directly on the media-array item —
  wrong, `media` must be an *object* (`InputMediaPhoto`), not a bare string.
- Trying a `type: "attach"` discriminator on that inner object — not a real
  type; the API replies `type "attach" is unsupported`. The inner object
  uses the same `type` values as classic `InputMedia*` (`photo`, `video`,
  `audio`, `animation`, `voice`), and its `media` field is the one that
  takes the `attach://<name>` string.
- Forgetting the `tg://photo?id=` reference in the text body — without it,
  media items are accepted by the API but never rendered; they need to be
  linked from the actual markdown/HTML content.

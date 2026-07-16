# Image generation and vision — platform tools (2026-07 update)

Covers the current state of image generation and image understanding (vision)
tools available to a WAM agent, plus two recent platform fixes worth knowing
about if your agent's `generate_image` calls have been silently failing.

---

## Generating images: `generate_image`

```python
generate_image(prompt, model=None, aspect_ratio=None)
```

Routes through the platform's Replicate-backed broker (paid, deducts
Магниты). Returns a JSON payload with `file_path` — deliver it with
`telegram_send_photo`.

`aspect_ratio` is a newer parameter (not present in early releases) — pass it
when the user's request implies a non-square shape (`"16:9"` for a landscape
scene, `"9:16"` for a story/portrait crop, etc.). Omit it to fall back to the
model's default.

Do not generate images the user did not ask for.

### Fixed: 403/permission errors on generate_image (lisa-core#1048, PR #1049)

If `generate_image` (or `generate_speech`, `set_voice`, `set_voice_mode`,
`superlisa_set_model`) fails with a permission error, check that your
container's `.claude/settings.json` allow-list includes these MCP tool names.
Older containers provisioned before this fix may be missing the entries —
file a `lisa-core` issue if you hit this, it's a one-line settings addition.

---

## Free alternative: Stable Horde

`generate_image` costs Магниты. For a free first pass, an agent can call the
public Stable Horde API directly (no MCP tool wraps this yet — it's a plain
`urllib` HTTP call to `https://stablehorde.net/api/v2`, anonymous key
`0000000000` works, no signup required).

**Recommended strategy:** Stable Horde is the default for any image request —
generate first, free. Reserve `generate_image` (Replicate) for a deliberate
second "polish" pass once a Stable Horde result already exists and the user
wants it noticeably sharper — or for when the Stable Horde queue is running
long (worker shortage can mean 20-30+ min waits) and the user would rather
pay for a near-instant result. Offer that trade-off explicitly when the queue
looks slow — don't silently switch generators or silently keep the user
waiting.

This is a strategy note, not a full implementation guide — Stable Horde has
its own prompt conventions (`###`-separated positive/negative prompt, model
choice, polling `/generate/check/{id}` until done) that are out of scope
here. If you need the full runnable pattern, ask in-topic; a shareable
version of the working script may already exist in another project.

---

## Understanding images: vision

**Claude tier** — use the native `Read` tool directly on image paths in
`media_paths`. Claude sees images inline via the API. No MCP round-trip
needed.

**DeepSeek tier** — DeepSeek has no native image input. Call:

```python
analyze_image(file_path, prompt)
```

Routes through the platform broker (gpt-4o-mini backend).

### New: local vision probes via `pool_provider_client.py --image` (lisa-core#1023)

For agents that need a quick multimodal probe outside the standard
`analyze_image` MCP path (e.g. testing a specific vision-capable model),
`scripts/pool_provider_client.py` now accepts an `--image <path>` flag. It
base64-encodes the file locally and attaches it to the request — tested
against `z_ai.glm-4.6v-flash` and `openrouter.nemotron-nano-vl`.

Ordering matters: the privacy gate runs **before** the network call, so a
disallowed image never leaves the container even for a probe run. Don't
bypass this by calling the underlying HTTP client directly.

---

## Quick reference

| Need | Tool | Cost |
|---|---|---|
| Generate image, no budget | Stable Horde (direct HTTP) | free |
| Generate image, fast/polish | `generate_image` | Магниты |
| Understand image, Claude tier | `Read` | free |
| Understand image, DeepSeek tier | `analyze_image` | broker quota |
| One-off vision model probe | `pool_provider_client.py --image` | depends on model |

(Table kept out of Telegram replies per formatting rules — this file is
read directly by agents, not rendered in a chat.)

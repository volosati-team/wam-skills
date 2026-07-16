#!/usr/bin/env python3
"""Send or edit Telegram rich messages through direct Bot API calls.

Owner-flow alpha/beta bridge for lisa-core#580. This is intentionally separate
from the WAM MCP transport: it proves the Bot API path while the platform source
for mcp__wam__telegram_* remains outside this repository.

Media attach and the sendRichMessageDraft typing-animation method were added
for lisa-core#1055. The InputRichMessageMedia schema (media referenced via
tg://photo?id=<id> links inside the markdown/html body, resolved through a
matching multipart field name) is not guessable from the method signature
alone — it was reverse-engineered against the live Bot API 10.1 changelog
and confirmed with a real send/delete round-trip (2026-07-16).
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

BOT_TOKEN_ENV = "BOT_TOKEN"


class BridgeError(RuntimeError):
    pass


def _read_body(inline: str | None, from_stdin: bool) -> str:
    if inline is not None and from_stdin:
        raise BridgeError("pass either --text or --stdin, not both")
    if from_stdin:
        body = sys.stdin.read()
    elif inline is not None:
        body = inline
    else:
        raise BridgeError("pass --text or --stdin")
    if not body.strip():
        raise BridgeError("message body is empty")
    return body


def _rich_message(markdown: str | None, html: str | None) -> dict[str, str]:
    if bool(markdown) == bool(html):
        raise BridgeError("pass exactly one of --rich-markdown or --rich-html")
    if markdown is not None:
        return {"markdown": markdown}
    return {"html": html or ""}


def _attach_media(rich: dict[str, Any], photos: list[str], captions: list[str]) -> dict[str, str]:
    """Embed tg://photo?id= markers for each --photo into the markdown body and
    return {attach_field_name: local_path} for the multipart uploader.

    HTML rich messages aren't supported here yet — only the markdown embed
    syntax (`![caption](tg://photo?id=...)`) has been verified against the
    live API.
    """
    if "html" in rich:
        raise BridgeError("--photo is only supported with --rich-markdown for now")
    if len(captions) not in (0, len(photos)):
        raise BridgeError("pass one --photo-caption per --photo, or none")
    attachments: dict[str, str] = {}
    media: list[dict[str, Any]] = []
    lines = [rich["markdown"], ""]
    for i, path in enumerate(photos):
        if not Path(path).is_file():
            raise BridgeError(f"photo not found: {path}")
        field = f"photo{i}"
        caption = captions[i] if captions else ""
        lines.append(f"![{caption}](tg://photo?id={field})")
        media.append({"id": field, "media": {"type": "photo", "media": f"attach://{field}"}})
        attachments[field] = path
    rich["markdown"] = "\n".join(lines)
    rich["media"] = media
    return attachments


def build_payload(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    if args.command == "send":
        rich = _rich_message(args.rich_markdown, args.rich_html)
        if args.photo:
            args.attachments = _attach_media(rich, args.photo, args.photo_caption or [])
        payload: dict[str, Any] = {
            "chat_id": args.chat_id,
            "rich_message": rich,
        }
        if args.thread_id is not None:
            payload["message_thread_id"] = args.thread_id
        return "sendRichMessage", payload

    if args.command == "reply":
        rich = _rich_message(args.rich_markdown, args.rich_html)
        if args.photo:
            args.attachments = _attach_media(rich, args.photo, args.photo_caption or [])
        payload = {
            "chat_id": args.chat_id,
            "rich_message": rich,
            "reply_parameters": {"message_id": args.reply_to_message_id},
        }
        if args.thread_id is not None:
            payload["message_thread_id"] = args.thread_id
        return "sendRichMessage", payload

    if args.command == "edit":
        rich = _rich_message(args.rich_markdown, args.rich_html)
        return "editMessageText", {
            "chat_id": args.chat_id,
            "message_id": args.message_id,
            "rich_message": rich,
        }

    if args.command == "draft":
        rich = _rich_message(args.rich_markdown, args.rich_html)
        payload = {
            "chat_id": args.chat_id,
            "draft_id": args.draft_id,
            "rich_message": rich,
        }
        if args.thread_id is not None:
            payload["message_thread_id"] = args.thread_id
        return "sendRichMessageDraft", payload

    raise BridgeError(f"unknown command: {args.command}")


def _build_multipart(fields: dict[str, Any], attachments: dict[str, str]) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for name, value in fields.items():
        body = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        parts.append(body.encode("utf-8"))
        parts.append(b"\r\n")
    for field, path in attachments.items():
        content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        filename = Path(path).name
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode()
        )
        parts.append(f"Content-Type: {content_type}\r\n\r\n".encode())
        parts.append(Path(path).read_bytes())
        parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), boundary


def call_bot_api(
    method: str, payload: dict[str, Any], token: str, attachments: dict[str, str] | None = None
) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    if attachments:
        body, boundary = _build_multipart(payload, attachments)
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
    else:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise BridgeError(f"telegram {method} failed: HTTP {exc.code} {body[:500]}") from exc
    if not result.get("ok"):
        raise BridgeError(f"telegram {method} failed: {json.dumps(result, ensure_ascii=False)}")
    return result


def _add_rich_args(parser: argparse.ArgumentParser) -> None:
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="rich message body")
    source.add_argument("--stdin", action="store_true", help="read rich message body from stdin")
    fmt = parser.add_mutually_exclusive_group(required=True)
    fmt.add_argument("--markdown", dest="format", action="store_const", const="markdown")
    fmt.add_argument("--html", dest="format", action="store_const", const="html")


def _finalize_rich_args(args: argparse.Namespace) -> None:
    body = _read_body(args.text, args.stdin)
    args.rich_markdown = body if args.format == "markdown" else None
    args.rich_html = body if args.format == "html" else None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Telegram rich-message owner-flow bridge")
    parser.add_argument("--dry-run", action="store_true", help="print method/payload without calling Telegram")
    sub = parser.add_subparsers(dest="command", required=True)

    send = sub.add_parser("send", help="send a rich message")
    send.add_argument("--chat-id", required=True, type=int)
    send.add_argument("--thread-id", type=int)
    send.add_argument("--photo", action="append", default=[], help="local image path; repeatable")
    send.add_argument("--photo-caption", action="append", default=[], help="caption for the matching --photo, in order")
    _add_rich_args(send)

    reply = sub.add_parser("reply", help="send a rich reply")
    reply.add_argument("--chat-id", required=True, type=int)
    reply.add_argument("--thread-id", type=int)
    reply.add_argument("--reply-to-message-id", required=True, type=int)
    reply.add_argument("--photo", action="append", default=[], help="local image path; repeatable")
    reply.add_argument("--photo-caption", action="append", default=[], help="caption for the matching --photo, in order")
    _add_rich_args(reply)

    edit = sub.add_parser("edit", help="replace a message with rich content")
    edit.add_argument("--chat-id", required=True, type=int)
    edit.add_argument("--message-id", required=True, type=int)
    _add_rich_args(edit)

    draft = sub.add_parser(
        "draft",
        help="stream a partial rich message (typing-animation preview, private chats only, "
        "ephemeral 30s — must be followed by a real send/reply to persist it)",
    )
    draft.add_argument("--chat-id", required=True, type=int)
    draft.add_argument("--thread-id", type=int)
    draft.add_argument("--draft-id", required=True, type=int, help="non-zero; reuse the same id to animate a stream of edits")
    _add_rich_args(draft)

    args = parser.parse_args(argv)
    _finalize_rich_args(args)
    if not hasattr(args, "photo"):
        args.photo = []
    if not hasattr(args, "photo_caption"):
        args.photo_caption = []
    args.attachments = {}
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        method, payload = build_payload(args)
        if args.dry_run:
            print(json.dumps({"method": method, "payload": payload}, ensure_ascii=False, indent=2))
            return 0
        token = os.environ.get(BOT_TOKEN_ENV, "")
        if not token:
            raise BridgeError(f"{BOT_TOKEN_ENV} is not set")
        result = call_bot_api(method, payload, token, args.attachments)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except BridgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

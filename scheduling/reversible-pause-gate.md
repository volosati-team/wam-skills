# Reversible pause-gate for cron jobs

You need to pause a lisa-cron job temporarily — an owner says "stop pinging me
for now" — without deleting the schedule or restarting the daemon. lisa-cron's
`Job` config has no `enabled` field (see the correction note in
`lisa-cron-quickstart.md`), so you cannot just flip a flag in the TOML.

The reliable pattern: put the pause check **inside the job script itself**,
gated on a marker file.

---

## The pattern

```python
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]  # adjust to your script's depth
PAUSE_MARKER = WORKSPACE / "projects" / "my-topic" / ".my_job_paused"

def main() -> int:
    if PAUSE_MARKER.exists():
        print(f"paused ({PAUSE_MARKER.read_text().strip()}), skipping")
        return 0
    # ... normal job body ...
```

To pause: write the marker file with a short note (who paused it, when, why).
To resume: delete the marker file. No lisa-cron restart needed — the check
happens fresh on every scheduled invocation.

```sh
# pause
echo "paused by <owner> $(date -Iseconds) — reason" > projects/my-topic/.my_job_paused

# resume
rm projects/my-topic/.my_job_paused
```

---

## Why not just edit `lisa-cron.toml`?

You could comment out or remove the `[[jobs]]` block, but that:
- requires editing a config file most topics don't own (core-zone in some
  deployments),
- needs the daemon to notice the change (depends on your lisa-cron build —
  some poll the file, some don't),
- loses the schedule/timeout/command details unless you're careful, making
  "resume" error-prone (typos on re-add).

The marker-file pattern keeps the schedule untouched, is self-contained in
the job's own script (usually in your own project folder — no core-zone
approval needed), and "resume" is a single `rm`.

---

## Verify it actually works before trusting it

Don't just create the marker and assume — run the script manually once with
the marker present and confirm it exits clean with no side effect (no
message sent, no file written, no state mutated):

```sh
python3 scripts/my_job.py
# expect: "paused (...), skipping" and exit 0 — no downstream calls
```

---

## Contrast with other pause mechanisms

- **`session_watchdog.py --pause/--resume`** (see `monitoring/session-watchdog.md`)
  — that daemon has its own CLI flag because it's a long-running process you
  control interactively. One-shot cron scripts don't have a running process
  to send a flag to, so a marker file checked at the top of `main()` is the
  equivalent.
- **Deleting the `[[jobs]]` block** — use this only when the job is being
  retired permanently, not for a temporary pause you intend to lift.

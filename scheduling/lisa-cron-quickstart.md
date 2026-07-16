# lisa-cron quickstart

lisa-cron is the durable scheduler for WAM agents. Unlike `CronCreate` (session-only),
lisa-cron persists across restarts and survives container reboots.

Config lives in a TOML file. Jobs are standard cron expressions plus a few extras.

---

## Config file location

```
~/workspace/lisa-cron/lisa-cron.toml
```

The daemon watches this file and reloads automatically on change. No restart needed.

> **Correction (2026-07-15):** an earlier version of this guide named the file
> `jobs.toml` — the actual file is `lisa-cron.toml`. Verified against the live
> config at `lisa-cron/lisa-cron.toml`.

---

## Job anatomy

```toml
[[jobs]]
name        = "my-job"          # unique identifier, no spaces
schedule    = "*/5 * * * *"     # cron expression (or @reboot, @hourly, etc.)
command     = "python3 /home/superlisa/workspace/scripts/my_script.py"
timezone    = "Europe/Moscow"   # optional; defaults to UTC if omitted
timeout_secs = 60               # kill job if it runs longer than this
```

All fields except `name`, `schedule`, and `command` are optional.

> **Correction (2026-07-15):** there is no `enabled` field on the `Job` config
> (checked against `lisa-cron/src/config.rs` — the struct has no such field,
> and serde does not reject unknown fields, so an `enabled = false` line would
> silently do nothing rather than error). To pause a job temporarily without
> deleting its schedule, see
> [`reversible-pause-gate.md`](reversible-pause-gate.md) in this same folder.

---

## Common schedule patterns

```toml
# Every 5 minutes
schedule = "*/5 * * * *"

# Every hour (at :00)
schedule = "0 * * * *"

# Every hour at :30
schedule = "30 * * * *"

# Daily at 09:00 Moscow time
schedule = "0 9 * * *"
timezone = "Europe/Moscow"

# Daily at 09:00 and 21:00
schedule = "0 9,21 * * *"
timezone = "Europe/Moscow"

# Every weekday at 08:30
schedule = "30 8 * * 1-5"
timezone = "Europe/Moscow"

# On container/daemon restart
schedule = "@reboot"

# Shorthand for every hour
schedule = "@hourly"

# Shorthand for daily at midnight UTC
schedule = "@daily"
```

---

## Timezone field

Without `timezone`, all schedules are in UTC. For human-facing schedules
(morning briefings, reminders, report delivery) always set the timezone:

```toml
timezone = "Europe/Moscow"    # MSK (UTC+3)
timezone = "Asia/Yekaterinburg"
timezone = "UTC"
```

Timezone names follow the IANA timezone database.

---

## timeout_secs

Jobs that overrun `timeout_secs` are killed with SIGTERM (then SIGKILL after 5s).
Set conservatively — a stuck job blocking others is worse than a job timing out.

Recommended defaults:
- Short scripts (file ops, API calls): `30`
- Network-heavy jobs (fetching, uploading): `120`
- Heavy processing: `600`
- No timeout (use sparingly): omit the field

---

## Example: full jobs.toml with 4 jobs

```toml
# lisa-cron jobs configuration
# Reload is automatic — no daemon restart needed after editing this file.

[[jobs]]
name         = "vpn-sub-update"
schedule     = "0 * * * *"
command      = "python3 /home/superlisa/workspace/vpn-sub/update.py"
timezone     = "Europe/Moscow"
timeout_secs = 120

[[jobs]]
name         = "morning-briefing"
schedule     = "0 9 * * *"
command      = "python3 /home/superlisa/workspace/scripts/morning_brief.py"
timezone     = "Europe/Moscow"
timeout_secs = 60

[[jobs]]
name         = "log-rotation"
schedule     = "0 3 * * *"
command      = "python3 /home/superlisa/workspace/scripts/rotate_logs.py"
timezone     = "UTC"
timeout_secs = 30

[[jobs]]
name         = "session-watchdog-ensure"
schedule     = "@reboot"
command      = "python3 /home/superlisa/workspace/scripts/session_watchdog.py --ensure"
timeout_secs = 10
```

To pause a job like `daily-disabled` above without an `enabled` field, use the
marker-file pattern in
[`reversible-pause-gate.md`](reversible-pause-gate.md) instead of editing this
TOML.

---

## Checking job status

```sh
# List all registered jobs and their last run time
python3 /home/superlisa/workspace/scripts/lisa_cron_status.py

# View job output logs
tail -f /home/superlisa/workspace/lisa-cron/logs/vpn-sub-update.log
```

---

## Adding a job from your agent

The agent can edit `lisa-cron/lisa-cron.toml` directly (Level A — auto, no confirmation
needed for internal file edits). After writing the file, changes take effect within
one polling cycle (typically a few seconds).

---

## Do not use CronCreate for persistent tasks

`CronCreate` is session-only — it vanishes when the agent session ends or the
container restarts. Use it only for within-session polling loops.

For anything that needs to survive restarts: lisa-cron.

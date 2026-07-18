# Claude Usage Widget

A tiny always-on-top widget for the Windows desktop corner that shows your
real Claude subscription usage — the same numbers as the `/usage` panel in
Claude Code: **Session (5hr)**, **Weekly (7 day)**, and per-model weekly limits.

Collapsed, it's a single unobtrusive row. Double-click to expand into gauges.

**Collapsed**

![Collapsed view](Demo_Collapse.png)

**Expanded**

![Expanded view](Demo_Expanded.png)

## How it works

Data sources, in order:

1. **Live** — calls the official usage API (`api.anthropic.com/api/oauth/usage`)
   using the OAuth token Claude Code already stores at
   `~/.claude/.credentials.json`. The token is read and used locally only.
2. **Fallback** — if a fresh call can't be made (rate-limited, offline, token
   expired), it shows the **last successful live result** with the time it was
   fetched. If no live call has ever succeeded this session, it reads the
   `cachedUsageUtilization` blob Claude Code keeps in `~/.claude.json`.

The expanded view shows a **`LIVE`** / **`CACHED`** indicator next to the fetch
time so you always know how fresh the numbers are. These are **real official
numbers**, not estimates.

> The usage endpoint is shared with Claude Code itself and rate-limits
> aggressively, so the widget only refreshes live every few minutes and backs
> off further on rate limits — showing the last known numbers in between.

## Requirements

- Windows
- Python 3 (tkinter is included in the standard installer; no third-party packages)
- Claude Code installed and logged in (any subscription plan)

Works for **any user** — it reads from the current user's own home directory,
so just copy this folder to another machine and run it. No API key needed.

## Usage

| Action | Result |
|---|---|
| Double-click `start_claude_usage.vbs` | Start silently (no console window) |
| Double-click the widget | Toggle collapsed ⇄ expanded |
| Drag | Move the widget (it stays where you drop it) |
| Click the ✕ | Quit |

**Start on boot:** create a shortcut to `start_claude_usage.vbs` in the
Startup folder (`Win+R` → `shell:startup`).

## Files

- `claude_usage.py` — the widget (Python + tkinter, stdlib only)
- `start_claude_usage.vbs` — silent launcher (uses `pythonw`, no console)
- `config.json` — settings (auto-created on first run)

## Settings (`config.json`)

| Key | Description | Default |
|---|---|---|
| `refresh_seconds` | UI refresh interval in seconds | 60 |
| `opacity` | Window opacity 0–1 | 1.0 |
| `margin` | Margin from the bottom-right corner (px) | 16 |
| `taskbar_height` | Taskbar height to avoid (px) | 48 |
| `border` | Coral border thickness (px) | 1 |

Edit, save, then restart the widget.

## License

MIT — see [LICENSE](LICENSE).

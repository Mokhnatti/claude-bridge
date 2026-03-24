# Claude Bridge

Chat with [Claude Code](https://docs.anthropic.com/en/docs/claude-code) from anywhere — Telegram, Discord, or your browser.

![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue) ![License: MIT](https://img.shields.io/badge/license-MIT-green)

## Features

- **Multi-platform** — Telegram, Discord, and Web UI from a single config
- **Real-time progress** — see which tools Claude is using (Read, Edit, Bash, etc.)
- **Session persistence** — conversation continues across restarts
- **Stop button** — cancel long-running tasks instantly
- **Message history** — resend any previous response
- **Access control** — whitelist user IDs per platform
- **Shared core** — easy to add new adapters (Slack, Matrix, etc.)

## Architecture

```
                 ┌─── Telegram (aiogram)
                 │
core.py ─────────┼─── Discord (discord.py)
(Claude CLI      │
 session mgr)    └─── Web UI (FastAPI + WebSocket)
```

Each adapter is independent — run one, two, or all three.

## Quick Start

### 1. Prerequisites

- Python 3.10+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated

### 2. Install

```bash
git clone https://github.com/Mokhnatti/claude-bridge.git
cd claude-bridge
pip install -r requirements.txt
```

### 3. Configure

```bash
cp config.example.json config.json
# Edit config.json with your tokens
```

### 4. Run

```bash
# Telegram
python telegram_bot.py

# Discord
python discord_bot.py

# Web UI (open http://localhost:8585)
python web_server.py

# Desktop GUI (Telegram + settings)
python tg_bot_setup.py
```

## Configuration

All adapters share one `config.json`:

| Field | Description | Default |
|-------|-------------|---------|
| `claude_path` | Path to Claude Code CLI | `claude` |
| `work_dir` | Working directory for Claude | `.` |
| `model` | Claude model | `claude-sonnet-4-20250514` |
| `permission_mode` | Claude Code permission mode | `bypassPermissions` |
| `effort` | Effort level (low/medium/high) | `high` |
| `max_turns` | Max turns (null = unlimited) | `null` |
| `history_size` | Responses kept for resend | `20` |
| `bot_token` | Telegram bot token | — |
| `discord_token` | Discord bot token | — |
| `allowed_users` | Whitelisted user IDs | `[]` |
| `web_token` | Optional token for web UI auth | `""` |

## Commands

### Telegram
| Command | Description |
|---------|-------------|
| `/start` | Show info |
| `/new` | Reset session |
| `/status` | Current status |
| `/resend N` | Resend response N |
| `/stop` | Stop task |

### Discord
| Command | Description |
|---------|-------------|
| `!new` | Reset session |
| `!status` | Current status |
| `!resend N` | Resend response N |
| `!stop` | Stop task |

Send a DM or @mention the bot to chat.

### Web UI
Open `http://localhost:8585` in your browser. Enter sends, Shift+Enter for newline.

## Files

| File | Description |
|------|-------------|
| `core.py` | Claude session manager (shared by all adapters) |
| `telegram_bot.py` | Telegram adapter |
| `discord_bot.py` | Discord adapter |
| `web_server.py` | Web server + WebSocket API |
| `web/index.html` | Web chat UI (dark theme) |
| `tg_bot_setup.py` | Desktop GUI (Telegram + settings) |
| `config.example.json` | Config template |

## Adding a new adapter

1. Import `ClaudeSession` and `BridgeConfig` from `core.py`
2. Create a session: `session = ClaudeSession(BridgeConfig.from_dict(config))`
3. Stream responses: `async for event in session.query(prompt): ...`
4. Handle event types: `tool`, `text`, `result`, `error`, `stopped`

## Security

- **Never commit config.json** — it contains your tokens
- Config files are in `.gitignore`
- Use `allowed_users` to restrict access
- Set `web_token` to protect the web UI
- The bot runs Claude Code with your local credentials

## License

MIT

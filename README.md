# Claude Bridge

Telegram bot that bridges your chat with [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI. Send a message in Telegram — get a full Claude Code response with tool use, file editing, and session persistence.

![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue) ![License: MIT](https://img.shields.io/badge/license-MIT-green)

## Features

- **Real-time progress** — see which tools Claude is using (Read, Edit, Bash, etc.)
- **Session persistence** — conversation continues across restarts
- **Stop button** — cancel long-running tasks instantly
- **Message history** — resend any previous response with `/resend N`
- **Desktop GUI** — setup wizard + built-in chat client (dark theme)
- **Autostart** — optional Windows Task Scheduler integration
- **Access control** — whitelist Telegram user IDs

## Quick Start

### 1. Prerequisites

- Python 3.10+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- Telegram bot token from [@BotFather](https://t.me/BotFather)

### 2. Install

```bash
git clone https://github.com/Mokhnatti/claude-bridge.git
cd claude-bridge
pip install -r requirements.txt
```

### 3. Configure

**Option A — GUI setup (recommended):**
```bash
python tg_bot_setup.py
```
Fill in your bot token, set allowed users, and click Start.

**Option B — Manual:**
```bash
cp config.example.json tg_bot_v2_config.json
# Edit tg_bot_v2_config.json with your values
```

### 4. Run

```bash
# Bot only (headless)
python tg_claude_bot.py

# Desktop app (GUI + bot)
python tg_bot_setup.py
```

## Configuration

| Field | Description | Default |
|-------|-------------|---------|
| `bot_token` | Telegram bot token from BotFather | — |
| `allowed_users` | List of Telegram user IDs (empty = allow all) | `[]` |
| `claude_path` | Path to Claude Code CLI | `claude` |
| `work_dir` | Working directory for Claude | `.` |
| `model` | Claude model to use | `claude-sonnet-4-20250514` |
| `permission_mode` | Permission mode for Claude Code | `bypassPermissions` |
| `effort` | Effort level (low/medium/high) | `high` |
| `max_turns` | Max conversation turns (null = unlimited) | `null` |
| `history_size` | Number of responses to keep for /resend | `20` |

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Show bot info |
| `/new` | Start new conversation (reset session) |
| `/status` | Show current status |
| `/resend N` | Resend response number N |
| `/stop` | Stop current task |

## Architecture

```
Telegram <-> aiogram bot <-> Claude Code CLI (subprocess, stream-json)
                |
         Desktop GUI (tkinter) <-> shared chat_history.jsonl
```

The bot spawns Claude Code as a subprocess with `--output-format stream-json`, parses events in real-time, and forwards tool usage and responses to Telegram.

## Files

| File | Description |
|------|-------------|
| `tg_claude_bot.py` | Telegram bot (headless, can run standalone) |
| `tg_bot_setup.py` | Desktop GUI app (settings + chat + bot manager) |
| `tg_bot_start.bat` | Windows batch launcher |
| `config.example.json` | Config template |

## Security

- **Never commit your config file** — it contains your bot token
- Config files (`*config*.json`) are in `.gitignore`
- Use `allowed_users` to restrict access to your Telegram ID
- The bot runs Claude Code with your local credentials

## License

MIT

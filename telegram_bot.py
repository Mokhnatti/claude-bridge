"""
Claude Bridge — Telegram adapter.

Thin wrapper: receives messages from Telegram, passes to core, streams back.

Usage:
  python telegram_bot.py
  python telegram_bot.py --config path/to/config.json
"""

import asyncio
import json
import sys
import io
import os
import argparse
import logging
from pathlib import Path
from datetime import datetime

os.environ.pop("CLAUDECODE", None)

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ChatAction
from aiogram.client.default import DefaultBotProperties

from core import ClaudeSession, BridgeConfig, ClaudeEvent, split_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("bridge.telegram")

CONFIG_PATH = Path(__file__).parent / "config.json"

config = {}
session: ClaudeSession = None
bot: Bot = None
current_task: asyncio.Task = None


def kb_idle():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="\U0001f504 New chat"), KeyboardButton(text="\U0001f4ca Status")]],
        resize_keyboard=True, is_persistent=True,
    )


def kb_working():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="\U0001f6d1 Stop"), KeyboardButton(text="\U0001f4ca Status")]],
        resize_keyboard=True, is_persistent=True,
    )


dp = Dispatcher()


@dp.message(F.text == "\U0001f6d1 Stop")
@dp.message(F.text.lower().in_({"stop", "/cancel", "/stop"}))
async def handle_stop(message: types.Message):
    global current_task
    if session.is_busy and current_task:
        await session.stop()
        current_task.cancel()
        await message.answer("\U0001f6d1 Stopped.", reply_markup=kb_idle())
    else:
        await message.answer("Nothing to stop.", reply_markup=kb_idle())


@dp.message(F.text.in_({"\U0001f4ca Status", "/status"}))
async def handle_status(message: types.Message):
    s = session.get_status()
    now = datetime.now().strftime("%H:%M:%S")
    text = (
        f"\U0001f4ca Status ({now})\n"
        f"Session: {s['session']}\n"
        f"Model: {s['model']}\n"
        f"Mode: {s['permission_mode']}\n"
        f"Busy: {s['busy']}\n"
        f"Messages: {s['messages']}\n"
        f"CWD: {s['work_dir']}"
    )
    kb = kb_working() if session.is_busy else kb_idle()
    await message.answer(text, reply_markup=kb)


@dp.message(F.text.in_({"\U0001f504 New chat", "/new"}))
async def handle_new(message: types.Message):
    session.reset_session()
    await message.answer("\U0001f504 Session reset. Next message starts a new chat.", reply_markup=kb_idle())


@dp.message(F.text == "/start")
async def handle_start(message: types.Message):
    s = session.get_status()
    info = (
        "\U0001f916 Claude Bridge (Telegram)\n\n"
        f"Model: {s['model']}\n"
        f"Mode: {s['permission_mode']}\n"
        f"CWD: {s['work_dir']}\n\n"
        "Send a message \u2014 Claude will respond.\n\n"
        "\U0001f6d1 Stop \u2014 cancel task\n"
        "\U0001f504 New chat \u2014 reset session\n"
        "\U0001f4ca Status \u2014 info\n"
        "/resend N \u2014 resend response N"
    )
    await message.answer(info, reply_markup=kb_idle())


@dp.message(F.text.startswith("/resend"))
async def handle_resend(message: types.Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /resend N")
        return
    saved = session.get_response(int(parts[1]))
    if not saved:
        available = sorted(session.state.history.keys(), key=lambda x: int(x))
        await message.answer(f"Response [{parts[1]}] not found. Available: {', '.join(available) or 'none'}")
        return
    for part in saved:
        await message.answer(part)


@dp.message(F.text.startswith("/"))
async def handle_unknown_cmd(message: types.Message):
    await message.answer("Commands: /start /new /status /resend N /stop")


@dp.message()
async def handle_text(message: types.Message):
    global current_task
    allowed = config.get("allowed_users", [])
    if allowed and message.from_user.id not in allowed:
        await message.answer("\u26d4 Access denied.")
        return
    if session.is_busy:
        await message.answer("\u23f3 Wait or press \U0001f6d1 Stop", reply_markup=kb_working())
        return
    text = message.text or message.caption or ""
    if not text.strip():
        return
    log.info(f"[{message.from_user.first_name}] {text[:80]}")
    await message.answer("\u23f3 Thinking...", reply_markup=kb_working())
    current_task = asyncio.create_task(process_query(message.chat.id, text.strip()))


async def process_query(chat_id: int, prompt: str):
    typing_task = asyncio.create_task(_keep_typing(chat_id))
    tool_batch = []
    last_tool_flush = 0.0
    TOOL_FLUSH_INTERVAL = 3.0
    last_sent_text = ""

    async def flush_tools():
        nonlocal tool_batch, last_tool_flush
        if tool_batch:
            await bot.send_message(chat_id, "\n".join(tool_batch), reply_markup=kb_working())
            tool_batch = []
            last_tool_flush = asyncio.get_event_loop().time()

    try:
        async for event in session.query(prompt):
            now = asyncio.get_event_loop().time()

            if event.type == "tool":
                tool_batch.append(event.data)
                if (now - last_tool_flush) > TOOL_FLUSH_INTERVAL:
                    await flush_tools()

            elif event.type == "text":
                await flush_tools()
                last_sent_text = event.data
                for part in split_message(event.data, 3500):
                    await bot.send_message(chat_id, part, reply_markup=kb_working())

            elif event.type == "result":
                await flush_tools()
                if event.data and event.data.strip() != last_sent_text.strip():
                    n = session.store_response(event.data)
                    labeled = session.get_response(n)
                    for part in labeled:
                        await bot.send_message(chat_id, part, reply_markup=kb_idle())
                else:
                    await bot.send_message(chat_id, "DONE", reply_markup=kb_idle())

            elif event.type == "error":
                await bot.send_message(chat_id, f"\u274c Error: {event.data}", reply_markup=kb_idle())

            elif event.type == "stopped":
                await bot.send_message(chat_id, "\U0001f6d1 Stopped.", reply_markup=kb_idle())

    except asyncio.CancelledError:
        await bot.send_message(chat_id, "\U0001f6d1 Stopped.", reply_markup=kb_idle())
    except Exception as e:
        log.error(f"Error: {e}", exc_info=True)
        await bot.send_message(chat_id, f"\u274c Error: {e}", reply_markup=kb_idle())
    finally:
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass


async def _keep_typing(chat_id: int):
    try:
        while True:
            await bot.send_chat_action(chat_id, ChatAction.TYPING)
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


async def main():
    global bot, config, session

    parser = argparse.ArgumentParser(description="Claude Bridge — Telegram")
    parser.add_argument("--config", default=str(CONFIG_PATH))
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        log.error(f"Config not found: {config_path}")
        sys.exit(1)

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    if not config.get("bot_token"):
        log.error("bot_token not set!")
        sys.exit(1)

    bridge_config = BridgeConfig.from_dict(config)
    state_path = Path(__file__).parent / "telegram_state.json"
    session = ClaudeSession(bridge_config, state_path)

    bot = Bot(token=config["bot_token"], default=DefaultBotProperties(parse_mode=None))

    me = await bot.get_me()
    log.info(f"Bot: @{me.username} (ID: {me.id})")
    log.info(f"Model: {bridge_config.model}")
    log.info(f"CWD: {bridge_config.work_dir}")
    log.info("Listening...")

    await dp.start_polling(bot, skip_updates=True)


if __name__ == '__main__':
    asyncio.run(main())

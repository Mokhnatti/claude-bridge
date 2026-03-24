"""
Claude Bridge — Discord adapter.

Listens for DMs or mentions in a channel, passes to core, streams back.

Usage:
  python discord_bot.py
  python discord_bot.py --config path/to/config.json
"""

import asyncio
import json
import sys
import os
import argparse
import logging
from pathlib import Path
from datetime import datetime

os.environ.pop("CLAUDECODE", None)

import discord
from discord.ext import commands

from core import ClaudeSession, BridgeConfig, ClaudeEvent, split_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("bridge.discord")

CONFIG_PATH = Path(__file__).parent / "config.json"

config = {}
session: ClaudeSession = None
current_task: asyncio.Task = None

intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)


def is_allowed(user_id: int) -> bool:
    allowed = config.get("allowed_users", [])
    return not allowed or user_id in allowed


@bot.event
async def on_ready():
    log.info(f"Bot: {bot.user.name} (ID: {bot.user.id})")
    log.info(f"Model: {session.config.model}")
    log.info(f"CWD: {session.config.work_dir}")
    log.info("Listening...")


@bot.command(name="status")
async def cmd_status(ctx):
    if not is_allowed(ctx.author.id):
        return
    s = session.get_status()
    now = datetime.now().strftime("%H:%M:%S")
    text = (
        f"**Status** ({now})\n"
        f"Session: `{s['session']}`\n"
        f"Model: `{s['model']}`\n"
        f"Busy: {s['busy']}\n"
        f"Messages: {s['messages']}\n"
        f"CWD: `{s['work_dir']}`"
    )
    await ctx.reply(text)


@bot.command(name="new")
async def cmd_new(ctx):
    if not is_allowed(ctx.author.id):
        return
    session.reset_session()
    await ctx.reply("\U0001f504 Session reset. Next message starts a new chat.")


@bot.command(name="stop")
async def cmd_stop(ctx):
    global current_task
    if not is_allowed(ctx.author.id):
        return
    if session.is_busy and current_task:
        await session.stop()
        current_task.cancel()
        await ctx.reply("\U0001f6d1 Stopped.")
    else:
        await ctx.reply("Nothing to stop.")


@bot.command(name="resend")
async def cmd_resend(ctx, n: int):
    if not is_allowed(ctx.author.id):
        return
    saved = session.get_response(n)
    if not saved:
        available = sorted(session.state.history.keys(), key=lambda x: int(x))
        await ctx.reply(f"Response [{n}] not found. Available: {', '.join(available) or 'none'}")
        return
    for part in saved:
        await ctx.reply(part)


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    await bot.process_commands(message)

    if message.content.startswith("!"):
        return

    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mention = bot.user in message.mentions if hasattr(message, 'mentions') else False

    if not is_dm and not is_mention:
        return

    if not is_allowed(message.author.id):
        await message.reply("\u26d4 Access denied.")
        return

    if session.is_busy:
        await message.reply("\u23f3 Wait or use `!stop`")
        return

    text = message.content
    if is_mention:
        text = text.replace(f"<@{bot.user.id}>", "").strip()

    if not text:
        return

    global current_task
    log.info(f"[{message.author.name}] {text[:80]}")
    thinking_msg = await message.reply("\u23f3 Thinking...")
    current_task = asyncio.create_task(process_query(message.channel, thinking_msg, text))


async def process_query(channel, thinking_msg: discord.Message, prompt: str):
    tool_batch = []
    last_tool_flush = 0.0
    TOOL_FLUSH_INTERVAL = 3.0
    last_sent_text = ""

    async def flush_tools():
        nonlocal tool_batch, last_tool_flush
        if tool_batch:
            await channel.send("\n".join(tool_batch))
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
                for part in split_message(event.data, 1900):
                    await channel.send(part)

            elif event.type == "result":
                await flush_tools()
                try:
                    await thinking_msg.delete()
                except Exception:
                    pass
                if event.data and event.data.strip() != last_sent_text.strip():
                    n = session.store_response(event.data)
                    labeled = session.get_response(n)
                    for part in labeled:
                        await channel.send(part)
                else:
                    await channel.send("\u2705 Done")

            elif event.type == "error":
                await channel.send(f"\u274c Error: {event.data}")

            elif event.type == "stopped":
                await channel.send("\U0001f6d1 Stopped.")

    except asyncio.CancelledError:
        await channel.send("\U0001f6d1 Stopped.")
    except Exception as e:
        log.error(f"Error: {e}", exc_info=True)
        await channel.send(f"\u274c Error: {e}")


def main():
    global config, session

    parser = argparse.ArgumentParser(description="Claude Bridge \u2014 Discord")
    parser.add_argument("--config", default=str(CONFIG_PATH))
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        log.error(f"Config not found: {config_path}")
        sys.exit(1)

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    if not config.get("discord_token"):
        log.error("discord_token not set!")
        sys.exit(1)

    bridge_config = BridgeConfig.from_dict(config)
    state_path = Path(__file__).parent / "discord_state.json"
    session = ClaudeSession(bridge_config, state_path)

    bot.run(config["discord_token"], log_handler=None)


if __name__ == '__main__':
    main()

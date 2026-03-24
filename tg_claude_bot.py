"""
Telegram <-> Claude Bridge Bot (subprocess + aiogram).

Features:
- Persistent Stop button in Telegram
- Real-time progress (tools, thinking)
- Session resume (lives forever)
- bypassPermissions — no prompts
- Config from JSON

Usage:
  py D:/Life/tg_claude_bot.py
  py D:/Life/tg_claude_bot.py --config path/to/config.json
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
from aiogram.enums import ParseMode, ChatAction
from aiogram.client.default import DefaultBotProperties




# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bot")

# --- Config ---

DEFAULT_CONFIG = {
    "bot_token": "",
    "allowed_users": [],
    "claude_path": "claude",
    "work_dir": ".",
    "model": "claude-opus-4-6",
    "permission_mode": "bypassPermissions",
    "effort": "high",
    "max_turns": None,
    "history_size": 20,
    "progress_interval": 10,
}

CONFIG_PATH = Path(__file__).parent / "tg_bot_v2_config.json"
STATE_PATH = Path(__file__).parent / "tg_bot_v2_state.json"
CHAT_LOG = Path(__file__).parent / "chat_history.jsonl"
STOP_SIGNAL = Path(__file__).parent / "tg_bot_stop_signal"

config = {}
state = {"session_id": None, "msg_counter": 0, "history": {}}

# --- State ---

is_busy = False
busy_start: datetime | None = None
current_task: asyncio.Task | None = None
progress_msg_id: int | None = None
bot: Bot | None = None


def load_state():
    if STATE_PATH.exists():
        try:
            with open(STATE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"session_id": None, "msg_counter": 0, "history": {}}


def save_state():
    tmp = STATE_PATH.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(STATE_PATH)


def chat_log(event_type, data, source="telegram"):
    entry = {
        "ts": datetime.now().isoformat(),
        "source": source,
        "type": event_type,
        "data": data,
    }
    try:
        with open(CHAT_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


# --- Keyboards ---

def kb_idle():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Новый чат"), KeyboardButton(text="📊 Статус")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def kb_working():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛑 Стоп"), KeyboardButton(text="📊 Статус")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


# --- Helpers ---

def split_message(text, max_len=4000):
    if len(text) <= max_len:
        return [text]
    parts = []
    while text:
        if len(text) <= max_len:
            parts.append(text)
            break
        split_at = text.rfind('\n', 0, max_len)
        if split_at == -1:
            split_at = max_len
        parts.append(text[:split_at])
        text = text[split_at:].lstrip('\n')
    return parts


def describe_tool(name: str, inp: dict) -> str:
    shortcuts = {
        "Read": lambda: f"📖 {Path(inp.get('file_path', '?')).name}",
        "Edit": lambda: f"✏️ {Path(inp.get('file_path', '?')).name}",
        "Write": lambda: f"📝 {Path(inp.get('file_path', '?')).name}",
        "Bash": lambda: f"💻 {(inp.get('command') or inp.get('description') or '?')[:50]}",
        "Glob": lambda: f"🔍 {inp.get('pattern', '?')}",
        "Grep": lambda: f"🔎 {inp.get('pattern', '?')[:35]}",
        "WebSearch": lambda: f"🌐 {inp.get('query', '?')[:35]}",
        "WebFetch": lambda: f"📥 {inp.get('url', '?')[:40]}",
        "Agent": lambda: f"🤖 {inp.get('description', '?')[:35]}",
    }
    fn = shortcuts.get(name)
    return fn() if fn else f"🔧 {name}"


async def send_response(chat_id: int, response_text: str):
    state["msg_counter"] = state.get("msg_counter", 0) + 1
    n = state["msg_counter"]

    raw_parts = split_message(response_text)
    total = len(raw_parts)

    if total == 1:
        labeled = [f"[{n}] {raw_parts[0]}"]
    else:
        labeled = [f"[{n}.{i+1}/{total}] {p}" for i, p in enumerate(raw_parts)]

    history = state.setdefault("history", {})
    history[str(n)] = labeled
    hs = config.get("history_size", 20)
    if len(history) > hs:
        oldest = sorted(history.keys(), key=lambda x: int(x))
        for k in oldest[:len(history) - hs]:
            del history[k]

    save_state()

    for part in labeled:
        await bot.send_message(chat_id, part, reply_markup=kb_idle())

    log.info(f"Response [{n}] sent ({len(response_text)} chars, {total} parts)")


# --- Claude interaction ---

async def process_query(chat_id: int, prompt: str):
    global is_busy, busy_start, current_proc, progress_msg_id

    is_busy = True
    busy_start = datetime.now()
    final_text = ""
    new_session = state.get("session_id")
    tool_batch = []
    last_tool_flush = 0.0
    last_sent_text = ""
    TOOL_FLUSH_INTERVAL = 3.0

    cmd = [
        config["claude_path"],
        "-p",
        "--output-format", "stream-json",
        "--verbose",
        "--model", config.get("model", "claude-opus-4-6"),
        "--permission-mode", config.get("permission_mode", "bypassPermissions"),
        "--effort", config.get("effort", "high"),
    ]
    if new_session:
        cmd.extend(["--resume", new_session])

    max_turns = config.get("max_turns")
    if max_turns:
        cmd.extend(["--max-turns", str(max_turns)])

    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    work_dir = Path(config.get("work_dir", "."))
    work_dir.mkdir(parents=True, exist_ok=True)

    async def flush_tools():
        nonlocal tool_batch, last_tool_flush
        if tool_batch:
            text = "\n".join(tool_batch)
            await bot.send_message(chat_id, text, reply_markup=kb_working())
            tool_batch = []
            last_tool_flush = asyncio.get_event_loop().time()

    try:
        kwargs = dict(
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(work_dir),
            env=env,
        )
        if sys.platform == "win32":
            import subprocess as _sp
            kwargs["creationflags"] = _sp.CREATE_NO_WINDOW
        proc = await asyncio.create_subprocess_exec(*cmd, **kwargs)
        current_proc = proc
        log.info(f"  claude started (PID {proc.pid}), session={new_session or 'new'}")

        proc.stdin.write(prompt.encode('utf-8'))
        await proc.stdin.drain()
        proc.stdin.close()

        typing_task = asyncio.create_task(_keep_typing(chat_id))

        try:
            async for raw_line in proc.stdout:
                if STOP_SIGNAL.exists():
                    STOP_SIGNAL.unlink(missing_ok=True)
                    proc.kill()
                    chat_log("stopped", {"by": "gui"})
                    await bot.send_message(chat_id, "🛑 Остановлено (из GUI)", reply_markup=kb_idle())
                    break

                line = raw_line.decode('utf-8', errors='replace').strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type", "")
                now = asyncio.get_event_loop().time()

                if etype == "result":
                    new_session = event.get("session_id", new_session)
                    final_text = event.get("result", "")
                    duration = event.get("duration_ms", 0)
                    log.info(f"  done: time={duration/1000:.1f}s")

                elif etype == "assistant":
                    msg = event.get("message", {})
                    if not isinstance(msg, dict):
                        continue
                    for block in msg.get("content", []):
                        btype = block.get("type")
                        if btype == "tool_use":
                            desc = describe_tool(block.get("name", "?"), block.get("input", {}))
                            log.info(f"  tool: {desc}")
                            chat_log("tool", {"desc": desc})
                            tool_batch.append(desc)
                            if (now - last_tool_flush) > TOOL_FLUSH_INTERVAL:
                                await flush_tools()

                        elif btype == "text" and block.get("text", "").strip():
                            txt = block["text"].strip()
                            if len(txt) > 5:
                                await flush_tools()
                                last_sent_text = txt
                                chat_log("text", {"text": txt})
                                for part in split_message(txt, 3500):
                                    await bot.send_message(chat_id, part, reply_markup=kb_working())

        finally:
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

        await proc.wait()
        current_proc = None

        stderr_data = await proc.stderr.read()
        if stderr_data:
            stderr_text = stderr_data.decode('utf-8', errors='replace').strip()
            for sline in stderr_text.split('\n')[:5]:
                log.warning(f"  stderr: {sline[:200]}")

        await flush_tools()

        if new_session:
            state["session_id"] = new_session
            save_state()

        if final_text and final_text.strip() != last_sent_text.strip():
            chat_log("result", {"text": final_text})
            await send_response(chat_id, final_text + "\n\nКОНЕЦ")
        else:
            chat_log("end", {})
            await bot.send_message(chat_id, "КОНЕЦ", reply_markup=kb_idle())

    except asyncio.CancelledError:
        log.info("  cancelled by user")
        if current_proc:
            try:
                current_proc.kill()
            except Exception:
                pass
            current_proc = None
        if progress_msg_id:
            try:
                await bot.delete_message(chat_id, progress_msg_id)
            except Exception:
                pass
        await bot.send_message(chat_id, "🛑 Остановлено.", reply_markup=kb_idle())

    except Exception as e:
        log.error(f"  error: {e}", exc_info=True)
        if progress_msg_id:
            try:
                await bot.delete_message(chat_id, progress_msg_id)
            except Exception:
                pass
        await bot.send_message(chat_id, f"❌ Ошибка: {e}", reply_markup=kb_idle())

    finally:
        is_busy = False
        busy_start = None
        current_proc = None


async def _keep_typing(chat_id: int):
    try:
        while True:
            await bot.send_chat_action(chat_id, ChatAction.TYPING)
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass



# --- Handlers ---

dp = Dispatcher()


@dp.message(F.text == "🛑 Стоп")
@dp.message(F.text.lower().in_({"стоп", "stop", "отмена", "/cancel", "/stop"}))
async def handle_stop(message: types.Message):
    global current_task, current_proc
    if is_busy and current_task:
        if current_proc:
            try:
                current_proc.kill()
            except Exception:
                pass
        current_task.cancel()
        await message.answer("🛑 Останавливаю...", reply_markup=kb_idle())
    else:
        await message.answer("Нечего останавливать.", reply_markup=kb_idle())


@dp.message(F.text.in_({"📊 Статус", "/status"}))
async def handle_status(message: types.Message):
    sid = state.get("session_id", "нет")
    cnt = state.get("msg_counter", 0)
    now = datetime.now().strftime("%H:%M:%S")
    busy_str = "нет"
    if is_busy and busy_start:
        elapsed = int((datetime.now() - busy_start).total_seconds())
        busy_str = f"да ({elapsed}с)"

    sid_short = (sid[:16] + "...") if sid and len(sid) > 16 else (sid or "нет")
    status = (
        f"📊 Статус ({now})\n"
        f"Сессия: {sid_short}\n"
        f"Модель: {config.get('model', '?')}\n"
        f"Режим: {config.get('permission_mode', '?')}\n"
        f"Занят: {busy_str}\n"
        f"Сообщений: {cnt}\n"
        f"CWD: {config.get('work_dir', '?')}"
    )
    kb = kb_working() if is_busy else kb_idle()
    await message.answer(status, reply_markup=kb)


@dp.message(F.text.in_({"🔄 Новый чат", "/new"}))
async def handle_new(message: types.Message):
    state["session_id"] = None
    save_state()
    await message.answer("🔄 Сессия сброшена. Следующее сообщение начнёт новый чат.", reply_markup=kb_idle())


@dp.message(F.text == "/start")
async def handle_start(message: types.Message):
    info = (
        "🤖 Claude Bridge Bot\n\n"
        f"Модель: {config.get('model', '?')}\n"
        f"Режим: {config.get('permission_mode', '?')}\n"
        f"CWD: {config.get('work_dir', '?')}\n\n"
        "Просто отправь сообщение — Claude ответит.\n\n"
        "🛑 Стоп — остановить\n"
        "🔄 Новый чат — сбросить сессию\n"
        "📊 Статус — информация\n"
        "/resend N — повторить ответ N"
    )
    await message.answer(info, reply_markup=kb_idle())


@dp.message(F.text.startswith("/resend"))
async def handle_resend(message: types.Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Формат: /resend N")
        return
    n_str = parts[1]
    history = state.get("history", {})
    saved = history.get(n_str)
    if not saved:
        available = sorted(history.keys(), key=lambda x: int(x))
        avail_str = ", ".join(available) if available else "пусто"
        await message.answer(f"Ответ [{n_str}] не найден. Доступные: {avail_str}")
        return
    for part in saved:
        await message.answer(part)


@dp.message(F.text.startswith("/"))
async def handle_unknown_cmd(message: types.Message):
    await message.answer("Команды: /start /new /status /resend N /stop")


@dp.message()
async def handle_text(message: types.Message):
    global current_task

    allowed = config.get("allowed_users", [])
    if allowed and message.from_user.id not in allowed:
        await message.answer("⛔ Доступ запрещён.")
        return

    if is_busy:
        await message.answer("⏳ Жди ответа или нажми 🛑 Стоп", reply_markup=kb_working())
        return

    text = message.text or message.caption or ""
    if not text.strip():
        return

    log.info(f"[{message.from_user.first_name}] {text[:80]}")
    chat_log("user_message", {"text": text.strip(), "user": message.from_user.first_name})

    await message.answer("⏳ Думаю...", reply_markup=kb_working())
    current_task = asyncio.create_task(process_query(message.chat.id, text.strip()))


# --- Main ---

async def main():
    global bot, config, state

    parser = argparse.ArgumentParser(description="Claude Bridge Telegram Bot")
    parser.add_argument("--config", default=str(CONFIG_PATH))
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        log.error(f"Config not found: {config_path}")
        log.error("Run: py tg_bot_setup.py")
        sys.exit(1)

    with open(config_path, 'r', encoding='utf-8') as f:
        loaded = json.load(f)
    config.update(DEFAULT_CONFIG)
    config.update(loaded)

    if not config.get("bot_token"):
        log.error("bot_token not set!")
        sys.exit(1)

    state.update(load_state())

    work_dir = Path(config["work_dir"])
    work_dir.mkdir(parents=True, exist_ok=True)

    bot = Bot(
        token=config["bot_token"],
        default=DefaultBotProperties(parse_mode=None),
    )

    me = await bot.get_me()
    log.info(f"Bot: @{me.username} (ID: {me.id})")
    log.info(f"Model: {config['model']}")
    log.info(f"Permissions: {config['permission_mode']}")
    log.info(f"Session: {state.get('session_id') or 'new'}")
    log.info(f"CWD: {config['work_dir']}")
    log.info(f"Allowed: {config.get('allowed_users', [])}")
    log.info("Listening...")

    asyncio.create_task(monitor_gui_chat())
    await dp.start_polling(bot, skip_updates=True)


async def monitor_gui_chat():
    chat_id = config.get("allowed_users", [None])[0]
    if not chat_id:
        return

    if CHAT_LOG.exists():
        pos = CHAT_LOG.stat().st_size
    else:
        pos = 0

    while True:
        await asyncio.sleep(1)
        try:
            if not CHAT_LOG.exists():
                continue
            size = CHAT_LOG.stat().st_size
            if size <= pos:
                continue
            with open(CHAT_LOG, 'r', encoding='utf-8') as f:
                f.seek(pos)
                new_data = f.read()
                pos = f.tell()

            for line in new_data.strip().split("\n"):
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("source") != "gui":
                    continue

                etype = entry.get("type", "")
                data = entry.get("data", {})

                if etype == "user_message":
                    text = data.get("text", "")
                    await bot.send_message(chat_id, f"💻 GUI: {text}", reply_markup=kb_idle())
                elif etype == "tool":
                    await bot.send_message(chat_id, data.get("desc", "?"), reply_markup=kb_working())
                elif etype == "text":
                    txt = data.get("text", "")
                    if len(txt) > 5:
                        for part in split_message(txt, 3500):
                            await bot.send_message(chat_id, part, reply_markup=kb_working())
                elif etype == "result":
                    txt = data.get("text", "")
                    if txt:
                        for part in split_message(txt, 3500):
                            await bot.send_message(chat_id, part, reply_markup=kb_idle())
                elif etype == "end":
                    await bot.send_message(chat_id, "КОНЕЦ", reply_markup=kb_idle())

        except Exception as e:
            log.warning(f"GUI monitor error: {e}")


if __name__ == '__main__':
    asyncio.run(main())

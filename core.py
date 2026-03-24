"""
Claude Bridge — Core session manager.

Manages Claude Code CLI subprocess: spawn, stream events, stop, resume.
Used by all adapters (Telegram, Discord, Web).
"""

import asyncio
import json
import sys
import os
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Optional

log = logging.getLogger("claude-bridge.core")


@dataclass
class ClaudeEvent:
    type: str  # "tool", "text", "result", "error", "started", "stopped"
    data: str = ""
    tool_name: str = ""
    session_id: str = ""
    duration_ms: int = 0


@dataclass
class SessionState:
    session_id: Optional[str] = None
    msg_counter: int = 0
    history: dict = field(default_factory=dict)


@dataclass
class BridgeConfig:
    claude_path: str = "claude"
    work_dir: str = "."
    model: str = "claude-sonnet-4-20250514"
    permission_mode: str = "bypassPermissions"
    effort: str = "high"
    max_turns: Optional[int] = None
    history_size: int = 20

    @classmethod
    def from_dict(cls, d: dict) -> "BridgeConfig":
        fields = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in fields})


def describe_tool(name: str, inp: dict) -> str:
    shortcuts = {
        "Read": lambda: f"\U0001f4d6 {Path(inp.get('file_path', '?')).name}",
        "Edit": lambda: f"\u270f\ufe0f {Path(inp.get('file_path', '?')).name}",
        "Write": lambda: f"\U0001f4dd {Path(inp.get('file_path', '?')).name}",
        "Bash": lambda: f"\U0001f4bb {(inp.get('command') or inp.get('description') or '?')[:50]}",
        "Glob": lambda: f"\U0001f50d {inp.get('pattern', '?')}",
        "Grep": lambda: f"\U0001f50e {inp.get('pattern', '?')[:35]}",
        "WebSearch": lambda: f"\U0001f310 {inp.get('query', '?')[:35]}",
        "WebFetch": lambda: f"\U0001f4e5 {inp.get('url', '?')[:40]}",
        "Agent": lambda: f"\U0001f916 {inp.get('description', '?')[:35]}",
    }
    fn = shortcuts.get(name)
    return fn() if fn else f"\U0001f527 {name}"


def split_message(text: str, max_len: int = 4000) -> list[str]:
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


class ClaudeSession:
    """Manages a single Claude Code CLI session."""

    def __init__(self, config: BridgeConfig, state_path: Optional[Path] = None):
        self.config = config
        self.state_path = state_path or Path("state.json")
        self.state = SessionState()
        self.is_busy = False
        self.busy_start: Optional[datetime] = None
        self.proc: Optional[asyncio.subprocess.Process] = None
        self._load_state()

    def _load_state(self):
        if self.state_path.exists():
            try:
                with open(self.state_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.state.session_id = data.get("session_id")
                self.state.msg_counter = data.get("msg_counter", 0)
                self.state.history = data.get("history", {})
            except Exception:
                pass

    def _save_state(self):
        tmp = self.state_path.with_suffix('.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({
                "session_id": self.state.session_id,
                "msg_counter": self.state.msg_counter,
                "history": self.state.history,
            }, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(self.state_path)

    def reset_session(self):
        self.state.session_id = None
        self._save_state()

    def store_response(self, text: str) -> int:
        self.state.msg_counter += 1
        n = self.state.msg_counter
        parts = split_message(text)
        total = len(parts)
        if total == 1:
            labeled = [f"[{n}] {parts[0]}"]
        else:
            labeled = [f"[{n}.{i+1}/{total}] {p}" for i, p in enumerate(parts)]
        self.state.history[str(n)] = labeled
        hs = self.config.history_size
        if len(self.state.history) > hs:
            oldest = sorted(self.state.history.keys(), key=lambda x: int(x))
            for k in oldest[:len(self.state.history) - hs]:
                del self.state.history[k]
        self._save_state()
        return n

    def get_response(self, n: int) -> Optional[list[str]]:
        return self.state.history.get(str(n))

    def get_status(self) -> dict:
        busy_str = "no"
        if self.is_busy and self.busy_start:
            elapsed = int((datetime.now() - self.busy_start).total_seconds())
            busy_str = f"yes ({elapsed}s)"
        sid = self.state.session_id
        sid_short = (sid[:16] + "...") if sid and len(sid) > 16 else (sid or "none")
        return {
            "session": sid_short,
            "model": self.config.model,
            "permission_mode": self.config.permission_mode,
            "busy": busy_str,
            "messages": self.state.msg_counter,
            "work_dir": self.config.work_dir,
        }

    async def stop(self):
        if self.proc:
            try:
                self.proc.kill()
            except Exception:
                pass

    async def query(self, prompt: str) -> AsyncIterator[ClaudeEvent]:
        if self.is_busy:
            yield ClaudeEvent(type="error", data="Session is busy")
            return

        self.is_busy = True
        self.busy_start = datetime.now()

        cmd = [
            self.config.claude_path,
            "-p",
            "--output-format", "stream-json",
            "--verbose",
            "--model", self.config.model,
            "--permission-mode", self.config.permission_mode,
            "--effort", self.config.effort,
        ]
        if self.state.session_id:
            cmd.extend(["--resume", self.state.session_id])
        if self.config.max_turns:
            cmd.extend(["--max-turns", str(self.config.max_turns)])

        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        work_dir = Path(self.config.work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)

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

            self.proc = await asyncio.create_subprocess_exec(*cmd, **kwargs)
            yield ClaudeEvent(type="started", data=f"PID {self.proc.pid}")

            self.proc.stdin.write(prompt.encode('utf-8'))
            await self.proc.stdin.drain()
            self.proc.stdin.close()

            final_text = ""
            last_sent_text = ""

            async for raw_line in self.proc.stdout:
                line = raw_line.decode('utf-8', errors='replace').strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type", "")

                if etype == "result":
                    new_session = event.get("session_id")
                    if new_session:
                        self.state.session_id = new_session
                        self._save_state()
                    final_text = event.get("result", "")
                    duration = event.get("duration_ms", 0)
                    yield ClaudeEvent(
                        type="result",
                        data=final_text,
                        session_id=new_session or "",
                        duration_ms=duration,
                    )

                elif etype == "assistant":
                    msg = event.get("message", {})
                    if not isinstance(msg, dict):
                        continue
                    for block in msg.get("content", []):
                        btype = block.get("type")
                        if btype == "tool_use":
                            desc = describe_tool(block.get("name", "?"), block.get("input", {}))
                            yield ClaudeEvent(type="tool", data=desc, tool_name=block.get("name", ""))
                        elif btype == "text" and block.get("text", "").strip():
                            txt = block["text"].strip()
                            if len(txt) > 5:
                                last_sent_text = txt
                                yield ClaudeEvent(type="text", data=txt)

            await self.proc.wait()
            self.proc = None

        except asyncio.CancelledError:
            if self.proc:
                try:
                    self.proc.kill()
                except Exception:
                    pass
                self.proc = None
            yield ClaudeEvent(type="stopped", data="Cancelled")

        except Exception as e:
            log.error(f"Query error: {e}", exc_info=True)
            yield ClaudeEvent(type="error", data=str(e))

        finally:
            self.is_busy = False
            self.busy_start = None

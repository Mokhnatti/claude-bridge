"""
Claude Bridge — Web adapter.

FastAPI + WebSocket. Serves a chat UI and streams Claude responses in real-time.

Usage:
  python web_server.py
  python web_server.py --config path/to/config.json --port 8080
"""

import asyncio
import json
import sys
import os
import argparse
import logging
from pathlib import Path

os.environ.pop("CLAUDECODE", None)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

from core import ClaudeSession, BridgeConfig, ClaudeEvent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("bridge.web")

CONFIG_PATH = Path(__file__).parent / "config.json"

config = {}
session: ClaudeSession = None
current_task: asyncio.Task = None

app = FastAPI(title="Claude Bridge")

WEB_DIR = Path(__file__).parent / "web"


@app.get("/")
async def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/status")
async def api_status():
    return session.get_status()


@app.post("/api/new")
async def api_new():
    session.reset_session()
    return {"ok": True}


@app.post("/api/stop")
async def api_stop():
    global current_task
    if session.is_busy:
        await session.stop()
        if current_task:
            current_task.cancel()
        return {"ok": True}
    return {"ok": False, "error": "Not busy"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    global current_task

    web_token = config.get("web_token", "")
    await ws.accept()

    if web_token:
        try:
            auth = await asyncio.wait_for(ws.receive_json(), timeout=5)
            if auth.get("token") != web_token:
                await ws.send_json({"type": "error", "data": "Invalid token"})
                await ws.close()
                return
        except Exception:
            await ws.close()
            return

    await ws.send_json({"type": "connected", "data": session.get_status()})

    try:
        while True:
            msg = await ws.receive_json()
            action = msg.get("action", "")

            if action == "query":
                prompt = msg.get("text", "").strip()
                if not prompt:
                    continue
                if session.is_busy:
                    await ws.send_json({"type": "error", "data": "Session is busy"})
                    continue
                log.info(f"[web] {prompt[:80]}")
                current_task = asyncio.create_task(handle_query(ws, prompt))

            elif action == "stop":
                if session.is_busy:
                    await session.stop()
                    if current_task:
                        current_task.cancel()

            elif action == "new":
                session.reset_session()
                await ws.send_json({"type": "session_reset"})

            elif action == "status":
                await ws.send_json({"type": "status", "data": session.get_status()})

            elif action == "resend":
                n = msg.get("n", 0)
                saved = session.get_response(n)
                if saved:
                    await ws.send_json({"type": "resend", "data": saved})
                else:
                    await ws.send_json({"type": "error", "data": f"Response [{n}] not found"})

    except WebSocketDisconnect:
        log.info("[web] Client disconnected")
    except Exception as e:
        log.error(f"[web] Error: {e}")


async def handle_query(ws: WebSocket, prompt: str):
    try:
        async for event in session.query(prompt):
            await ws.send_json({
                "type": event.type,
                "data": event.data,
                "tool_name": event.tool_name,
                "session_id": event.session_id,
                "duration_ms": event.duration_ms,
            })
    except asyncio.CancelledError:
        await ws.send_json({"type": "stopped", "data": "Cancelled"})
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "data": str(e)})
        except Exception:
            pass


def main():
    global config, session

    parser = argparse.ArgumentParser(description="Claude Bridge \u2014 Web")
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8585)
    args = parser.parse_args()

    config_path = Path(args.config)
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

    bridge_config = BridgeConfig.from_dict(config)
    state_path = Path(__file__).parent / "web_state.json"
    session = ClaudeSession(bridge_config, state_path)

    log.info(f"Model: {bridge_config.model}")
    log.info(f"CWD: {bridge_config.work_dir}")
    log.info(f"Web UI: http://{args.host}:{args.port}")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == '__main__':
    main()

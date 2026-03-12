"""
server.py — FastAPI server for remote access to DesktopPet.

Run via the pet itself (started as a daemon thread from animals.py),
or standalone for development:
    uvicorn server:create_app --factory --host 0.0.0.0 --port 7865
"""

import os
import io
import json
import secrets
import asyncio
import threading
import time
import base64
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import (
    FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect,
    UploadFile, File, Query,
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, Response
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

TOKEN_FILE = Path(__file__).parent / "remote_token.json"
_bearer = HTTPBearer()


def _load_or_create_token() -> str:
    if TOKEN_FILE.exists():
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        return data.get("token", "")
    token = secrets.token_urlsafe(32)
    TOKEN_FILE.write_text(json.dumps({"token": token}, indent=2), encoding="utf-8")
    return token


_SERVER_TOKEN: str = ""


def _verify(creds: HTTPAuthorizationCredentials = Depends(_bearer)):
    if not secrets.compare_digest(creds.credentials, _SERVER_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid token")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4096)

class SayRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1024)

class CommandRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=256)

class ReminderRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=512)
    minutes: float = Field(..., gt=0, le=1440)

class CancelReminderRequest(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=256)

class HabitLogRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    count: int = Field(1, ge=1, le=1000)

class HabitAddRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    goal: int = Field(1, ge=1, le=1000)
    icon: str = Field("✅", max_length=4)

class MemoryRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2048)
    topic: str = Field("", max_length=128)

class RecallRequest(BaseModel):
    query: str = Field("", max_length=512)

class NoteRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4096)

class MoodRequest(BaseModel):
    score: int = Field(..., ge=1, le=5)
    note: str = Field("", max_length=512)

class EquipRequest(BaseModel):
    item_id: str = Field(..., min_length=1, max_length=64)

class MouseMoveRequest(BaseModel):
    x: int
    y: int

class MouseClickRequest(BaseModel):
    x: int
    y: int
    button: str = Field("left", pattern="^(left|right)$")

class MouseScrollRequest(BaseModel):
    delta: int = Field(..., ge=-5000, le=5000)

class KeyTypeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=256)

class KeyPressRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=32)
    action: str = Field("press", pattern="^(press|down|up)$")

class KeyComboRequest(BaseModel):
    keys: list[str] = Field(..., min_length=1, max_length=5)

class ClipboardRequest(BaseModel):
    text: str = Field(..., max_length=65536)

class FilePathRequest(BaseModel):
    path: str = Field("", max_length=512)

class FileDeleteRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=512)

class FileRenameRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=512)
    new_name: str = Field(..., min_length=1, max_length=255)

class FolderCreateRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=512)

class ScheduleRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=256)
    hour: int = Field(..., ge=0, le=23)
    minute: int = Field(..., ge=0, le=59)

class ScheduleDeleteRequest(BaseModel):
    id: int = Field(..., ge=1)

class VolumeRequest(BaseModel):
    level: int = Field(..., ge=0, le=100)

class MediaKeyRequest(BaseModel):
    action: str = Field(..., pattern="^(play_pause|next|prev|stop|vol_up|vol_down|vol_mute)$")

class KillProcessRequest(BaseModel):
    pid: int = Field(..., ge=1)

class PowerRequest(BaseModel):
    action: str = Field(..., pattern="^(lock|sleep|shutdown|restart|cancel_shutdown)$")

class BrightnessRequest(BaseModel):
    level: int = Field(..., ge=0, le=100)

class QuickLaunchRequest(BaseModel):
    app_id: str = Field(..., min_length=1, max_length=64)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

_bridge = None


def create_app(bridge=None) -> FastAPI:
    global _bridge, _SERVER_TOKEN
    if bridge is not None:
        _bridge = bridge
    _SERVER_TOKEN = _load_or_create_token()

    app = FastAPI(title="Toty Remote", version="2.0.0", docs_url="/docs")

    # ── ASGI middleware for real-time file transfer progress on pet ──
    from starlette.types import ASGIApp, Receive, Scope, Send

    class SharingProgressMiddleware:
        """Track real network bytes for uploads and downloads."""
        def __init__(self, inner: ASGIApp):
            self.inner = inner

        async def __call__(self, scope: Scope, receive: Receive, send: Send):
            if scope["type"] != "http" or _bridge is None:
                return await self.inner(scope, receive, send)

            path = scope.get("path", "")

            # ── Track connected devices on all /api/ requests ──
            if path.startswith("/api/"):
                ip = "unknown"
                if scope.get("client"):
                    ip = scope["client"][0]
                ua = ""
                for hdr_name, hdr_val in scope.get("headers", []):
                    if hdr_name == b"user-agent":
                        ua = hdr_val.decode(errors="replace")
                        break
                if ua:
                    _bridge.track_device(ip, ua)

            # ── Upload: track incoming bytes ──
            if path == "/api/files/upload" and scope.get("method") == "POST":
                cl = 0
                for hdr_name, hdr_val in scope.get("headers", []):
                    if hdr_name == b"content-length":
                        cl = int(hdr_val)
                        break
                if cl > 512 * 1024:  # only track > 512 KB
                    tid = f"up_{secrets.token_hex(4)}"
                    received = 0
                    _bridge.notify_sharing(tid, "📥 Receiving file…", 0, cl)

                    async def tracked_receive():
                        nonlocal received
                        msg = await receive()
                        received += len(msg.get("body", b""))
                        _bridge.notify_sharing(tid, "📥 Receiving file…", received, cl)
                        return msg

                    try:
                        return await self.inner(scope, tracked_receive, send)
                    finally:
                        _bridge.notify_sharing_done(tid, "📥 File received!")

            # ── Download: track outgoing bytes ──
            if path == "/api/files/download" and scope.get("method") == "GET":
                tid = f"dl_{secrets.token_hex(4)}"
                cl = 0
                sent = 0
                started = False

                async def tracked_send(msg):
                    nonlocal cl, sent, started
                    if msg["type"] == "http.response.start":
                        for hdr_name, hdr_val in msg.get("headers", []):
                            if hdr_name == b"content-length":
                                cl = int(hdr_val)
                                break
                        if cl > 512 * 1024:
                            started = True
                            # Extract filename from content-disposition
                            fname = "file"
                            for hn, hv in msg.get("headers", []):
                                if hn == b"content-disposition":
                                    val = hv.decode(errors="replace")
                                    if 'filename="' in val:
                                        fname = val.split('filename="')[1].rstrip('"')
                                    break
                            _bridge.notify_sharing(tid, f"📤 Sharing: {fname}", 0, cl)
                    elif msg["type"] == "http.response.body" and started:
                        sent += len(msg.get("body", b""))
                        _bridge.notify_sharing(tid, "📤 Sharing…", sent, cl)
                    await send(msg)

                try:
                    return await self.inner(scope, receive, tracked_send)
                finally:
                    if started:
                        _bridge.notify_sharing_done(tid, "📤 Shared!")

            return await self.inner(scope, receive, send)

    app.add_middleware(SharingProgressMiddleware)

    # ── Rate limiter middleware ────────────────────────
    _rate_buckets: dict[str, list[float]] = defaultdict(list)
    _RATE_LIMITS = {
        "/api/power": (3, 60),        # 3 requests per 60s
        "/api/processes/kill": (5, 60),  # 5 per 60s
        "/api/input/": (60, 1),         # 60 per second (typing)
    }
    _GLOBAL_RATE = (120, 60)  # 120 requests per 60s per IP

    class RateLimitMiddleware:
        def __init__(self, inner: ASGIApp):
            self.inner = inner

        async def __call__(self, scope: Scope, receive: Receive, send: Send):
            if scope["type"] != "http":
                return await self.inner(scope, receive, send)
            path = scope.get("path", "")
            ip = scope["client"][0] if scope.get("client") else "unknown"
            now = time.time()

            # Check endpoint-specific limits
            for prefix, (max_reqs, window) in _RATE_LIMITS.items():
                if path.startswith(prefix):
                    key = f"{ip}:{prefix}"
                    bucket = _rate_buckets[key]
                    bucket[:] = [t for t in bucket if now - t < window]
                    if len(bucket) >= max_reqs:
                        response = Response(
                            content=json.dumps({"detail": "Rate limit exceeded"}),
                            status_code=429,
                            media_type="application/json",
                        )
                        await response(scope, receive, send)
                        return
                    bucket.append(now)
                    break

            # Global per-IP limit
            gkey = f"{ip}:global"
            gbucket = _rate_buckets[gkey]
            gbucket[:] = [t for t in gbucket if now - t < _GLOBAL_RATE[1]]
            if len(gbucket) >= _GLOBAL_RATE[0]:
                response = Response(
                    content=json.dumps({"detail": "Rate limit exceeded"}),
                    status_code=429,
                    media_type="application/json",
                )
                await response(scope, receive, send)
                return
            gbucket.append(now)

            return await self.inner(scope, receive, send)

    app.add_middleware(RateLimitMiddleware)

    # ── CORS — restrict to localhost dashboard origins ──
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:7865",
            "http://127.0.0.1:7865",
            "http://localhost:3000",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Dashboard ──────────────────────────────────────
    _dashboard_html = ""
    _dashboard_path = Path(__file__).parent / "remote_dashboard.html"
    if _dashboard_path.exists():
        _dashboard_html = _dashboard_path.read_text(encoding="utf-8")

    @app.get("/", response_class=HTMLResponse)
    def dashboard():
        return _dashboard_html

    # ── PWA static files ──────────────────────────────
    _static_dir = Path(__file__).parent

    @app.get("/manifest.json")
    def pwa_manifest():
        p = _static_dir / "manifest.json"
        if p.exists():
            return Response(content=p.read_text(encoding="utf-8"),
                            media_type="application/manifest+json")
        raise HTTPException(404)

    @app.get("/sw.js")
    def service_worker():
        p = _static_dir / "sw.js"
        if p.exists():
            return Response(content=p.read_text(encoding="utf-8"),
                            media_type="application/javascript",
                            headers={"Service-Worker-Allowed": "/"})
        raise HTTPException(404)

    @app.get("/icon-{size}.png")
    def pwa_icon(size: int):
        p = _static_dir / f"icon-{size}.png"
        if p.exists():
            return Response(content=p.read_bytes(), media_type="image/png")
        raise HTTPException(404)

    # ══════════════════════════════════════════════════
    #  STATUS & STATS
    # ══════════════════════════════════════════════════

    @app.get("/api/status")
    def status(creds=Depends(_verify)):
        return _bridge.get_status()

    @app.get("/api/devices")
    def get_devices(creds=Depends(_verify)):
        return {"devices": _bridge.get_devices(), "active": _bridge.get_active_device_count()}

    @app.get("/api/stats")
    def stats(creds=Depends(_verify)):
        return _bridge.get_stats()

    # ══════════════════════════════════════════════════
    #  CHAT & SAY
    # ══════════════════════════════════════════════════

    @app.post("/api/chat")
    async def chat(req: ChatRequest, creds=Depends(_verify)):
        reply = await _bridge.chat(req.message)
        return {"reply": reply}

    @app.post("/api/say")
    def say(req: SayRequest, creds=Depends(_verify)):
        _bridge.say(req.text)
        return {"ok": True}

    # ══════════════════════════════════════════════════
    #  COMMANDS
    # ══════════════════════════════════════════════════

    @app.post("/api/command")
    def command(req: CommandRequest, creds=Depends(_verify)):
        result = _bridge.execute_command(req.command)
        return {"result": result}

    # ══════════════════════════════════════════════════
    #  REMINDERS
    # ══════════════════════════════════════════════════

    @app.get("/api/reminders")
    def list_reminders(creds=Depends(_verify)):
        return {"reminders": _bridge.list_reminders()}

    @app.post("/api/reminders")
    def add_reminder(req: ReminderRequest, creds=Depends(_verify)):
        return {"result": _bridge.add_reminder(req.text, req.minutes)}

    @app.delete("/api/reminders")
    def cancel_reminder(req: CancelReminderRequest, creds=Depends(_verify)):
        return {"result": _bridge.cancel_reminder(req.keyword)}

    # ══════════════════════════════════════════════════
    #  HABITS
    # ══════════════════════════════════════════════════

    @app.get("/api/habits")
    def list_habits(creds=Depends(_verify)):
        return _bridge.list_habits()

    @app.post("/api/habits")
    def add_habit(req: HabitAddRequest, creds=Depends(_verify)):
        return {"result": _bridge.add_habit(req.name, req.goal, req.icon)}

    @app.post("/api/habits/log")
    def log_habit(req: HabitLogRequest, creds=Depends(_verify)):
        return {"result": _bridge.log_habit(req.name, req.count)}

    # ══════════════════════════════════════════════════
    #  MEMORY
    # ══════════════════════════════════════════════════

    @app.post("/api/memory/remember")
    def remember(req: MemoryRequest, creds=Depends(_verify)):
        return {"result": _bridge.remember(req.text, req.topic)}

    @app.post("/api/memory/recall")
    def recall(req: RecallRequest, creds=Depends(_verify)):
        return {"result": _bridge.recall(req.query)}

    # ══════════════════════════════════════════════════
    #  STICKY NOTES
    # ══════════════════════════════════════════════════

    @app.get("/api/notes")
    def get_notes(creds=Depends(_verify)):
        return {"notes": _bridge.get_notes()}

    @app.post("/api/notes")
    def create_note(req: NoteRequest, creds=Depends(_verify)):
        return {"result": _bridge.create_note(req.text)}

    @app.post("/api/notes/toggle")
    def toggle_notes(creds=Depends(_verify)):
        _bridge.toggle_notes()
        return {"ok": True}

    # ══════════════════════════════════════════════════
    #  MOOD JOURNAL
    # ══════════════════════════════════════════════════

    @app.post("/api/mood")
    def log_mood(req: MoodRequest, creds=Depends(_verify)):
        return {"result": _bridge.log_mood(req.score, req.note)}

    @app.get("/api/mood")
    def get_mood(limit: int = Query(14, ge=1, le=365), creds=Depends(_verify)):
        return {
            "history": _bridge.get_mood_history(limit),
            "week": _bridge.get_mood_week(),
        }

    # ══════════════════════════════════════════════════
    #  WARDROBE
    # ══════════════════════════════════════════════════

    @app.get("/api/wardrobe")
    def get_wardrobe(creds=Depends(_verify)):
        return _bridge.get_wardrobe()

    @app.post("/api/wardrobe/equip")
    def equip(req: EquipRequest, creds=Depends(_verify)):
        return {"result": _bridge.equip_item(req.item_id)}

    @app.post("/api/wardrobe/unequip")
    def unequip(creds=Depends(_verify)):
        return {"result": _bridge.unequip_item()}

    # ══════════════════════════════════════════════════
    #  SCREENSHOT
    # ══════════════════════════════════════════════════

    @app.get("/api/screenshot")
    def screenshot(creds=Depends(_verify)):
        path = _bridge.take_screenshot()
        if path and Path(path).exists():
            data = Path(path).read_bytes()
            return Response(content=data, media_type="image/png")
        raise HTTPException(404, "Screenshot failed")

    # ══════════════════════════════════════════════════
    #  MONITORS
    # ══════════════════════════════════════════════════

    @app.get("/api/monitors")
    def list_monitors(creds=Depends(_verify)):
        return {"monitors": _bridge.list_monitors()}

    # ══════════════════════════════════════════════════
    #  SCREEN SHARING (WebSocket — WebP/JPEG frames)
    # ══════════════════════════════════════════════════

    _screen_sessions = {}  # ws_id → {last_activity, started}

    @app.websocket("/ws/screen")
    async def ws_screen(ws: WebSocket):
        await ws.accept()
        try:
            auth_msg = await ws.receive_text()
            if not secrets.compare_digest(auth_msg, _SERVER_TOKEN):
                await ws.close(code=4001, reason="Unauthorized")
                return
        except WebSocketDisconnect:
            return

        quality = 35
        scale = 0.5
        fps = 3
        monitor = -1
        cursor = True
        use_webp = True
        ws_id = id(ws)
        _screen_sessions[ws_id] = {"started": time.time(), "last_activity": time.time()}
        SESSION_TIMEOUT = 30 * 60  # 30 minutes inactivity timeout

        try:
            while True:
                # Session timeout check
                session = _screen_sessions.get(ws_id)
                if session and (time.time() - session["last_activity"]) > SESSION_TIMEOUT:
                    await ws.send_text(json.dumps({"type": "timeout"}))
                    break

                # Check for control messages (non-blocking)
                try:
                    msg = await asyncio.wait_for(ws.receive_text(), timeout=0.01)
                    data = json.loads(msg)
                    _screen_sessions[ws_id]["last_activity"] = time.time()
                    dtype = data.get("type")
                    if dtype == "settings":
                        quality = max(10, min(90, data.get("quality", quality)))
                        scale = max(0.2, min(1.0, data.get("scale", scale)))
                        fps = max(1, min(15, data.get("fps", fps)))
                        monitor = data.get("monitor", monitor)
                        cursor = data.get("cursor", cursor)
                        use_webp = data.get("webp", use_webp)
                    elif dtype == "mouse_move":
                        _bridge.mouse_move(int(data["x"] / scale), int(data["y"] / scale))
                    elif dtype == "mouse_click":
                        _bridge.mouse_click(
                            int(data["x"] / scale), int(data["y"] / scale),
                            data.get("button", "left")
                        )
                    elif dtype == "mouse_down":
                        _bridge.mouse_down(
                            int(data["x"] / scale), int(data["y"] / scale),
                            data.get("button", "left")
                        )
                    elif dtype == "mouse_up":
                        _bridge.mouse_up(
                            int(data["x"] / scale), int(data["y"] / scale),
                            data.get("button", "left")
                        )
                    elif dtype == "mouse_scroll":
                        _bridge.mouse_scroll(data.get("delta", 0))
                    elif dtype == "key_type":
                        _bridge.keyboard_type(data.get("text", ""))
                    elif dtype == "key_press":
                        _bridge.keyboard_key(data.get("key", ""), data.get("action", "press"))
                    elif dtype == "key_combo":
                        _bridge.keyboard_combo(data.get("keys", []))
                    elif dtype == "ping":
                        await ws.send_text(json.dumps({"type": "pong", "ts": data.get("ts", 0)}))
                        continue
                except asyncio.TimeoutError:
                    pass

                frame = await asyncio.get_event_loop().run_in_executor(
                    None, _bridge.capture_screen_frame, quality, scale,
                    monitor, cursor, use_webp
                )
                if frame:
                    await ws.send_bytes(frame)
                await asyncio.sleep(1.0 / fps)
        except (WebSocketDisconnect, Exception):
            pass
        finally:
            _screen_sessions.pop(ws_id, None)

    # ══════════════════════════════════════════════════
    #  REMOTE INPUT (REST fallback)
    #  Requires remote_input_enabled setting
    # ══════════════════════════════════════════════════

    def _check_remote_input(creds=Depends(_verify)):
        if _bridge and not getattr(_bridge, 'remote_input_enabled', True):
            raise HTTPException(403, "Remote input is disabled in settings")

    @app.post("/api/input/mouse/move")
    def mouse_move(req: MouseMoveRequest, creds=Depends(_verify), _=Depends(_check_remote_input)):
        _bridge.mouse_move(req.x, req.y)
        return {"ok": True}

    @app.post("/api/input/mouse/click")
    def mouse_click(req: MouseClickRequest, creds=Depends(_verify), _=Depends(_check_remote_input)):
        _bridge.mouse_click(req.x, req.y, req.button)
        return {"ok": True}

    @app.post("/api/input/mouse/scroll")
    def mouse_scroll(req: MouseScrollRequest, creds=Depends(_verify), _=Depends(_check_remote_input)):
        _bridge.mouse_scroll(req.delta)
        return {"ok": True}

    @app.post("/api/input/keyboard/type")
    def keyboard_type(req: KeyTypeRequest, creds=Depends(_verify), _=Depends(_check_remote_input)):
        _bridge.keyboard_type(req.text)
        return {"ok": True}

    @app.post("/api/input/keyboard/key")
    def keyboard_key(req: KeyPressRequest, creds=Depends(_verify), _=Depends(_check_remote_input)):
        _bridge.keyboard_key(req.key, req.action)
        return {"ok": True}

    @app.post("/api/input/keyboard/combo")
    def keyboard_combo(req: KeyComboRequest, creds=Depends(_verify), _=Depends(_check_remote_input)):
        _bridge.keyboard_combo(req.keys)
        return {"ok": True}

    # ══════════════════════════════════════════════════
    #  CLIPBOARD
    # ══════════════════════════════════════════════════

    @app.get("/api/clipboard")
    def get_clipboard(creds=Depends(_verify)):
        return {"text": _bridge.get_clipboard()}

    @app.post("/api/clipboard")
    def set_clipboard(req: ClipboardRequest, creds=Depends(_verify)):
        _bridge.set_clipboard(req.text)
        return {"ok": True}

    # ══════════════════════════════════════════════════
    #  SYSTEM HEALTH
    # ══════════════════════════════════════════════════

    @app.get("/api/system")
    def system_health(creds=Depends(_verify)):
        return _bridge.get_system_health()

    # ══════════════════════════════════════════════════
    #  APP TIME & HEATMAP
    # ══════════════════════════════════════════════════

    @app.get("/api/app-time")
    def app_time(creds=Depends(_verify)):
        return _bridge.get_app_time()

    @app.get("/api/heatmap")
    def heatmap(creds=Depends(_verify)):
        return _bridge.get_keyboard_heatmap()

    # ══════════════════════════════════════════════════
    #  BACKUP
    # ══════════════════════════════════════════════════

    @app.post("/api/backup")
    def create_backup(creds=Depends(_verify)):
        path = _bridge.create_backup()
        if path:
            return {"path": path}
        raise HTTPException(500, "Backup failed")

    @app.get("/api/backups")
    def list_backups(creds=Depends(_verify)):
        return {"backups": _bridge.list_backups()}

    # ══════════════════════════════════════════════════
    #  FILE BROWSER & TRANSFER
    # ══════════════════════════════════════════════════

    # ── Sensitive file blocklist ──
    _BLOCKED_PATTERNS = {
        '.ssh', '.env', '.pem', '.key', '.pfx', '.p12',
        'id_rsa', 'id_ed25519', 'known_hosts', 'authorized_keys',
        'remote_token.json', '.git/config', 'credentials',
    }

    def _is_blocked_path(path_str: str) -> bool:
        parts = Path(path_str).parts
        name = Path(path_str).name
        for blocked in _BLOCKED_PATTERNS:
            if blocked in parts or name == blocked or name.endswith(blocked):
                return True
        return False

    @app.get("/api/files")
    def list_files(path: str = Query("", max_length=512), creds=Depends(_verify)):
        return {"files": _bridge.list_files(path)}

    @app.get("/api/files/info")
    def file_info(path: str = Query(..., min_length=1, max_length=512), creds=Depends(_verify)):
        if _is_blocked_path(path):
            raise HTTPException(403, "Access to this file is restricted")
        return _bridge.get_file_info(path)

    @app.get("/api/files/download")
    def download_file(path: str = Query(..., min_length=1, max_length=512), creds=Depends(_verify)):
        if _is_blocked_path(path):
            raise HTTPException(403, "Access to this file is restricted")
        fpath = _bridge.get_file_path(path)
        if fpath is None:
            raise HTTPException(404, "File not found or access denied")
        file_size = fpath.stat().st_size
        name = fpath.name
        suffix = fpath.suffix.lower()
        mime_map = {
            '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.gif': 'image/gif', '.webp': 'image/webp', '.svg': 'image/svg+xml',
            '.txt': 'text/plain', '.py': 'text/plain', '.js': 'text/plain',
            '.html': 'text/html', '.css': 'text/css', '.json': 'application/json',
            '.md': 'text/plain', '.csv': 'text/plain', '.log': 'text/plain',
            '.pdf': 'application/pdf', '.mp3': 'audio/mpeg', '.mp4': 'video/mp4',
            '.wav': 'audio/wav', '.ogg': 'audio/ogg', '.webm': 'video/webm',
            '.mov': 'video/quicktime', '.mkv': 'video/x-matroska',
        }
        media_type = mime_map.get(suffix, 'application/octet-stream')

        # Stream file in 1 MB chunks (progress tracked by ASGI middleware)
        CHUNK = 1024 * 1024

        def _stream():
            with open(fpath, "rb") as f:
                while True:
                    chunk = f.read(CHUNK)
                    if not chunk:
                        break
                    yield chunk

        return StreamingResponse(
            _stream(),
            media_type=media_type,
            headers={
                "Content-Disposition": f'inline; filename="{name}"',
                "Content-Length": str(file_size),
            },
        )

    @app.post("/api/files/upload")
    async def upload_file(
        files: list[UploadFile] = File(...),
        dest: str = Query("uploads", max_length=512),
        creds=Depends(_verify),
    ):
        base = Path(".").resolve()
        target_dir = (base / dest).resolve()
        if not str(target_dir).startswith(str(base)):
            raise HTTPException(403, "Path traversal denied")
        target_dir.mkdir(parents=True, exist_ok=True)
        MAX_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB per file
        CHUNK = 1024 * 1024  # 1 MB read chunks
        results = []

        for file in files:
            target = target_dir / file.filename
            if not str(target.resolve()).startswith(str(base)):
                results.append({"name": file.filename, "error": "Path traversal"})
                continue
            # Stream to disk in chunks
            written = 0
            try:
                with open(target, "wb") as out:
                    while True:
                        chunk = await file.read(CHUNK)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > MAX_SIZE:
                            break
                        out.write(chunk)
            except Exception as exc:
                results.append({"name": file.filename, "error": str(exc)})
                target.unlink(missing_ok=True)
                continue
            if written > MAX_SIZE:
                results.append({"name": file.filename, "error": "Too large (2GB max)"})
                target.unlink(missing_ok=True)
                continue
            results.append({"name": file.filename, "path": str(target.relative_to(base)), "size": written})

        return {"files": results}

    @app.post("/api/files/delete")
    def delete_file(req: FileDeleteRequest, creds=Depends(_verify)):
        return _bridge.delete_file(req.path)

    @app.post("/api/files/rename")
    def rename_file(req: FileRenameRequest, creds=Depends(_verify)):
        return _bridge.rename_file(req.path, req.new_name)

    @app.post("/api/files/mkdir")
    def create_folder(req: FolderCreateRequest, creds=Depends(_verify)):
        return _bridge.create_folder(req.path)

    # ══════════════════════════════════════════════════
    #  VOLUME CONTROL
    # ══════════════════════════════════════════════════

    @app.get("/api/volume")
    def get_volume(creds=Depends(_verify)):
        return _bridge.get_volume()

    @app.post("/api/volume")
    def set_volume(req: VolumeRequest, creds=Depends(_verify)):
        return _bridge.set_volume(req.level)

    @app.post("/api/volume/mute")
    def toggle_mute(creds=Depends(_verify)):
        return _bridge.toggle_mute()

    # ══════════════════════════════════════════════════
    #  MEDIA CONTROL
    # ══════════════════════════════════════════════════

    @app.post("/api/media")
    def media_key(req: MediaKeyRequest, creds=Depends(_verify)):
        return _bridge.media_key(req.action)

    # ══════════════════════════════════════════════════
    #  RUNNING PROCESSES
    # ══════════════════════════════════════════════════

    @app.get("/api/processes")
    def list_processes(
        sort: str = Query("cpu", pattern="^(cpu|mem)$"),
        limit: int = Query(30, ge=5, le=100),
        creds=Depends(_verify),
    ):
        return {"processes": _bridge.list_processes(sort_by=sort, limit=limit)}

    @app.post("/api/processes/kill")
    def kill_process(req: KillProcessRequest, creds=Depends(_verify)):
        return _bridge.kill_process(req.pid)

    # ══════════════════════════════════════════════════
    #  POWER MANAGEMENT
    # ══════════════════════════════════════════════════

    @app.post("/api/power")
    def power_action(req: PowerRequest, creds=Depends(_verify)):
        return _bridge.power_action(req.action)

    # ══════════════════════════════════════════════════
    #  NETWORK INFO
    # ══════════════════════════════════════════════════

    @app.get("/api/network")
    def get_network(creds=Depends(_verify)):
        return _bridge.get_network_info()

    # ══════════════════════════════════════════════════
    #  QUICK LAUNCH
    # ══════════════════════════════════════════════════

    @app.post("/api/launch")
    def quick_launch(req: QuickLaunchRequest, creds=Depends(_verify)):
        return _bridge.quick_launch(req.app_id)

    # ══════════════════════════════════════════════════
    #  DISPLAY BRIGHTNESS
    # ══════════════════════════════════════════════════

    @app.get("/api/brightness")
    def get_brightness(creds=Depends(_verify)):
        return _bridge.get_brightness()

    @app.post("/api/brightness")
    def set_brightness(req: BrightnessRequest, creds=Depends(_verify)):
        return _bridge.set_brightness(req.level)

    # ══════════════════════════════════════════════════
    #  TOKEN ROTATION
    # ══════════════════════════════════════════════════

    @app.post("/api/token/rotate")
    def rotate_token(creds=Depends(_verify)):
        global _SERVER_TOKEN
        new_token = secrets.token_urlsafe(32)
        TOKEN_FILE.write_text(json.dumps({"token": new_token}, indent=2), encoding="utf-8")
        _SERVER_TOKEN = new_token
        return {"token": new_token}

    # ══════════════════════════════════════════════════
    #  SCHEDULED COMMANDS
    # ══════════════════════════════════════════════════

    @app.get("/api/schedule")
    def list_scheduled(creds=Depends(_verify)):
        return {"schedules": _bridge.list_scheduled()}

    @app.post("/api/schedule")
    def add_scheduled(req: ScheduleRequest, creds=Depends(_verify)):
        entry = _bridge.add_scheduled(req.command, req.hour, req.minute)
        return {"result": "Scheduled", "entry": entry}

    @app.delete("/api/schedule")
    def remove_scheduled(req: ScheduleDeleteRequest, creds=Depends(_verify)):
        ok = _bridge.remove_scheduled(req.id)
        return {"result": "Removed" if ok else "Not found"}

    # Periodic scheduler check (runs every 60s)
    async def _schedule_checker():
        while True:
            await asyncio.sleep(60)
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, _bridge.check_scheduled
                )
            except Exception:
                pass

    @app.on_event("startup")
    async def _start_scheduler():
        asyncio.create_task(_schedule_checker())

    # ══════════════════════════════════════════════════
    #  DATA EXPORT (CSV)
    # ══════════════════════════════════════════════════

    @app.get("/api/export/mood")
    def export_mood(creds=Depends(_verify)):
        csv = _bridge.export_mood_csv()
        return Response(content=csv, media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="mood.csv"'})

    @app.get("/api/export/habits")
    def export_habits(creds=Depends(_verify)):
        csv = _bridge.export_habits_csv()
        return Response(content=csv, media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="habits.csv"'})

    @app.get("/api/export/app-time")
    def export_app_time(creds=Depends(_verify)):
        csv = _bridge.export_app_time_csv()
        return Response(content=csv, media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="app_time.csv"'})

    # ══════════════════════════════════════════════════
    #  PING (REST)
    # ══════════════════════════════════════════════════

    @app.get("/api/ping")
    def ping(creds=Depends(_verify)):
        return {"pong": True, "ts": time.time()}

    # ══════════════════════════════════════════════════
    #  WEBSOCKET (chat + general)
    # ══════════════════════════════════════════════════

    @app.websocket("/ws/chat")
    async def ws_chat(ws: WebSocket):
        await ws.accept()
        try:
            auth_msg = await ws.receive_text()
            if not secrets.compare_digest(auth_msg, _SERVER_TOKEN):
                await ws.close(code=4001, reason="Unauthorized")
                return
        except WebSocketDisconnect:
            return

        await ws.send_json({"type": "connected", "status": _bridge.get_status()})

        try:
            while True:
                data = await ws.receive_text()
                msg = json.loads(data)
                t = msg.get("type")
                if t == "chat":
                    reply = await _bridge.chat(msg["message"])
                    await ws.send_json({"type": "chat", "reply": reply})
                elif t == "status":
                    await ws.send_json({"type": "status", "data": _bridge.get_status()})
                elif t == "command":
                    result = _bridge.execute_command(msg["command"])
                    await ws.send_json({"type": "command", "result": result})
                elif t == "say":
                    _bridge.say(msg["text"])
                    await ws.send_json({"type": "ok"})
        except (WebSocketDisconnect, json.JSONDecodeError):
            pass

    return app


# ---------------------------------------------------------------------------
# Launcher
# ---------------------------------------------------------------------------

def start_server(bridge, host: str = "127.0.0.1", port: int = 7865):
    """Start the server in a daemon thread. Returns (thread, token).
    
    Defaults to localhost only. Pass host='0.0.0.0' to allow LAN access.
    """
    import uvicorn

    app = create_app(bridge)
    token = _SERVER_TOKEN

    config = uvicorn.Config(
        app, host=host, port=port, log_level="warning",
        h11_max_incomplete_event_size=0,  # no header size limit
    )
    srv = uvicorn.Server(config)

    t = threading.Thread(target=srv.run, daemon=True, name="toty-remote-server")
    t.start()
    return t, token

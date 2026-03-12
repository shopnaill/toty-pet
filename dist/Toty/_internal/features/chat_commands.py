"""Chat command engine — parses user messages and executes local commands.

Handles: system commands, app launcher, file finder, math/conversions,
clipboard management, network info, cleanup suggestions.
Returns a result string if a command was matched, or None to fall through to AI.
"""

import ctypes
import logging
import math
import os
import re
import shutil
import subprocess
import time

log = logging.getLogger("toty.commands")

# ── Command registry ─────────────────────────────────────────
# Each handler: (pattern_list, handler_fn)
# handler_fn(match, user_text, context) -> str | None

_COMMANDS: list[tuple[list[re.Pattern], callable]] = []


def _register(*patterns):
    """Decorator to register a command handler with regex patterns."""
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
    def decorator(fn):
        _COMMANDS.append((compiled, fn))
        return fn
    return decorator


def try_command(user_text: str, context: dict) -> str | None:
    """Try to match user_text against registered commands.
    Returns response string if matched, None otherwise."""
    text = user_text.strip()
    for patterns, handler in _COMMANDS:
        for pat in patterns:
            m = pat.search(text)
            if m:
                try:
                    result = handler(m, text, context)
                    if result is not None:
                        return result
                except Exception as exc:
                    log.warning("Command error: %s", exc)
                    return f"\u26a0\ufe0f Oops, something went wrong: {exc}"
    return None


# ══════════════════════════════════════════════════════════════
#  SYSTEM COMMANDS
# ══════════════════════════════════════════════════════════════

@_register(
    r"^open\s+(.+)",
    r"^launch\s+(.+)",
    r"^start\s+(.+)",
    r"^run\s+(.+)",
)
def _cmd_open_app(m, text, ctx):
    app_name = m.group(1).strip().strip('"').strip("'")
    # Common app aliases
    aliases = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe", "calc": "calc.exe",
        "paint": "mspaint.exe",
        "cmd": "cmd.exe", "terminal": "cmd.exe", "command prompt": "cmd.exe",
        "powershell": "powershell.exe",
        "explorer": "explorer.exe", "file explorer": "explorer.exe", "files": "explorer.exe",
        "task manager": "taskmgr.exe", "taskmgr": "taskmgr.exe",
        "settings": "ms-settings:",
        "control panel": "control.exe",
        "snipping tool": "snippingtool.exe", "screenshot": "snippingtool.exe",
        "chrome": "chrome.exe", "google chrome": "chrome.exe",
        "edge": "msedge.exe", "microsoft edge": "msedge.exe",
        "firefox": "firefox.exe",
        "vscode": "code", "vs code": "code", "visual studio code": "code",
        "word": "winword.exe", "excel": "excel.exe", "powerpoint": "powerpnt.exe",
        "discord": "discord.exe",
        "spotify": "spotify.exe",
        "telegram": "telegram.exe",
        "whatsapp": "whatsapp.exe",
    }
    exe = aliases.get(app_name.lower(), app_name)
    try:
        if exe.startswith("ms-"):
            os.startfile(exe)
        else:
            subprocess.Popen(exe, shell=True, creationflags=0x08000000)
        return f"\u2705 Opening {app_name}!"
    except Exception as exc:
        return f"\u274c Couldn't open '{app_name}': {exc}"


@_register(
    r"^(?:kill|close|stop|end)\s+(.+)",
)
def _cmd_kill_app(m, text, ctx):
    proc_name = m.group(1).strip()
    # Add .exe if not present
    if not proc_name.lower().endswith(".exe"):
        proc_name += ".exe"
    try:
        result = subprocess.run(
            ["taskkill", "/IM", proc_name, "/F"],
            capture_output=True, text=True, creationflags=0x08000000,
        )
        if result.returncode == 0:
            return f"\u2705 Killed {proc_name}!"
        else:
            return f"\u274c Couldn't find process '{proc_name}'"
    except Exception as exc:
        return f"\u274c Error: {exc}"


@_register(
    r"(?:empty|clear)\s+(?:the\s+)?recycle\s*bin",
    r"(?:clean|clear)\s+(?:the\s+)?trash",
)
def _cmd_empty_recycle(m, text, ctx):
    try:
        ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x07)
        return "\u2705 Recycle bin emptied! \U0001f5d1\ufe0f"
    except Exception:
        return "\u274c Couldn't empty recycle bin (might need admin)"


# ══════════════════════════════════════════════════════════════
#  SYSTEM INFO
# ══════════════════════════════════════════════════════════════

@_register(
    r"(?:what(?:'?s| is)\s+my\s+ip|my\s+ip\s*address|show\s+ip)",
)
def _cmd_ip(m, text, ctx):
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "unknown"
    # Try to get public IP
    try:
        import urllib.request
        public_ip = urllib.request.urlopen(
            "https://api.ipify.org", timeout=3
        ).read().decode()
    except Exception:
        public_ip = "couldn't fetch"
    return f"\U0001f310 Local IP: {local_ip}\n\U0001f30d Public IP: {public_ip}"


@_register(
    r"(?:disk|storage|drive)\s*(?:space|usage|free|info)",
    r"how\s+much\s+(?:disk|storage|space)",
    r"(?:check|show|see)\s+(?:my\s+)?(?:disk|storage|drive)",
)
def _cmd_disk(m, text, ctx):
    lines = []
    for letter in "CDEFGH":
        path = f"{letter}:\\"
        if os.path.exists(path):
            total, used, free = shutil.disk_usage(path)
            pct = used / total * 100
            bar_len = 15
            filled = int(pct / 100 * bar_len)
            bar = "\u2588" * filled + "\u2591" * (bar_len - filled)
            lines.append(
                f"  {letter}: [{bar}] {pct:.0f}%  "
                f"({free / (1024**3):.1f} GB free / {total / (1024**3):.0f} GB)"
            )
    return "\U0001f4be Disk Usage:\n" + "\n".join(lines) if lines else "\u274c No drives found"


@_register(
    r"(?:system|pc|computer)\s*(?:info|health|status)",
    r"how(?:'?s| is)\s+my\s+(?:pc|computer)",
    r"(?:check|show|see)\s+(?:my\s+)?(?:system|pc|computer)",
)
def _cmd_system_info(m, text, ctx):
    import platform
    lines = ["\U0001f4bb System Info:"]
    lines.append(f"  OS: {platform.system()} {platform.release()} ({platform.architecture()[0]})")
    lines.append(f"  CPU: {os.cpu_count()} cores")

    # RAM via ctypes
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        mem = MEMORYSTATUSEX()
        mem.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
        total_gb = mem.ullTotalPhys / (1024**3)
        avail_gb = mem.ullAvailPhys / (1024**3)
        used_pct = mem.dwMemoryLoad
        lines.append(f"  RAM: {used_pct}% used ({avail_gb:.1f} GB free / {total_gb:.1f} GB)")
    except Exception:
        pass

    # Battery
    try:
        class SYSTEM_POWER_STATUS(ctypes.Structure):
            _fields_ = [
                ("ACLineStatus", ctypes.c_byte),
                ("BatteryFlag", ctypes.c_byte),
                ("BatteryLifePercent", ctypes.c_byte),
                ("SystemStatusFlag", ctypes.c_byte),
                ("BatteryLifeTime", ctypes.c_ulong),
                ("BatteryFullLifeTime", ctypes.c_ulong),
            ]
        sps = SYSTEM_POWER_STATUS()
        ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(sps))
        pct = sps.BatteryLifePercent
        if 0 <= pct <= 100:
            plug = "\u26a1 Plugged in" if sps.ACLineStatus == 1 else "\U0001f50b Battery"
            lines.append(f"  Battery: {pct}% ({plug})")
    except Exception:
        pass

    # Uptime
    try:
        ticks = ctypes.windll.kernel32.GetTickCount64()
        hrs = ticks // (1000 * 3600)
        mins = (ticks // (1000 * 60)) % 60
        lines.append(f"  Uptime: {hrs}h {mins}m")
    except Exception:
        pass

    # Disk summary
    try:
        total, used, free = shutil.disk_usage("C:\\")
        lines.append(f"  C: Drive: {free / (1024**3):.1f} GB free / {total / (1024**3):.0f} GB")
    except Exception:
        pass

    return "\n".join(lines)


@_register(
    r"(?:battery|power)\s*(?:level|status|info)?",
    r"how\s+much\s+battery",
)
def _cmd_battery(m, text, ctx):
    try:
        class SYSTEM_POWER_STATUS(ctypes.Structure):
            _fields_ = [
                ("ACLineStatus", ctypes.c_byte),
                ("BatteryFlag", ctypes.c_byte),
                ("BatteryLifePercent", ctypes.c_byte),
                ("SystemStatusFlag", ctypes.c_byte),
                ("BatteryLifeTime", ctypes.c_ulong),
                ("BatteryFullLifeTime", ctypes.c_ulong),
            ]
        sps = SYSTEM_POWER_STATUS()
        ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(sps))
        pct = sps.BatteryLifePercent
        if 0 <= pct <= 100:
            plug = "\u26a1 Plugged in" if sps.ACLineStatus == 1 else "\U0001f50b On battery"
            emoji = "\U0001f7e2" if pct > 60 else "\U0001f7e1" if pct > 20 else "\U0001f534"
            return f"{emoji} Battery: {pct}% ({plug})"
        return "\U0001f50c Desktop PC — no battery detected"
    except Exception:
        return "\u274c Couldn't read battery status"


# ══════════════════════════════════════════════════════════════
#  QUICK MATH & CONVERSIONS
# ══════════════════════════════════════════════════════════════

@_register(
    r"(?:what(?:'?s| is)\s+)?(\d+(?:\.\d+)?)\s*%\s+of\s+(\d+(?:\.\d+)?)",
)
def _cmd_percent(m, text, ctx):
    pct = float(m.group(1))
    val = float(m.group(2))
    result = pct / 100 * val
    return f"\U0001f4ca {pct}% of {val} = **{result:,.2f}**"


@_register(
    r"(?:calc(?:ulate)?|what(?:'?s| is)|compute)\s+([\d\s\+\-\*\/\.\(\)\^]+)$",
)
def _cmd_calc(m, text, ctx):
    expr = m.group(1).strip().replace("^", "**")
    # Only allow safe characters
    if not re.match(r'^[\d\s\+\-\*\/\.\(\)]+$', expr.replace("**", "")):
        return None
    try:
        result = eval(expr, {"__builtins__": {}}, {"math": math})
        return f"\U0001f9ee {expr} = **{result:,}**" if isinstance(result, int) else f"\U0001f9ee {expr} = **{result:,.4f}**"
    except Exception:
        return f"\u274c Couldn't calculate: {expr}"


@_register(
    r"convert\s+(\d+(?:\.\d+)?)\s*(usd|sar|eur|gbp|egp|aed)\s+to\s+(usd|sar|eur|gbp|egp|aed)",
)
def _cmd_convert_currency(m, text, ctx):
    amount = float(m.group(1))
    fr = m.group(2).upper()
    to = m.group(3).upper()
    # Approximate rates to USD (updated periodically)
    to_usd = {"USD": 1.0, "SAR": 0.2667, "EUR": 1.08, "GBP": 1.27, "EGP": 0.0205, "AED": 0.2723}
    if fr not in to_usd or to not in to_usd:
        return None
    usd_amount = amount * to_usd[fr]
    result = usd_amount / to_usd[to]
    return f"\U0001f4b1 {amount:,.2f} {fr} = **{result:,.2f} {to}**"


@_register(
    r"convert\s+(\d+(?:\.\d+)?)\s*(c|f|celsius|fahrenheit)\s+to\s+(c|f|celsius|fahrenheit)",
)
def _cmd_convert_temp(m, text, ctx):
    val = float(m.group(1))
    fr = m.group(2)[0].upper()
    to = m.group(3)[0].upper()
    if fr == to:
        return f"\U0001f321\ufe0f {val}\u00b0{fr} = {val}\u00b0{to} (same unit!)"
    if fr == "C":
        result = val * 9 / 5 + 32
    else:
        result = (val - 32) * 5 / 9
    return f"\U0001f321\ufe0f {val}\u00b0{fr} = **{result:.1f}\u00b0{to}**"


# ══════════════════════════════════════════════════════════════
#  FILE FINDER
# ══════════════════════════════════════════════════════════════

@_register(
    r"(?:find|search|locate|where(?:'?s| is))\s+(?:my\s+)?(?:file\s+)?['\"]?(.+?)['\"]?\s*$",
)
def _cmd_find_file(m, text, ctx):
    query = m.group(1).strip()
    if len(query) < 2:
        return None
    # Don't match if it's clearly conversational
    skip_words = {"you", "the", "my", "that", "this", "it", "them", "him", "her",
                  "happiness", "love", "meaning", "purpose", "life", "friend",
                  "problem", "issue", "way", "answer", "reason", "thing"}
    if query.lower() in skip_words:
        return None

    search_dirs = []
    user = os.environ.get("USERPROFILE", "")
    if user:
        for d in ["Desktop", "Documents", "Downloads", "Pictures", "Videos"]:
            p = os.path.join(user, d)
            if os.path.isdir(p):
                search_dirs.append(p)

    results = []
    pattern = query.lower()
    for base_dir in search_dirs:
        try:
            for root, dirs, files in os.walk(base_dir):
                # Limit depth to 3
                depth = root.replace(base_dir, "").count(os.sep)
                if depth > 3:
                    dirs.clear()
                    continue
                for f in files:
                    if pattern in f.lower():
                        full = os.path.join(root, f)
                        try:
                            size = os.path.getsize(full)
                        except OSError:
                            size = 0
                        results.append((f, full, size))
                        if len(results) >= 10:
                            break
                if len(results) >= 10:
                    break
        except PermissionError:
            continue
        if len(results) >= 10:
            break

    if not results:
        return f"\U0001f50d Couldn't find any files matching \"{query}\""

    lines = [f"\U0001f50d Found {len(results)} file(s) matching \"{query}\":"]
    for name, path, size in results:
        if size < 1024:
            sz = f"{size} B"
        elif size < 1024 * 1024:
            sz = f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            sz = f"{size / (1024 * 1024):.1f} MB"
        else:
            sz = f"{size / (1024 * 1024 * 1024):.2f} GB"
        lines.append(f"  \U0001f4c4 {name} ({sz})\n     {path}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
#  NETWORK
# ══════════════════════════════════════════════════════════════

@_register(
    r"(?:internet|network|wifi|connection)\s*(?:speed|test|status)",
    r"(?:what(?:'?s| is)\s+my\s+(?:internet\s+)?speed)",
    r"speed\s*test",
)
def _cmd_speed_test(m, text, ctx):
    """Simple download speed test using a small file."""
    try:
        import urllib.request
        url = "http://speed.cloudflare.com/cdn-cgi/trace"
        start = time.monotonic()
        data = urllib.request.urlopen(url, timeout=5).read()
        elapsed = time.monotonic() - start
        size = len(data)
        speed_mbps = (size * 8) / elapsed / 1_000_000
        # Parse some info from the trace
        info = {}
        for line in data.decode().split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                info[k.strip()] = v.strip()
        loc = info.get("loc", "?")
        ip = info.get("ip", "?")
        return (
            f"\U0001f310 Network Status: Connected\n"
            f"  IP: {ip}\n"
            f"  Location: {loc}\n"
            f"  Quick test: ~{speed_mbps:.1f} Mbps\n"
            f"  (Note: This is a rough estimate from a small file)"
        )
    except Exception as exc:
        return f"\u274c Network test failed: {exc}"


# ══════════════════════════════════════════════════════════════
#  CLEANUP SUGGESTIONS
# ══════════════════════════════════════════════════════════════

@_register(
    r"(?:clean|cleanup|clear)\s*(?:up)?\s*(?:my\s+)?(?:pc|computer|disk|temp)",
    r"(?:free|save)\s+(?:up\s+)?(?:disk\s+)?space",
)
def _cmd_cleanup(m, text, ctx):
    """Scan for cleanable items and report sizes."""
    user = os.environ.get("USERPROFILE", "")
    temp = os.environ.get("TEMP", "")
    results = []

    def _dir_size(path, max_files=5000):
        total = 0
        count = 0
        try:
            for root, dirs, files in os.walk(path):
                for f in files:
                    count += 1
                    if count > max_files:
                        return total, count
                    try:
                        total += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
        except PermissionError:
            pass
        return total, count

    # Temp folder
    if temp and os.path.isdir(temp):
        size, count = _dir_size(temp)
        if size > 1024 * 1024:
            results.append(f"  \U0001f4c1 Temp files: {size / (1024**2):.0f} MB ({count} files)\n     {temp}")

    # Browser caches
    cache_paths = {
        "Chrome cache": os.path.join(user, "AppData", "Local", "Google", "Chrome", "User Data", "Default", "Cache"),
        "Edge cache": os.path.join(user, "AppData", "Local", "Microsoft", "Edge", "User Data", "Default", "Cache"),
    }
    for name, path in cache_paths.items():
        if os.path.isdir(path):
            size, count = _dir_size(path, max_files=2000)
            if size > 10 * 1024 * 1024:
                results.append(f"  \U0001f310 {name}: {size / (1024**2):.0f} MB")

    # Downloads folder
    dl = os.path.join(user, "Downloads")
    if os.path.isdir(dl):
        size, count = _dir_size(dl, max_files=2000)
        results.append(f"  \u2b07\ufe0f Downloads: {size / (1024**2):.0f} MB ({count} files)")

    # Recycle bin size (approximate)
    recycle = os.path.join("C:\\", "$Recycle.Bin")
    if os.path.isdir(recycle):
        size, count = _dir_size(recycle, max_files=500)
        if size > 1024 * 1024:
            results.append(f"  \U0001f5d1\ufe0f Recycle Bin: ~{size / (1024**2):.0f} MB")

    if not results:
        return "\u2728 Your PC looks pretty clean already!"

    header = "\U0001f9f9 Cleanup Suggestions:\n"
    footer = "\n\nTip: Say \"empty recycle bin\" to clean trash, or manually clear temp/caches."
    return header + "\n".join(results) + footer


# ══════════════════════════════════════════════════════════════
#  CLIPBOARD
# ══════════════════════════════════════════════════════════════

_clipboard_store: dict[str, str] = {}


@_register(
    r"(?:save|store)\s+(?:this\s+)?clip(?:board)?\s+(?:as\s+)?['\"]?(.+?)['\"]?\s*$",
    r"(?:save|store)\s+clipboard\s+(?:as\s+)?['\"]?(.+?)['\"]?\s*$",
)
def _cmd_save_clip(m, text, ctx):
    name = m.group(1).strip()
    try:
        import subprocess
        result = subprocess.run(
            ["powershell", "-c", "Get-Clipboard"],
            capture_output=True, text=True, timeout=5, creationflags=0x08000000,
        )
        clip = result.stdout.strip()
        if not clip:
            return "\u274c Clipboard is empty!"
        _clipboard_store[name.lower()] = clip
        preview = clip[:80] + "..." if len(clip) > 80 else clip
        return f"\u2705 Saved clipboard as \"{name}\":\n  {preview}"
    except Exception as exc:
        return f"\u274c Couldn't read clipboard: {exc}"


@_register(
    r"(?:paste|get|show)\s+(?:my\s+)?(?:saved\s+)?clip(?:s|board)?\s*$",
    r"(?:list|show)\s+clips?\s*$",
)
def _cmd_list_clips(m, text, ctx):
    if not _clipboard_store:
        return "\U0001f4cb No saved clips yet. Say \"save clipboard as [name]\" to save one!"
    lines = ["\U0001f4cb Saved Clips:"]
    for name, content in _clipboard_store.items():
        preview = content[:60].replace("\n", " ") + ("..." if len(content) > 60 else "")
        lines.append(f"  \u2022 {name}: {preview}")
    lines.append("\nSay \"paste [name]\" to copy one back.")
    return "\n".join(lines)


@_register(
    r"(?:paste|get|copy)\s+(?:clip\s+)?['\"]?(.+?)['\"]?\s*$",
)
def _cmd_paste_clip(m, text, ctx):
    name = m.group(1).strip().lower()
    if name in ("clips", "clipboard", "my clips"):
        return None  # Fall through to list command
    content = _clipboard_store.get(name)
    if not content:
        return f"\u274c No saved clip named \"{name}\""
    try:
        import subprocess
        # Use PowerShell to set clipboard safely
        subprocess.run(
            ["powershell", "-c", f"Set-Clipboard -Value $input"],
            input=content, capture_output=True, text=True, timeout=5,
            creationflags=0x08000000,
        )
        return f"\u2705 Copied \"{name}\" back to clipboard!"
    except Exception as exc:
        return f"\u274c Couldn't set clipboard: {exc}"


# ══════════════════════════════════════════════════════════════
#  HELP
# ══════════════════════════════════════════════════════════════

@_register(
    r"^(?:help|commands|what can you do|capabilities)\s*\??$",
)
def _cmd_help(m, text, ctx):
    return (
        "\U0001f4ac **What I Can Do:**\n\n"
        "\U0001f4bb **System:**\n"
        "  \u2022 open [app] — launch any app\n"
        "  \u2022 kill [app] — close a running app\n"
        "  \u2022 system info — PC health check\n"
        "  \u2022 disk space — storage usage\n"
        "  \u2022 battery — power status\n"
        "  \u2022 speed test — internet speed\n"
        "  \u2022 clean up PC — cleanup suggestions\n"
        "  \u2022 empty recycle bin\n\n"
        "\U0001f50d **Find:**\n"
        "  \u2022 find [filename] — search your files\n"
        "  \u2022 what's my IP — network info\n\n"
        "\U0001f4cb **Clipboard:**\n"
        "  \u2022 save clipboard as [name]\n"
        "  \u2022 show clips — list saved\n"
        "  \u2022 paste [name] — restore a clip\n\n"
        "\U0001f9ee **Math:**\n"
        "  \u2022 what's 15% of 230\n"
        "  \u2022 calculate 125 * 3.5\n"
        "  \u2022 convert 50 USD to SAR\n"
        "  \u2022 convert 100 F to C\n\n"
        "\u23f0 **Reminders:**\n"
        "  \u2022 remind me in 30 min to [task]\n"
        "  \u2022 show reminders\n\n"
        "\U0001f4dd **Memory:**\n"
        "  \u2022 remember [fact]\n"
        "  \u2022 what do you remember about [topic]\n"
        "  \u2022 forget [topic]\n\n"
        "\u2705 **Habits:**\n"
        "  \u2022 I drank water / I exercised / etc.\n"
        "  \u2022 show habits — see streaks\n\n"
        "\U0001f4c5 **Daily:**\n"
        "  \u2022 what do I have today — daily briefing\n"
        "  \u2022 how was my day — session summary\n\n"
        "Or just chat with me about anything! \U0001f43e"
    )


# ══════════════════════════════════════════════════════════════
#  MEMORY (pet_memory integration)
# ══════════════════════════════════════════════════════════════

@_register(
    r"^remember\s+(?:that\s+)?(.+)",
    r"^note\s+(?:that\s+)?(.+)",
)
def _cmd_remember(m, text, ctx):
    memory = ctx.get("memory")
    if not memory:
        return None
    fact = m.group(1).strip()
    return memory.remember(fact)


@_register(
    r"(?:what\s+do\s+you\s+)?remember\s+(?:about\s+)?(.+)",
    r"recall\s+(.+)",
)
def _cmd_recall(m, text, ctx):
    memory = ctx.get("memory")
    if not memory:
        return None
    query = m.group(1).strip()
    return memory.recall(query)


@_register(
    r"^(?:show|list)\s+(?:all\s+)?memor(?:y|ies)\s*$",
    r"^what\s+do\s+you\s+(?:know|remember)\s*\??\s*$",
)
def _cmd_recall_all(m, text, ctx):
    memory = ctx.get("memory")
    if not memory:
        return None
    return memory.recall_all()


@_register(
    r"^forget\s+(?:about\s+)?(.+)",
)
def _cmd_forget(m, text, ctx):
    memory = ctx.get("memory")
    if not memory:
        return None
    query = m.group(1).strip()
    return memory.forget(query)


# ══════════════════════════════════════════════════════════════
#  REMINDERS (reminders integration)
# ══════════════════════════════════════════════════════════════

@_register(
    r"remind\s+me",
    r"set\s+(?:a\s+)?reminder",
    r"in\s+\d+\s*(?:min|hour|hr|sec)\s+remind",
)
def _cmd_add_reminder(m, text, ctx):
    from features.reminders import parse_reminder
    reminder_mgr = ctx.get("reminders")
    if not reminder_mgr:
        return None
    reminder_text, minutes = parse_reminder(text)
    if reminder_text and minutes is not None:
        return reminder_mgr.add(reminder_text, minutes=minutes)
    return "\u26a0\ufe0f Try: \"remind me in 30 minutes to take a break\""


@_register(
    r"^(?:show|list|my)\s+reminders?\s*$",
    r"^reminders?\s*$",
)
def _cmd_list_reminders(m, text, ctx):
    reminder_mgr = ctx.get("reminders")
    if not reminder_mgr:
        return None
    return reminder_mgr.list_active()


@_register(
    r"^cancel\s+reminder\s+(?:#?\s*)?(\d+)",
    r"^cancel\s+reminder\s+(?:about\s+)?(.+)",
)
def _cmd_cancel_reminder(m, text, ctx):
    reminder_mgr = ctx.get("reminders")
    if not reminder_mgr:
        return None
    val = m.group(1).strip()
    if val.isdigit():
        return reminder_mgr.cancel(rid=int(val))
    return reminder_mgr.cancel(keyword=val)


@_register(
    r"^clear\s+(?:all\s+)?reminders?\s*$",
)
def _cmd_clear_reminders(m, text, ctx):
    reminder_mgr = ctx.get("reminders")
    if not reminder_mgr:
        return None
    return reminder_mgr.clear_all()


# ══════════════════════════════════════════════════════════════
#  HABITS (habits integration)
# ══════════════════════════════════════════════════════════════

@_register(
    r"^(?:my\s+)?habits?\s*(?:status)?\s*$",
    r"^show\s+(?:my\s+)?habits?\s*$",
)
def _cmd_habit_status(m, text, ctx):
    tracker = ctx.get("habits")
    if not tracker:
        return None
    return tracker.status()


@_register(
    r"^(?:weekly|week)\s+(?:habits?|report)",
    r"^habits?\s+(?:weekly|report|week)",
)
def _cmd_habit_weekly(m, text, ctx):
    tracker = ctx.get("habits")
    if not tracker:
        return None
    return tracker.weekly_report()


@_register(
    r"^track\s+(.+?)(?:\s+(\d+)x?)?\s*$",
)
def _cmd_track_habit(m, text, ctx):
    tracker = ctx.get("habits")
    if not tracker:
        return None
    name = m.group(1).strip()
    goal = int(m.group(2) or 1)
    return tracker.add_habit(name, goal=goal)


@_register(
    r"^(?:un\s?track|stop\s+tracking|remove\s+habit)\s+(.+)",
)
def _cmd_untrack_habit(m, text, ctx):
    tracker = ctx.get("habits")
    if not tracker:
        return None
    return tracker.remove_habit(m.group(1).strip())


@_register(
    r"^i\s+(?:drank|had|ate|did|took|went\s+for|finished|completed)\s+",
    r"^(?:drank|had|ate|did|took|went\s+for|finished|completed)\s+",
    r"^log\s+",
)
def _cmd_log_habit(m, text, ctx):
    from features.habits import parse_habit_command
    tracker = ctx.get("habits")
    if not tracker:
        return None
    action, name, count = parse_habit_command(text)
    if action == "log" and name:
        return tracker.log_habit(name, count)
    return None


# ══════════════════════════════════════════════════════════════
#  DAILY BRIEFING
# ══════════════════════════════════════════════════════════════

@_register(
    r"(?:what\s+do\s+i\s+have|what(?:'?s| is)\s+(?:my\s+)?(?:plan|schedule|tasks?))\s+today",
    r"^(?:daily\s+)?briefing\s*$",
    r"^morning\s+(?:briefing|report|summary)\s*$",
    r"^good\s+morning\s*!?\s*$",
)
def _cmd_briefing(m, text, ctx):
    briefing = ctx.get("briefing")
    if not briefing:
        return None
    return briefing.morning_briefing()


@_register(
    r"how\s+was\s+my\s+day",
    r"(?:end\s+of\s+)?day\s+summary",
    r"^what\s+did\s+i\s+(?:do|accomplish)\s+today",
)
def _cmd_day_summary(m, text, ctx):
    briefing = ctx.get("briefing")
    if not briefing:
        return None
    return briefing.end_of_day_summary()

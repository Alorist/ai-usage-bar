"""
AI Usage Bar - background program for the Rainmeter skin.

  aiusage.exe collect --data-dir DIR
      Reads Claude / Codex plan limits and (optionally) ccusage token totals,
      writes DIR/rainmeter_data.txt for the skin. Run by the skin every 5 min.

  aiusage.exe helper --config NAME --ini FILE --flag FILE --rainmeter EXE
      Keeps the taskbar variant parked left of the tray and hides it while
      something is fullscreen on the main monitor. Started by the skin; exits
      when Rainmeter closes or the taskbar variant is unloaded.

Everything stays on this PC except one HTTPS request to api.anthropic.com,
which carries your existing Claude Code login token. The token is never
written anywhere.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import datetime as dt
import glob
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request

VERSION = "1.0.0"
HOME = os.path.expanduser("~")
CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CREATE_NO_WINDOW = 0x08000000
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


class NotInstalled(Exception):
    """The tool isn't set up on this PC - the skin hides its section."""


# ----------------------------------------------------------------- helpers


def iso_to_epoch(s):
    if not s:
        return None
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def window_label(minutes):
    if minutes == 10080:
        return "Weekly"
    if minutes and minutes % 60 == 0:
        return f"{minutes // 60}-hour window"
    return f"{minutes}-min window"


def claude_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(HOME, ".claude")


def codex_dir():
    return os.environ.get("CODEX_HOME") or os.path.join(HOME, ".codex")


# -------------------------------------------------------------- collectors


def collect_claude():
    path = os.path.join(claude_dir(), ".credentials.json")
    if not os.path.exists(path):
        raise NotInstalled
    with open(path, encoding="utf-8") as f:
        cred = json.load(f).get("claudeAiOauth")
    if not cred or not cred.get("accessToken"):
        raise NotInstalled  # Claude Code used with an API key, not a subscription
    if cred.get("expiresAt", 0) / 1000 < time.time():
        # Never refresh it ourselves: that could log Claude Code out.
        raise RuntimeError("login expired - open Claude Code to refresh it")
    req = urllib.request.Request(CLAUDE_USAGE_URL, headers={
        "Authorization": "Bearer " + cred["accessToken"],
        "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": f"ai-usage-bar/{VERSION}",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}") from None

    bars = []
    for lim in data.get("limits") or []:
        kind = lim.get("kind")
        if kind == "session":
            label = "Session (5h)"
        elif kind == "weekly_all":
            label = "Weekly (all models)"
        else:
            scope = lim.get("scope") or {}
            name = (scope.get("model") or {}).get("display_name")
            surface = scope.get("surface")
            if not name and surface:
                name = surface.get("display_name") if isinstance(surface, dict) else str(surface)
            name = name or (kind or "limit").replace("_", " ")
            label = f"Weekly ({name})" if lim.get("group") == "weekly" else name
        bars.append({"label": label, "pct": float(lim.get("percent") or 0),
                     "resets_at": iso_to_epoch(lim.get("resets_at"))})
    if not bars:  # older response shape
        for key, label in (("five_hour", "Session (5h)"), ("seven_day", "Weekly (all models)")):
            w = data.get(key)
            if w:
                bars.append({"label": label, "pct": float(w.get("utilization") or 0),
                             "resets_at": iso_to_epoch(w.get("resets_at"))})
    return {"plan": cred.get("subscriptionType"), "bars": bars, "seen_at": time.time()}


def collect_codex():
    sessions = os.path.join(codex_dir(), "sessions")
    if not os.path.isdir(sessions):
        raise NotInstalled
    files = glob.glob(os.path.join(sessions, "**", "*.jsonl"), recursive=True)
    files.sort(key=os.path.getmtime, reverse=True)
    for path in files[:30]:
        last = None
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"rate_limits":{' in line:
                    last = line
        if not last:
            continue
        ev = json.loads(last)
        rl = ev["payload"]["rate_limits"]
        now = time.time()
        bars = []
        for key in ("primary", "secondary"):
            w = rl.get(key)
            if not w:
                continue
            resets = w.get("resets_at")
            expired = resets is not None and resets < now
            bars.append({"label": window_label(w.get("window_minutes")),
                         "pct": 0.0 if expired else float(w.get("used_percent") or 0),
                         "resets_at": None if expired else resets,
                         "reset_note": "reset since last use" if expired else None})
        return {"plan": rl.get("plan_type"), "bars": bars,
                "seen_at": iso_to_epoch(ev.get("timestamp")) or os.path.getmtime(path)}
    raise RuntimeError("no Codex usage recorded yet")


def find_ccusage():
    exe = shutil.which("ccusage.cmd") or shutil.which("ccusage")
    if not exe:
        cand = os.path.join(os.environ.get("APPDATA", ""), "npm", "ccusage.cmd")
        exe = cand if os.path.exists(cand) else None
    return exe


def collect_tokens():
    # Optional: only if the user installed ccusage (npm i -g ccusage). Never downloads anything.
    exe = find_ccusage()
    if not exe:
        raise NotInstalled
    since = (dt.date.today() - dt.timedelta(days=6)).strftime("%Y%m%d")
    p = subprocess.run([exe, "daily", "--json", "--since", since], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL,  # windowed exe has no console handles
                       encoding="utf-8", errors="replace", timeout=180, creationflags=CREATE_NO_WINDOW)
    out = p.stdout
    if "{" not in out:
        raise RuntimeError(f"ccusage failed (exit {p.returncode})")
    data = json.loads(out[out.index("{"):])
    by_day = {d["period"]: d for d in data.get("daily", [])}
    days = []
    for i in range(6, -1, -1):
        day = dt.date.today() - dt.timedelta(days=i)
        d = by_day.get(day.isoformat(), {})
        days.append({"date": day.isoformat(), "tokens": d.get("totalTokens", 0), "cost": d.get("totalCost", 0.0)})
    return {"days": days, "seen_at": time.time()}


def _ascii(v):
    s = str(v if v is not None else "").replace("\r", " ").replace("\n", " ")
    return s.encode("ascii", "replace").decode()


def write_rainmeter(state, path):
    kv = {"version": VERSION, "updated_at": int(state.get("updated_at") or 0)}
    for key in ("claude", "codex"):
        d = state.get(key) or {}
        bars = d.get("bars") or []
        kv.update({f"{key}_available": 1 if d.get("available", True) else 0,
                   f"{key}_plan": (d.get("plan") or "").upper(), f"{key}_error": d.get("error", ""),
                   f"{key}_seen_at": int(d.get("seen_at") or 0), f"{key}_n": len(bars)})
        for i, b in enumerate(bars[:4], 1):
            kv.update({f"{key}_{i}_label": b.get("label"), f"{key}_{i}_pct": round(b.get("pct") or 0, 1),
                       f"{key}_{i}_reset": int(b.get("resets_at") or 0),
                       f"{key}_{i}_note": b.get("reset_note") or ""})
    t = state.get("tokens") or {}
    days = (t.get("days") or [])[-7:]
    kv.update({"tok_available": 1 if t.get("available", True) else 0,
               "tok_error": t.get("error", ""), "tok_seen_at": int(t.get("seen_at") or 0),
               "tok_today_cost": days[-1]["cost"] if days else 0,
               "tok_today_tokens": days[-1]["tokens"] if days else 0,
               "tok_week_cost": sum(d["cost"] for d in days),
               "tok_week_tokens": sum(d["tokens"] for d in days)})
    for i, d in enumerate(days, 1):
        name = "Today" if i == len(days) else dt.date.fromisoformat(d["date"]).strftime("%a")
        kv.update({f"day_{i}_name": name, f"day_{i}_cost": round(d["cost"], 2)})
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="ascii", newline="\n") as f:
        f.writelines(f"{k}={_ascii(v)}\n" for k, v in kv.items())
    os.replace(tmp, path)


def cmd_collect(args):
    os.makedirs(args.data_dir, exist_ok=True)
    state_path = os.path.join(args.data_dir, "usage.json")
    log_path = os.path.join(args.data_dir, "aiusage.log")

    def log(msg):
        try:
            if os.path.exists(log_path) and os.path.getsize(log_path) > 200_000:
                os.replace(log_path, log_path + ".old")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
        except OSError:
            pass

    try:
        try:
            with open(state_path, encoding="utf-8") as f:
                state = json.load(f)
        except (OSError, ValueError):
            state = {}
        for key, fn in (("claude", collect_claude), ("codex", collect_codex), ("tokens", collect_tokens)):
            try:
                state[key] = fn()
                state[key]["available"] = True
            except NotInstalled:
                state[key] = {"available": False}
            except Exception as e:  # keep the last good numbers and flag the problem
                log(f"{key}: {e}")
                prev = state.get(key) or {}
                prev.update({"error": str(e)[:120], "available": True})
                state[key] = prev
            else:
                state[key].pop("error", None)
        state["updated_at"] = time.time()
        tmp = state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=1)
        os.replace(tmp, state_path)
        write_rainmeter(state, os.path.join(args.data_dir, "rainmeter_data.txt"))
    except Exception:
        log(traceback.format_exc())
        return 1
    return 0


# ------------------------------------------------------------------ helper


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]


IGNORE = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
          "RainmeterMeterWindow", "DummyRainWClass", "RainmeterTrayClass"}


def class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def rect(hwnd):
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r


def primary_monitor():
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    user32.GetMonitorInfoW(user32.MonitorFromWindow(user32.FindWindowW("Shell_TrayWnd", None), 1), ctypes.byref(mi))
    return mi


def fullscreen_on_primary():
    fg = user32.GetForegroundWindow()
    if not fg or class_name(fg) in IGNORE:
        return False
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(user32.MonitorFromWindow(fg, 2), ctypes.byref(mi)) or not mi.dwFlags & 1:
        return False
    r, m = rect(fg), mi.rcMonitor
    # maximized windows only cover the work area (taskbar excluded), so they don't count
    return r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom


def find_skin_window(ini_path):
    """Rainmeter titles each skin window with the full path of its .ini."""
    target = os.path.normcase(os.path.abspath(ini_path))
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _):
        if class_name(h) == "RainmeterMeterWindow":
            buf = ctypes.create_unicode_buffer(1024)
            user32.GetWindowTextW(h, buf, 1024)
            if os.path.normcase(buf.value) == target:
                found.append(h)
        return True
    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def taskbar_spot(w, h):
    """Where the bar should sit: on a bottom taskbar, just left of the tray area."""
    tray = user32.FindWindowW("Shell_TrayWnd", None)
    if tray:
        tb = rect(tray)
        horizontal = (tb.right - tb.left) > (tb.bottom - tb.top)
        mon = primary_monitor().rcMonitor
        if horizontal and tb.top > mon.top and (tb.bottom - tb.top) >= h:
            rebar = user32.FindWindowExW(tray, None, "ReBarWindow32", None)
            right = rect(rebar).right if rebar else rect(user32.FindWindowExW(tray, None, "TrayNotifyWnd", None)).left
            return right - w - 12, tb.top + (tb.bottom - tb.top - h) // 2
    work = primary_monitor().rcWork  # taskbar on the side/top or hidden: bottom-right corner of the desktop
    return work.right - w - 16, work.bottom - h - 16


def flag_active(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return "active=1" in f.read().replace("\x00", "").replace(" ", "")
    except OSError:
        return False


def cmd_helper(args):
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except OSError:
        pass
    kernel32.CreateMutexW(None, False, "Local\\AIUsageBarHelper_" + args.config.replace("\\", "_"))
    if kernel32.GetLastError() == 183:  # already running
        return 0

    def bang(*b):
        subprocess.Popen([args.rainmeter, *b, args.config], creationflags=CREATE_NO_WINDOW)

    hidden, missing, tick = None, 0, 0
    while True:
        alive = user32.FindWindowW("DummyRainWClass", None) and flag_active(args.flag)
        missing = 0 if alive else missing + 1
        if missing >= 5:
            if hidden:
                bang("!Show")
            return 0
        if alive:
            fs = fullscreen_on_primary()
            if fs != hidden:
                bang("!Hide" if fs else "!Show")
                hidden = fs
            if not fs and tick % 5 == 0:  # re-park every 5 s (taskbar/tray/resolution changes)
                hwnd = find_skin_window(args.ini)
                if hwnd:
                    r = rect(hwnd)
                    x, y = taskbar_spot(r.right - r.left, r.bottom - r.top)
                    if abs(x - r.left) > 2 or abs(y - r.top) > 2:
                        bang("!Move", str(x), str(y))
        tick += 1
        time.sleep(1)


def main():
    ap = argparse.ArgumentParser(prog="aiusage")
    ap.add_argument("--version", action="version", version=VERSION)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--data-dir", required=True)
    h = sub.add_parser("helper")
    h.add_argument("--config", required=True)
    h.add_argument("--ini", required=True)
    h.add_argument("--flag", required=True)
    h.add_argument("--rainmeter", required=True)
    args = ap.parse_args()
    sys.exit(cmd_collect(args) if args.cmd == "collect" else cmd_helper(args))


if __name__ == "__main__":
    main()

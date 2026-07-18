# -*- coding: utf-8 -*-
"""
Claude Usage - always-on-top mini widget for the Windows desktop corner.

Shows your real Claude subscription limits (same numbers as the built-in
/usage panel in Claude Code): Session (5hr), Weekly (7 day), per-model weekly.

Data sources (in order):
 1. Live: calls the official usage API with the local Claude Code OAuth token
 2. Fallback: reads the cachedUsageUtilization blob in ~/.claude.json

The token is read and used locally only - it never leaves your machine.

Features:
 - Official Claude logo rendered from its SVG path (vector, crisp at any size)
 - Coral breathing glow around the card
 - No third-party dependencies (Python stdlib + tkinter only)
"""
import os
import re
import json
import math
import time
import threading
import urllib.request
from datetime import datetime, timezone
import tkinter as tk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
HOME = os.path.expanduser("~")
CLAUDE_JSON = os.path.join(HOME, ".claude.json")
CREDS_PATH = os.path.join(HOME, ".claude", ".credentials.json")
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
# Claude Code's public OAuth client id + token endpoint (used to refresh the
# access token so the widget stays live without re-opening Claude Code).
OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
TOKEN_SKEW_MS = 120_000   # refresh when within 2 min of expiry

DEFAULT_CONFIG = {
    "refresh_seconds": 60,
    "opacity": 1.0,
    "margin": 16,
    "taskbar_height": 48,
    "glow": True,
}

# --- Claude-style dark palette ---
BG = "#262624"        # card background (warm near-black)
FG = "#faf9f5"        # warm white text
DIM = "#8a8880"       # muted gray
TRACK = "#3d3c39"     # progress track
CORAL = "#e8735a"     # Claude coral accent
WARN = "#e6c07b"      # 70%+
KEY = "#010203"       # transparent color key (rare color -> click-through)

# Official Claude logo, single SVG path from claude-color.svg (viewBox 0 0 24 24)
CLAUDE_PATH = (
    "M4.709 15.955l4.72-2.647.08-.23-.08-.128H9.2l-.79-.048-2.698-.073"
    "-2.339-.097-2.266-.122-.571-.121L0 11.784l.055-.352.48-.321.686.06"
    "1.52.103 2.278.158 1.652.097 2.449.255h.389l.055-.157-.134-.098-.103"
    "-.097-2.358-1.596-2.552-1.688-1.336-.972-.724-.491-.364-.462-.158"
    "-1.008.656-.722.881.06.225.061.893.686 1.908 1.476 2.491 1.833.365"
    ".304.145-.103.019-.073-.164-.274-1.355-2.446-1.446-2.49-.644-1.032"
    "-.17-.619a2.97 2.97 0 01-.104-.729L6.283.134 6.696 0l.996.134.42.364"
    ".62 1.414 1.002 2.229 1.555 3.03.456.898.243.832.091.255h.158V9.01"
    "l.128-1.706.237-2.095.23-2.695.08-.76.376-.91.747-.492.584.28.48.685"
    "-.067.444-.286 1.851-.559 2.903-.364 1.942h.212l.243-.242.985-1.306"
    "1.652-2.064.73-.82.85-.904.547-.431h1.033l.76 1.129-.34 1.166-1.064"
    "1.347-.881 1.142-1.264 1.7-.79 1.36.073.11.188-.02 2.856-.606 1.543"
    "-.28 1.841-.315.833.388.091.395-.328.807-1.969.486-2.309.462-3.439"
    ".813-.042.03.049.061 1.549.146.662.036h1.622l3.02.225.79.522.474.638"
    "-.079.485-1.215.62-1.64-.389-3.829-.91-1.312-.329h-.182v.11l1.093"
    "1.068 2.006 1.81 2.509 2.33.127.578-.322.455-.34-.049-2.205-1.657"
    "-.851-.747-1.926-1.62h-.128v.17l.444.649 2.345 3.521.122 1.08-.17.353"
    "-.608.213-.668-.122-1.374-1.925-1.415-2.167-1.143-1.943-.14.08-.674"
    " 7.254-.316.37-.729.28-.607-.461-.322-.747.322-1.476.389-1.924.315"
    "-1.53.286-1.9.17-.632-.012-.042-.14.018-1.434 1.967-2.18 2.945-1.726"
    " 1.845-.414.164-.717-.37.067-.662.401-.589 2.388-3.036 1.44-1.882.93"
    "-1.086-.006-.158h-.055L4.132 18.56l-1.13.146-.487-.456.061-.746.231"
    "-.243 1.908-1.312-.006.006z"
)


# ----------------- SVG path -> polygons -----------------
_TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?")


def _flatten_cubic(p0, p1, p2, p3, n=16):
    pts = []
    for i in range(1, n + 1):
        t = i / n
        u = 1 - t
        x = (u*u*u*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t*t*t*p3[0])
        y = (u*u*u*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t*t*t*p3[1])
        pts.append((x, y))
    return pts


def _flatten_quad(p0, p1, p2, n=12):
    pts = []
    for i in range(1, n + 1):
        t = i / n
        u = 1 - t
        x = u*u*p0[0] + 2*u*t*p1[0] + t*t*p2[0]
        y = u*u*p0[1] + 2*u*t*p1[1] + t*t*p2[1]
        pts.append((x, y))
    return pts


def _flatten_arc(x0, y0, rx, ry, phi, large, sweep, x, y, n=18):
    if rx == 0 or ry == 0:
        return [(x, y)]
    phi = math.radians(phi)
    cosp, sinp = math.cos(phi), math.sin(phi)
    dx, dy = (x0 - x) / 2, (y0 - y) / 2
    x1p = cosp*dx + sinp*dy
    y1p = -sinp*dx + cosp*dy
    rx, ry = abs(rx), abs(ry)
    lam = x1p*x1p/(rx*rx) + y1p*y1p/(ry*ry)
    if lam > 1:
        s = math.sqrt(lam)
        rx *= s; ry *= s
    num = rx*rx*ry*ry - rx*rx*y1p*y1p - ry*ry*x1p*x1p
    den = rx*rx*y1p*y1p + ry*ry*x1p*x1p
    co = math.sqrt(max(0, num/den)) if den else 0
    if large == sweep:
        co = -co
    cxp = co * rx * y1p / ry
    cyp = -co * ry * x1p / rx
    cx = cosp*cxp - sinp*cyp + (x0 + x)/2
    cy = sinp*cxp + cosp*cyp + (y0 + y)/2

    def ang(ux, uy, vx, vy):
        d = math.hypot(ux, uy) * math.hypot(vx, vy)
        c = max(-1, min(1, (ux*vx + uy*vy) / d)) if d else 1
        a = math.acos(c)
        if ux*vy - uy*vx < 0:
            a = -a
        return a
    th1 = ang(1, 0, (x1p - cxp)/rx, (y1p - cyp)/ry)
    dth = ang((x1p - cxp)/rx, (y1p - cyp)/ry, (-x1p - cxp)/rx, (-y1p - cyp)/ry)
    if not sweep and dth > 0:
        dth -= 2*math.pi
    elif sweep and dth < 0:
        dth += 2*math.pi
    pts = []
    for i in range(1, n + 1):
        th = th1 + dth * i / n
        ex = cx + rx*math.cos(th)*cosp - ry*math.sin(th)*sinp
        ey = cy + rx*math.cos(th)*sinp + ry*math.sin(th)*cosp
        pts.append((ex, ey))
    return pts


def parse_path(d):
    """Parse an SVG path 'd' into a list of subpaths (each a list of points)."""
    toks = _TOKEN.findall(d)
    i = 0
    cx = cy = sx = sy = 0.0
    cmd = None
    subs, cur = [], []

    def num():
        nonlocal i
        v = float(toks[i]); i += 1
        return v

    def flag():
        # Arc flags are single 0/1 digits and may be packed with no
        # separator (e.g. "01" -> large=0, sweep=1). Read one digit.
        nonlocal i
        tok = toks[i]
        ch = tok[0]
        rest = tok[1:]
        if rest == "":
            i += 1
        else:
            toks[i] = rest
        return float(ch)

    while i < len(toks):
        t = toks[i]
        if re.match(r"[A-Za-z]", t):
            cmd = t; i += 1
        rel = cmd.islower()
        c = cmd.upper()
        if c == "M":
            cx, cy = num(), num()
            if rel and cur:
                cx += cur[-1][0]; cy += cur[-1][1]
            if cur:
                subs.append(cur)
            cur = [(cx, cy)]
            sx, sy = cx, cy
            cmd = "l" if rel else "L"
        elif c == "L":
            x, y = num(), num()
            if rel: x += cx; y += cy
            cx, cy = x, y; cur.append((cx, cy))
        elif c == "H":
            x = num()
            if rel: x += cx
            cx = x; cur.append((cx, cy))
        elif c == "V":
            y = num()
            if rel: y += cy
            cy = y; cur.append((cx, cy))
        elif c == "C":
            x1, y1, x2, y2, x, y = num(), num(), num(), num(), num(), num()
            if rel:
                x1 += cx; y1 += cy; x2 += cx; y2 += cy; x += cx; y += cy
            cur += _flatten_cubic((cx, cy), (x1, y1), (x2, y2), (x, y))
            cx, cy = x, y
        elif c == "Q":
            x1, y1, x, y = num(), num(), num(), num()
            if rel:
                x1 += cx; y1 += cy; x += cx; y += cy
            cur += _flatten_quad((cx, cy), (x1, y1), (x, y))
            cx, cy = x, y
        elif c == "A":
            rx, ry, rot = num(), num(), num()
            large, sweep = flag(), flag()
            x, y = num(), num()
            if rel: x += cx; y += cy
            cur += _flatten_arc(cx, cy, rx, ry, rot, large, sweep, x, y)
            cx, cy = x, y
        elif c == "Z":
            cur.append((sx, sy))
            cx, cy = sx, sy
        else:  # unsupported (S/T) - skip a pair defensively
            num(); num()
    if cur:
        subs.append(cur)
    return subs


CLAUDE_SUBPATHS = parse_path(CLAUDE_PATH)


_ICON_CACHE = {}


def _rasterize_logo(size, color=CORAL, bg=BG, ss=4):
    """Rasterize the logo path into a PhotoImage with supersampled
    anti-aliasing: scanline-fill at ss x resolution, then box-downsample,
    blending edge pixels between `color` and `bg`."""
    key = (size, color, bg)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    big = size * ss
    s = big / 24.0
    polys = [[(x * s, y * s) for (x, y) in sub] for sub in CLAUDE_SUBPATHS]

    # scanline even-odd fill into a bitmask
    mask = [[False] * big for _ in range(big)]
    for yi in range(big):
        yc = yi + 0.5
        xs = []
        for poly in polys:
            n = len(poly)
            for i in range(n):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % n]
                if (y1 <= yc < y2) or (y2 <= yc < y1):
                    xs.append(x1 + (yc - y1) * (x2 - x1) / (y2 - y1))
        xs.sort()
        for j in range(0, len(xs) - 1, 2):
            for xi in range(max(0, int(xs[j] + 0.5)),
                            min(big, int(xs[j + 1] + 0.5))):
                mask[yi][xi] = True

    fg_rgb, bg_rgb = _hex(color), _hex(bg)
    img = tk.PhotoImage(width=size, height=size)
    rows = []
    area = ss * ss
    for py in range(size):
        row = []
        for px in range(size):
            cov = 0
            for dy in range(ss):
                mrow = mask[py * ss + dy]
                for dx in range(ss):
                    if mrow[px * ss + dx]:
                        cov += 1
            t = cov / area
            r = int(bg_rgb[0] + (fg_rgb[0] - bg_rgb[0]) * t)
            g = int(bg_rgb[1] + (fg_rgb[1] - bg_rgb[1]) * t)
            b = int(bg_rgb[2] + (fg_rgb[2] - bg_rgb[2]) * t)
            row.append(f"#{r:02x}{g:02x}{b:02x}")
        rows.append("{" + " ".join(row) + "}")
    img.put(" ".join(rows))
    _ICON_CACHE[key] = img
    return img


class ClaudeIcon(tk.Label):
    """Official Claude logo, supersample-antialiased raster of its SVG path."""
    def __init__(self, parent, size=15, color=CORAL, bg=BG, **kw):
        self._img = _rasterize_logo(size, color, bg)
        super().__init__(parent, image=self._img, bg=bg, bd=0, **kw)


# ----------------- data -----------------
def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
        except OSError:
            pass
    return cfg


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def fmt_reset(resets_at):
    dt = parse_ts(resets_at)
    if dt is None:
        return ""
    secs = int((dt - datetime.now(timezone.utc)).total_seconds())
    if secs <= 0:
        return "resetting"
    d, rem = divmod(secs, 86400)
    h, m = divmod(rem // 60, 60)
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def _rows_from_util(util):
    rows = []
    for it in util.get("limits") or []:
        kind = it.get("kind")
        scope = it.get("scope") or {}
        model = (scope.get("model") or {}).get("display_name")
        if kind == "session":
            label, short = "Session (5hr)", "5h"
        elif kind == "weekly_scoped" and model:
            label, short = f"Weekly {model}", model[:1] + "w"
        else:
            label, short = "Weekly (7 day)", "7d"
        rows.append({"label": label, "short": short,
                     "pct": it.get("percent", 0),
                     "resets_at": it.get("resets_at"),
                     "reset": fmt_reset(it.get("resets_at"))})
    return rows


def _read_creds():
    with open(CREDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_creds(creds):
    """Atomically write the credentials file back (preserve permissions)."""
    tmp = CREDS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(creds, f)
    os.replace(tmp, CREDS_PATH)


def _refresh_token(creds):
    """Exchange the refresh token for a new access token; persist it so
    Claude Code stays in sync. Returns the new access token, or None."""
    o = creds.get("claudeAiOauth") or {}
    rt = o.get("refreshToken")
    if not rt:
        return None
    body = json.dumps({
        "grant_type": "refresh_token",
        "refresh_token": rt,
        "client_id": OAUTH_CLIENT_ID,
    }).encode("utf-8")
    req = urllib.request.Request(TOKEN_URL, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "User-Agent": "ClaudeUsageWidget/1.0",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    at = data.get("access_token")
    if not at:
        return None
    o["accessToken"] = at
    if data.get("refresh_token"):
        o["refreshToken"] = data["refresh_token"]
    if data.get("expires_in"):
        o["expiresAt"] = int(time.time() * 1000) + int(data["expires_in"]) * 1000
    creds["claudeAiOauth"] = o
    try:
        _write_creds(creds)
    except OSError:
        pass
    return at


def get_access_token():
    """Return a valid access token, refreshing it first if near expiry."""
    creds = _read_creds()
    o = creds.get("claudeAiOauth") or {}
    token = o.get("accessToken")
    exp = o.get("expiresAt")
    if token and exp and (exp - time.time() * 1000) > TOKEN_SKEW_MS:
        return token                      # still valid
    try:
        new = _refresh_token(creds)       # expired / about to — refresh
        if new:
            return new
    except Exception:
        pass
    return token                          # fall back to the existing one


def fetch_live():
    """Returns (rows, dt, 'live'), 'ratelimited', or None."""
    try:
        token = get_access_token()
        if not token:
            return None
        req = urllib.request.Request(USAGE_URL, headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "Content-Type": "application/json",
            "User-Agent": "ClaudeUsageWidget/1.0",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        rows = _rows_from_util(data)
        if rows:
            return rows, datetime.now(timezone.utc), "live"
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return "ratelimited"
    except Exception:
        pass
    return None


def fetch_cached():
    try:
        with open(CLAUDE_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        cache = data.get("cachedUsageUtilization") or {}
        rows = _rows_from_util(cache.get("utilization", {}))
        fetched = cache.get("fetchedAtMs")
        dt = datetime.fromtimestamp(fetched / 1000, timezone.utc) if fetched else None
        if rows:
            return rows, dt, "cache"
    except Exception:
        pass
    return [], None, "err"


LIVE_OK_INTERVAL = 300    # after a successful live call, wait this long (s)
LIVE_429_BACKOFF = 600    # after a 429 (when we already have data), back off (s)
LIVE_RETRY_NODATA = 30    # retry sooner while we have no live data yet (s)


class UsageSource:
    """Live-first data source with rate-limit backoff.

    The usage endpoint is shared with Claude Code itself and rate-limits
    aggressively, so we only hit it every LIVE_OK_INTERVAL seconds and back
    off harder on 429. Between live calls we reuse the last live result
    (recomputing the reset countdowns) rather than flapping back to the
    stale file cache.
    """
    def __init__(self):
        self._blocked_until = 0.0
        self._last = None            # (rows, dt)

    def get(self):
        now = time.time()
        if now >= self._blocked_until:
            res = fetch_live()
            if not isinstance(res, tuple) and self._last is None:
                # the endpoint rate-limits intermittently; while we have no
                # live data yet, retry a few times within this cycle
                for _ in range(3):
                    time.sleep(4)
                    res = fetch_live()
                    if isinstance(res, tuple):
                        break
            if isinstance(res, tuple):
                # fresh data straight from the API this cycle -> LIVE
                self._last = (res[0], res[1])
                self._blocked_until = now + LIVE_OK_INTERVAL
                rows, dt = self._last
                for r in rows:
                    r["reset"] = fmt_reset(r.get("resets_at"))
                return rows, dt, "live"
            elif self._last is None:
                # no data yet — keep trying soon so first LIVE arrives fast
                self._blocked_until = now + LIVE_RETRY_NODATA
            elif res == "ratelimited":
                self._blocked_until = now + LIVE_429_BACKOFF
            else:
                self._blocked_until = now + LIVE_OK_INTERVAL
        # not fetched fresh this cycle: reuse the last successful LIVE data,
        # labelled CACHED, keeping the time it was actually fetched.
        if self._last:
            rows, dt = self._last
            for r in rows:               # keep the reset countdowns ticking
                r["reset"] = fmt_reset(r.get("resets_at"))
            return rows, dt, "cache"
        return fetch_cached()


def bar_color(pct):
    if pct < 70:
        return CORAL
    if pct < 90:
        return WARN
    return "#ef5350"


def _hex(c):
    return (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16))


def blend(c1, c2, t):
    a, b = _hex(c1), _hex(c2)
    r = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return f"#{r[0]:02x}{r[1]:02x}{r[2]:02x}"


# ----------------- widget -----------------
GLOW_PAD = 4      # glow halo thickness (px) - keep subtle
INNER = 6         # padding between content and card edge
CARD_R = 13       # card corner radius


def rounded_pts(x0, y0, x1, y1, r):
    return [
        x0+r, y0, x1-r, y0, x1, y0, x1, y0+r,
        x1, y1-r, x1, y1, x1-r, y1, x0+r, y1,
        x0, y1, x0, y1-r, x0, y0+r, x0, y0,
    ]


class UsageApp:
    def __init__(self):
        self.cfg = load_config()
        self.source = UsageSource()
        self.expanded = False
        self.src = ""
        self.time_text = ""
        self.rows_data = []
        self.src_text = ""
        self._phase = 0.0
        self._glow_items = []
        self.glow_on = self.cfg.get("glow", True)

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", self.cfg.get("opacity", 1.0))
        # solid card with a crisp 1px coral border: outer frame = border color,
        # inner content padded by the border width. No transparency (which would
        # make rounded corners jagged) and no glow halo (which leaked as black).
        self.border = int(self.cfg.get("border", 1))
        self.root.configure(bg=CORAL)
        self.content = tk.Frame(self.root, bg=BG)
        self.content.pack(padx=self.border, pady=self.border)

        self._bind_move(self.root)
        self._bind_move(self.content)
        self.refresh()

    # ---- interactions ----
    def _bind_move(self, w):
        w.bind("<Button-1>", self._start_move)
        w.bind("<B1-Motion>", self._on_move)
        w.bind("<ButtonRelease-1>", self._on_release)
        w.bind("<Double-Button-1>", self._on_double)

    def _start_move(self, e):
        self._mx, self._my = e.x_root, e.y_root
        self._gx, self._gy = self.root.winfo_x(), self.root.winfo_y()

    def _on_move(self, e):
        dx, dy = e.x_root - self._mx, e.y_root - self._my
        self.root.geometry(f"+{self._gx + dx}+{self._gy + dy}")

    def _toggle(self):
        self.expanded = not self.expanded
        self._render()

    def _on_double(self, e):
        self._dragged = False        # a double-click is never a drag
        self._toggle()
        return "break"

    def _indicator(self, parent, size=6):
        """A small 'LIVE'/'CACHED' text label in the accent color."""
        live = self.src == "live"
        lbl = tk.Label(parent, text="LIVE" if live else "CACHED", bg=BG,
                       fg=CORAL, font=("Segoe UI", size, "bold"),
                       padx=0, pady=0, bd=0)
        return lbl, lbl

    def _on_release(self, e):
        # left button drags only; expand/collapse is on right-click
        if abs(e.x_root - self._mx) + abs(e.y_root - self._my) > 3:
            # dragged: remember drop position (anchor = bottom-right corner)
            self.root.update_idletasks()
            self._anchor = (self.root.winfo_x() + self.root.winfo_width(),
                            self.root.winfo_y() + self.root.winfo_height())

    def _place_bottom_right(self):
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        anchor = getattr(self, "_anchor", None)
        if anchor:
            # keep the user-chosen spot (anchor the bottom-right corner so
            # expand/collapse grows leftward/upward, not off-screen)
            self.root.geometry(f"+{anchor[0] - w}+{anchor[1] - h}")
            return
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        m = self.cfg.get("margin", 16)
        tb = self.cfg.get("taskbar_height", 48)
        self.root.geometry(f"+{sw - w - m}+{sh - h - m - tb}")

    # ---- rendering ----
    def _clear_content(self):
        for w in self.content.winfo_children():
            w.destroy()

    def _render(self):
        self._clear_content()
        if not self.rows_data:
            lb = tk.Label(self.content, text="no data", bg=BG, fg=DIM,
                          font=("Segoe UI", 8))
            lb.pack(padx=6, pady=4)
            self._bind_move(lb)
        elif self.expanded:
            self._render_full()
        else:
            self._render_compact()

        self.root.after(20, self._place_bottom_right)

    def _render_compact(self):
        row = tk.Frame(self.content, bg=BG)
        row.pack(padx=8, pady=4)
        widgets = [row]
        icon = ClaudeIcon(row, size=16)
        icon.grid(row=0, column=0, rowspan=2, padx=(0, 8), sticky="w")
        widgets.append(icon)
        for i, r in enumerate(self.rows_data):
            col = i + 1
            lb = tk.Label(row, text=f"{r['short']} {r['pct']}%", bg=BG, fg=FG,
                          font=("Segoe UI", 9), pady=0, bd=0)
            lb.grid(row=0, column=col, padx=(0 if i == 0 else 10, 0),
                    sticky="s")
            widgets.append(lb)
            rs = tk.Label(row, text=r["reset"].replace(" ", ""), bg=BG,
                          fg="#a09e96", font=("Segoe UI", 7), pady=0, bd=0)
            rs.grid(row=1, column=col, padx=(0 if i == 0 else 10, 0),
                    pady=(0, 0), sticky="n")
            widgets.append(rs)
        close = tk.Label(row, text="✕", bg=BG, fg=DIM, cursor="hand2",
                         font=("Segoe UI", 7), pady=0, bd=0)
        close.grid(row=0, column=len(self.rows_data) + 1, rowspan=2,
                   padx=(8, 0), sticky="ne")
        close.bind("<Button-1>", lambda e: self.root.destroy())
        close.bind("<Enter>", lambda e: close.config(fg=CORAL))
        close.bind("<Leave>", lambda e: close.config(fg=DIM))
        for w in widgets:
            self._bind_move(w)

    def _render_full(self):
        BAR_W, BAR_H = 200, 14
        head = tk.Frame(self.content, bg=BG)
        head.pack(fill="x", padx=9, pady=(6, 2))
        ClaudeIcon(head, size=16).pack(side="left")
        tk.Label(head, text=" Claude Usage", bg=BG, fg=FG,
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        close = tk.Label(head, text="✕", bg=BG, fg=DIM, cursor="hand2",
                         font=("Segoe UI", 8))
        close.pack(side="right", padx=(8, 0))
        close.bind("<Button-1>", lambda e: self.root.destroy())
        close.bind("<Enter>", lambda e: close.config(fg=CORAL))
        close.bind("<Leave>", lambda e: close.config(fg=DIM))
        self._no_move = {close}   # keep its click binding; skip in bind loop
        # LIVE/CACHED indicator + fetch time (replaces the old "live HH:MM")
        ind, _ = self._indicator(head, size=5)
        ind.pack(side="right", padx=(6, 0))
        if self.time_text:
            tk.Label(head, text=self.time_text, bg=BG, fg=DIM,
                     font=("Segoe UI", 7)).pack(side="right", padx=(10, 0))
        for r in self.rows_data:
            block = tk.Frame(self.content, bg=BG)
            block.pack(fill="x", padx=9, pady=(7, 0))
            top = tk.Frame(block, bg=BG)
            top.pack(fill="x")
            tk.Label(top, text=r["label"], bg=BG, fg=FG,
                     font=("Segoe UI", 8)).pack(side="left")
            reset_txt = ("Resetting…" if r["reset"] == "resetting"
                         else f"Resets in {r['reset']}")
            tk.Label(top, text=reset_txt, bg=BG, fg=DIM,
                     font=("Segoe UI", 7)).pack(side="right")
            # gauge: thick bar with the percentage printed on it
            c = tk.Canvas(block, width=BAR_W, height=BAR_H, bg=TRACK,
                          highlightthickness=0)
            c.pack(fill="x", pady=(3, 0))
            pct = max(0, min(100, r["pct"]))
            fill_w = int(BAR_W * pct / 100)
            if fill_w:
                c.create_rectangle(0, 0, fill_w, BAR_H,
                                   fill=bar_color(pct), outline="")
            # put the % label inside the filled part if it fits, else after it
            txt = f"{r['pct']}%"
            if fill_w > 34:
                c.create_text(fill_w - 5, BAR_H // 2, text=txt, anchor="e",
                              fill="#1d1d1b", font=("Segoe UI", 8, "bold"))
            else:
                c.create_text(fill_w + 5, BAR_H // 2, text=txt, anchor="w",
                              fill=FG, font=("Segoe UI", 8, "bold"))
        tk.Frame(self.content, bg=BG, height=7).pack()
        skip = getattr(self, "_no_move", set())
        for w in self.content.winfo_children():
            if w not in skip:
                self._bind_move(w)
            for cc in w.winfo_children():
                if cc not in skip:
                    self._bind_move(cc)

    # ---- data ----
    def refresh(self):
        def work():
            rows, dt, src = self.source.get()
            self.root.after(0, lambda: self._got(rows, dt, src))
        threading.Thread(target=work, daemon=True).start()
        self.root.after(int(self.cfg.get("refresh_seconds", 60)) * 1000,
                        self.refresh)

    def _got(self, rows, dt, src):
        self.rows_data = rows
        self.src = src
        self.time_text = f"{dt.astimezone():%H:%M}" if dt else ""
        if src == "live":
            self.src_text = f"live {dt.astimezone():%H:%M}" if dt else "live"
        elif dt:
            self.src_text = f"cached {dt.astimezone():%H:%M}"
        else:
            self.src_text = "no data"
        self._render()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    UsageApp().run()

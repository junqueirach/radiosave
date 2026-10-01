#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RadioSave - schedule-based internet radio recorder with live metadata.

0.3.0
  * Per-station IANA time zone (DST-aware) instead of a hard-wired Brasilia.
  * "Record extra minutes" padding, in minutes, before and after every capture.
  * "Record Now" - immediate rolling capture split on a chosen clock boundary.
  * ID3 tags written into every finished file.
  * Settings saved on every change, plus a log file next to the recordings.
  * The machine is kept awake while a recording is running (Windows).

0.3.1
  * Stopping a recording, or closing the app, now finalises the MP3 instead of
    throwing it away. Partial files are marked (INCOMPLETE).
  * The "Queue & log" tab blinks blue when something happens, and now sits
    directly after "Schedule".
  * About tab.

Requirements: Python 3.9+ (tkinter, standard library) and ffmpeg.
On Windows also:  pip install tzdata
Filenames:    YYYY-MM-DD-HHh-HHh - PROGRAM NAME.mp3
"""

import ctypes
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time as _time
import tkinter as tk
import unicodedata
import urllib.request
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from tkinter import filedialog, messagebox, ttk

try:
    from zoneinfo import ZoneInfo, available_timezones
    HAVE_ZONEINFO = True
except Exception:
    HAVE_ZONEINFO = False

APP_NAME = "RadioSave"
APP_VERSION = "0.3.1"
APP_AUTHOR = "Luiz Junqueira & Claude AI"
APP_CONTACT = "USEReira.ch@gmail.com"

INCOMPLETE_MARK = "(INCOMPLETE)"
BLINK_MAX_SEC = 15
BLINK_INTERVAL_MS = 450
GRACEFUL_STOP_SEC = 8
CLOSE_WAIT_SEC = 60

DEFAULT_TZ = "America/Sao_Paulo"
FALLBACK_OFFSETS = {
    "America/Sao_Paulo": -180, "America/New_York": -300, "America/Chicago": -360,
    "America/Denver": -420, "America/Los_Angeles": -480, "Europe/London": 0,
    "Europe/Lisbon": 0, "Europe/Madrid": 60, "Europe/Paris": 60, "Europe/Berlin": 60,
    "Europe/Rome": 60, "Europe/Moscow": 180, "UTC": 0, "Africa/Luanda": 60,
    "Asia/Tokyo": 540, "Australia/Sydney": 600,
}
TZ_COMMON = [
    "America/Sao_Paulo", "America/Fortaleza", "America/Manaus", "America/Buenos_Aires",
    "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
    "Europe/London", "Europe/Lisbon", "Europe/Madrid", "Europe/Paris", "Europe/Berlin",
    "Europe/Rome", "Europe/Moscow", "UTC", "Africa/Luanda", "Africa/Maputo",
    "Asia/Tokyo", "Asia/Shanghai", "Asia/Kolkata", "Australia/Sydney",
]

GRACE_MINUTES = 10
META_SAMPLE_SEC = 30
META_IDLE_SEC = 20
LOG_MAX_BYTES = 2_000_000

DAYS_PT = ["Domingo", "Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado"]
DAYS_EN = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
GRID_TO_PYWD = {0: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}
PYWD_TO_GRID = {v: k for k, v in GRID_TO_PYWD.items()}

TZ_CHOICES = ["Radio station time", "My local time", "Custom offset..."]
SPLIT_CHOICES = ["No split (one entry)", "30 minutes", "1 hour", "90 minutes", "2 hours", "3 hours"]
SPLIT_MINUTES = {"No split (one entry)": 0, "30 minutes": 30, "1 hour": 60,
                 "90 minutes": 90, "2 hours": 120, "3 hours": 180}
CHUNK_CHOICES = ["30 minutes", "1 hour", "90 minutes", "2 hours", "3 hours", "Custom..."]
CHUNK_MINUTES = {"30 minutes": 30, "1 hour": 60, "90 minutes": 90,
                 "2 hours": 120, "3 hours": 180}

# ---------------------------------------------------------------------------
# Radio Atlan weekly grid, station time. Used only to seed the schedule on the
# very first run - after that your edits live in the config file.
# Index 0 = Domingo .. 6 = Sabado, each list is hours 00..23.
# ---------------------------------------------------------------------------
ATLAN_GRID = [
    [
        "CONVERSAS SOBRE ESPIRITUALIDADE - REPRISE", "COSMIC REVELATION",
        "LIVROS QUE FAZEM PENSAR - REPRISE", "PARA ONDE CAMINHA A HUMANIDADE - REPRISE",
        "ARVORE DA VIDA - REPRISE", "DESPERTAR DA CONSCIENCIA COSMICA - REPRISE",
        "PONTO DE MUTACAO - REPRISE", "SALUTEM - SAUDE E DESENV. HUMANO - REPRISE",
        "VIVER COM SAUDE - REPRISE", "NA BUSCA DA VERDADE - REPRISE",
        "NO MUNDO DO SER - REPRISE", "PROJETO ORBUM - REPRISE",
        "REINVENCAO DA VIDA - REPRISE", "ATLAN PAINEL - REPRISE",
        "MITOS E CONSPIRACOES - REPRISE", "PONTO DE MUTACAO - REPRISE",
        "MUSICA, ARTE E FILOSOFIA - REPRISE", "IMAGENS E REFLEXOES - REPRISE",
        "A LIRA DE ORFEU", "PAINEIS DA REVELACAO COSMICA", "PROJETO ORBUM",
        "CONVERSAS SOBRE ESPIRITUALIDADE", "ACOMPANHANDO O MUNDO - REPRISE",
        "CONEXOES COSMICAS - REPRISE",
    ],
    [
        "REINVENCAO DA VIDA - REPRISE", "COSMIC REVELATION - REPRISE",
        "PROJETO ORBUM - REPRISE", "NA BUSCA DA VERDADE - REPRISE",
        "PAINEIS DA REVELACAO COSMICA - REPRISE", "VIVER COM SAUDE - REPRISE",
        "NO MUNDO DO SER - REPRISE", "PAINEIS DA REVELACAO COSMICA - REPRISE",
        "PARA ONDE CAMINHA A HUMANIDADE - REPRISE", "ARVORE DA VIDA - REPRISE",
        "DESPERTAR DA CONSCIENCIA COSMICA - REPRISE", "SALUTEM - SAUDE E DESENV. HUMANO - REPRISE",
        "A LIRA DE ORFEU - REPRISE", "PONTO DE MUTACAO - REPRISE",
        "CONVERSAS SOBRE ESPIRITUALIDADE - REPRISE", "MITOS E CONSPIRACOES - REPRISE",
        "DESPERTAR DA CONSCIENCIA COSMICA - REPRISE", "ALEM DAS FRONTEIRAS FILOSOFICAS - REPRISE",
        "A LIRA DE ORFEU - REPRISE", "MUSICA, ARTE E FILOSOFIA - REPRISE",
        "CONEXOES COSMICAS", "LIVROS QUE FAZEM PENSAR", "ATLAN PAINEL - REPRISE",
        "PONTO DE MUTACAO - REPRISE",
    ],
    [
        "DESPERTAR DA CONSCIENCIA COSMICA - REPRISE", "ALEM DAS FRONTEIRAS FILOSOFICAS - REPRISE",
        "NO MUNDO DO SER - REPRISE", "MITOS E CONSPIRACOES - REPRISE",
        "PONTO DE MUTACAO - REPRISE", "CONVERSAS SOBRE ESPIRITUALIDADE - REPRISE",
        "PARA ONDE CAMINHA A HUMANIDADE - REPRISE", "IMAGENS E REFLEXOES - REPRISE",
        "SALUTEM - SAUDE E DESENV. HUMANO - REPRISE", "ACOMPANHANDO O MUNDO - REPRISE",
        "ALEM DAS FRONTEIRAS FILOSOFICAS - REPRISE", "VIVER COM SAUDE - REPRISE",
        "MUSICA, ARTE E FILOSOFIA - REPRISE", "PROJETO ORBUM - REPRISE",
        "LIVROS QUE FAZEM PENSAR - REPRISE", "ATLAN PAINEL - REPRISE",
        "TRANSMUTACAO MUSICAL - REPRISE", "PROJETO ORBUM - REPRISE", "MUSICA",
        "REINVENCAO DA VIDA", "EGREGORA DE MAGIA", "ALEM DAS FRONTEIRAS FILOSOFICAS",
        "CONEXOES COSMICAS - REPRISE", "MUSICA, ARTE E FILOSOFIA - REPRISE",
    ],
    [
        "MITOS E CONSPIRACOES - REPRISE", "TRANSMUTACAO MUSICAL - REPRISE",
        "A LIRA DE ORFEU - REPRISE", "ALEM DAS FRONTEIRAS FILOSOFICAS - REPRISE",
        "CONEXOES COSMICAS - REPRISE", "MUSICA", "CONVERSAS SOBRE ESPIRITUALIDADE - REPRISE",
        "REINVENCAO DA VIDA - REPRISE", "PONTO DE MUTACAO - REPRISE",
        "LIVROS QUE FAZEM PENSAR - REPRISE", "ALEM DAS FRONTEIRAS FILOSOFICAS - REPRISE",
        "MITOS E CONSPIRACOES - REPRISE", "VIVER COM SAUDE - REPRISE",
        "SALUTEM - SAUDE E DESENV. HUMANO - REPRISE", "NA BUSCA DA VERDADE - REPRISE",
        "DESPERTAR DA CONSCIENCIA COSMICA - REPRISE", "IMAGENS E REFLEXOES - REPRISE",
        "PAINEIS DA REVELACAO COSMICA - REPRISE", "TRANSMUTACAO MUSICAL - REPRISE",
        "NO MUNDO DO SER", "ARVORE DA VIDA", "PARA ONDE CAMINHA A HUMANIDADE",
        "A LIRA DE ORFEU - REPRISE", "ATLAN PAINEL - REPRISE",
    ],
    [
        "CONEXOES COSMICAS - REPRISE", "VIVER COM SAUDE - REPRISE",
        "PAINEIS DA REVELACAO COSMICA - REPRISE", "A LIRA DE ORFEU - REPRISE",
        "SALUTEM - SAUDE E DESENV. HUMANO - REPRISE", "MUSICA - REPRISE",
        "TRANSMUTACAO MUSICAL - REPRISE", "ALEM DAS FRONTEIRAS FILOSOFICAS - REPRISE",
        "ARVORE DA VIDA - REPRISE", "PARA ONDE CAMINHA A HUMANIDADE - REPRISE",
        "IMAGENS E REFLEXOES - REPRISE", "MUSICA, ARTE E FILOSOFIA - REPRISE",
        "LIVROS QUE FAZEM PENSAR - REPRISE", "PROJETO ORBUM - REPRISE",
        "A LIRA DE ORFEU - REPRISE", "CONVERSAS SOBRE ESPIRITUALIDADE - REPRISE",
        "CONEXOES COSMICAS - REPRISE", "VIVER COM SAUDE - REPRISE",
        "NO MUNDO DO SER - REPRISE", "DESPERTAR DA CONSCIENCIA COSMICA",
        "SALUTEM - SAUDE E DESENV. HUMANO", "ATLAN PAINEL", "TRANSMUTACAO MUSICAL",
        "PONTO DE MUTACAO - REPRISE",
    ],
    [
        "VIVER COM SAUDE - REPRISE", "PARA ONDE CAMINHA A HUMANIDADE - REPRISE",
        "PONTO DE MUTACAO - REPRISE", "ARVORE DA VIDA - REPRISE",
        "NO MUNDO DO SER - REPRISE", "PAINEIS DA REVELACAO COSMICA - REPRISE",
        "LIVROS QUE FAZEM PENSAR - REPRISE", "MUSICA, ARTE E FILOSOFIA - REPRISE",
        "DESPERTAR DA CONSCIENCIA COSMICA - REPRISE", "TRANSMUTACAO MUSICAL - REPRISE",
        "NA BUSCA DA VERDADE - REPRISE", "CONVERSAS SOBRE ESPIRITUALIDADE - REPRISE",
        "IMAGENS E REFLEXOES - REPRISE", "ACOMPANHANDO O MUNDO - REPRISE",
        "ALEM DAS FRONTEIRAS FILOSOFICAS - REPRISE", "NO MUNDO DO SER - REPRISE",
        "NA BUSCA DA VERDADE - REPRISE", "DESPERTAR DA CONSCIENCIA COSMICA - REPRISE",
        "ARVORE DA VIDA - REPRISE", "REINVENCAO DA VIDA - REPRISE",
        "MUSICA, ARTE E FILOSOFIA", "VIVER COM SAUDE", "IMAGENS E REFLEXOES",
        "SALUTEM - SAUDE E DESENV. HUMANO - REPRISE",
    ],
    [
        "ACOMPANHANDO O MUNDO - REPRISE", "CONEXOES COSMICAS - REPRISE",
        "NO MUNDO DO SER - REPRISE", "DESPERTAR DA CONSCIENCIA COSMICA - REPRISE",
        "CONVERSAS SOBRE ESPIRITUALIDADE - REPRISE", "MUSICA - REPRISE",
        "PAINEIS DA REVELACAO COSMICA - REPRISE", "ARVORE DA VIDA - REPRISE",
        "PONTO DE MUTACAO - REPRISE", "IMAGENS E REFLEXOES - REPRISE",
        "A LIRA DE ORFEU - REPRISE", "TRANSMUTACAO MUSICAL - REPRISE",
        "PROJETO ORBUM - REPRISE", "ATLAN PAINEL - REPRISE",
        "REINVENCAO DA VIDA - REPRISE", "ACOMPANHANDO O MUNDO - REPRISE",
        "PONTO DE MUTACAO", "ARVORE DA VIDA - REPRISE",
        "PARA ONDE CAMINHA A HUMANIDADE - REPRISE", "ATLAN PAINEL - REPRISE",
        "NA BUSCA DA VERDADE", "MITOS E CONSPIRACOES", "CONEXOES COSMICAS - REPRISE",
        "ACOMPANHANDO O MUNDO - REPRISE",
    ],
]


# ===========================================================================
# Time zones
# ===========================================================================

_TZ_CACHE = {}
TZ_DB_OK = True


def get_tz(name):
    """Return a tzinfo for an IANA name, falling back to a fixed offset."""
    global TZ_DB_OK
    name = name or DEFAULT_TZ
    if name in _TZ_CACHE:
        return _TZ_CACHE[name]
    tz = None
    if HAVE_ZONEINFO:
        try:
            tz = ZoneInfo(name)
        except Exception:
            tz = None
            TZ_DB_OK = False
    if tz is None:
        mins = FALLBACK_OFFSETS.get(name, 0)
        tz = timezone(timedelta(minutes=mins), name.split("/")[-1])
    _TZ_CACHE[name] = tz
    return tz


def tz_name_list():
    names = list(TZ_COMMON)
    if HAVE_ZONEINFO:
        try:
            rest = sorted(n for n in available_timezones() if n not in TZ_COMMON)
            if rest:
                names += ["--------"] + rest
        except Exception:
            pass
    else:
        names += ["--------"] + sorted(n for n in FALLBACK_OFFSETS if n not in TZ_COMMON)
    return names


def tz_db_available():
    """True when a real IANA database is reachable (tzdata installed)."""
    if not HAVE_ZONEINFO:
        return False
    try:
        ZoneInfo("America/Sao_Paulo")
        ZoneInfo("Europe/London")
        return True
    except Exception:
        return False


def offset_label(tz, when=None):
    when = when or datetime.now()
    aware = when.replace(tzinfo=None).replace(tzinfo=tz)
    off = aware.utcoffset() or timedelta(0)
    total = int(off.total_seconds() // 60)
    sign = "+" if total >= 0 else "-"
    hh, mm = divmod(abs(total), 60)
    abbr = aware.tzname() or ""
    return "{} (UTC{}{:02d}:{:02d})".format(abbr, sign, hh, mm) if abbr else \
        "UTC{}{:02d}:{:02d}".format(sign, hh, mm)


def local_tz_label():
    now = datetime.now().astimezone()
    off = now.utcoffset() or timedelta(0)
    total = int(off.total_seconds() // 60)
    sign = "+" if total >= 0 else "-"
    hh, mm = divmod(abs(total), 60)
    return "{} (UTC{}{:02d}:{:02d})".format(now.tzname() or "Local", sign, hh, mm)


# ===========================================================================
# Keep the machine awake while capturing
# ===========================================================================

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040


def _set_execution_state(flags):
    if os.name != "nt":
        return
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags))
    except Exception:
        pass


# ===========================================================================
# Pure helpers
# ===========================================================================

def new_id():
    return uuid.uuid4().hex[:10]


def is_rerun(title):
    return "REPRISE" in (title or "").upper()


def config_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, APP_NAME)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "config.json")


def sanitize(name, ascii_only=False):
    if ascii_only:
        name = unicodedata.normalize("NFKD", name)
        name = name.encode("ascii", "ignore").decode("ascii")
    name = re.sub(r'[<>:"/\\|?*]', "-", name)
    name = re.sub(r"[\x00-\x1f]", "", name)
    name = re.sub(r"\s+", " ", name).strip().strip(".")
    return name[:150] or "recording"


def build_filename(start_dt, end_dt, program, ascii_only=False):
    """YYYY-MM-DD-HHh-HHh - PROGRAM NAME.mp3 (nominal programme times)."""
    stem = "{}-{:02d}h-{:02d}h - {}".format(
        start_dt.strftime("%Y-%m-%d"), start_dt.hour, end_dt.hour, program)
    return sanitize(stem, ascii_only) + ".mp3"


def clean_title(raw):
    if not raw:
        return ""
    t = str(raw).strip()
    t = re.sub(r"\s*-\s*-\s*$", "", t)
    t = re.sub(r"\s*[-–]\s*$", "", t)
    t = re.sub(r"^\s*[-–]\s*", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def parse_hhmm(text):
    m = re.match(r"^\s*(\d{1,2})\s*[:hH]?\s*(\d{1,2})?\s*$", text or "")
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2) or 0)
    if hh > 23 or mm > 59:
        return None
    return hh, mm


def localize(naive_dt, tz_kind, station_tz, custom_minutes=0):
    """Attach a timezone to a naive wall-clock time per the user's choice."""
    if tz_kind.startswith("Radio"):
        return naive_dt.replace(tzinfo=station_tz)
    if tz_kind.startswith("My local"):
        return naive_dt.astimezone()
    return naive_dt.replace(tzinfo=timezone(timedelta(minutes=custom_minutes)))


def to_local(dt_aware):
    return dt_aware.astimezone()


def next_occurrence(grid_day, hh, mm, now_station, tz):
    """Next station-local datetime for this weekday + time, after now."""
    ref = now_station.replace(tzinfo=None)
    target = GRID_TO_PYWD[grid_day]
    delta = (target - ref.weekday()) % 7
    cand = ref.replace(hour=hh, minute=mm, second=0, microsecond=0) + timedelta(days=delta)
    if cand <= ref:
        cand += timedelta(days=7)
    return cand.replace(tzinfo=tz)


def entry_next_start(entry, now_station, tz):
    hh, mm = parse_hhmm(entry["start"]) or (0, 0)
    return next_occurrence(entry["day"], hh, mm, now_station, tz)


def entry_is_on_air(entry, now_station, tz):
    hh, mm = parse_hhmm(entry["start"]) or (0, 0)
    ref = now_station.replace(tzinfo=None)
    target = GRID_TO_PYWD[entry["day"]]
    delta = (ref.weekday() - target) % 7
    start = (ref - timedelta(days=delta)).replace(
        hour=hh, minute=mm, second=0, microsecond=0)
    if start > ref:
        start -= timedelta(days=7)
    return start <= ref < start + timedelta(minutes=int(entry.get("dur", 60)))


def ffmpeg_command(ffmpeg, url, duration, outfile, interactive=True):
    """Build the capture command.

    `interactive` leaves stdin open so a 'q' can be sent later, which makes
    ffmpeg close the file cleanly instead of us killing it mid-write.
    """
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "warning"]
    if not interactive:
        cmd.append("-nostdin")
    cmd += [
        "-y", "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "30",
        "-i", url, "-t", str(int(duration)), "-c", "copy", "-f", "mp3", outfile,
    ]
    return cmd


def graceful_stop(proc, timeout=GRACEFUL_STOP_SEC):
    """Ask ffmpeg to finish the file, escalating only if it ignores us."""
    if proc is None or proc.poll() is not None:
        return "already finished"
    try:
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.write("q")
            proc.stdin.flush()
    except Exception:
        pass
    if _wait_for(proc, timeout):
        return "clean"
    try:
        proc.terminate()
    except Exception:
        pass
    if _wait_for(proc, 3):
        return "terminated"
    try:
        proc.kill()
    except Exception:
        pass
    _wait_for(proc, 2)
    return "killed"


def _wait_for(proc, seconds):
    deadline = _time.monotonic() + seconds
    while _time.monotonic() < deadline:
        if proc.poll() is not None:
            return True
        _time.sleep(0.15)
    return proc.poll() is not None


def no_window_kwargs():
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": si, "creationflags": 0x08000000}
    return {}


def tag_mp3(ffmpeg, path, title, album, when, comment):
    """Stream-copy the file back onto itself with ID3v2 metadata attached."""
    if not os.path.exists(path):
        return False, "file missing"
    tmp = path + ".tag.mp3"
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", path, "-c", "copy", "-id3v2_version", "3",
        "-metadata", "title=" + title,
        "-metadata", "album=" + album,
        "-metadata", "artist=" + album,
        "-metadata", "genre=Radio",
        "-metadata", "date=" + when.strftime("%Y-%m-%d"),
        "-metadata", "comment=" + comment,
        "-f", "mp3", tmp,
    ]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                           **no_window_kwargs())
        if p.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 1000:
            os.replace(tmp, path)
            return True, ""
        err = (p.stderr or "").strip()[:200]
    except Exception as exc:
        err = str(exc)
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
    except Exception:
        pass
    return False, err


def decide_name(prefer, radio_name, sched_name, entry_auto):
    radio_name = (radio_name or "").strip()
    sched_name = (sched_name or "").strip()
    if entry_auto:
        return radio_name or sched_name or "UNKNOWN PROGRAM"
    if prefer == "radio":
        return radio_name or sched_name or "UNKNOWN PROGRAM"
    return sched_name or radio_name or "UNKNOWN PROGRAM"


def pick_dominant(titles):
    vals = [t for t in titles if t]
    if not vals:
        return ""
    counts = Counter(vals)
    best = max(counts.values())
    for t in vals:
        if counts[t] == best:
            return t
    return vals[0]


# --------------------------- metadata readers ------------------------------

def fetch_title_json(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": "RadioSave/" + APP_VERSION})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    playing = data.get("playing") or {}
    for key in ("title", "current", "song", "name"):
        v = playing.get(key) if isinstance(playing, dict) else None
        if v:
            return clean_title(v)
    for key in ("title", "songtitle", "current_song", "streamtitle"):
        if data.get(key):
            return clean_title(data[key])
    icestats = data.get("icestats") or {}
    src = icestats.get("source")
    if isinstance(src, list) and src:
        src = src[0]
    if isinstance(src, dict) and src.get("title"):
        return clean_title(src["title"])
    return ""


def fetch_title_icy(stream_url, timeout=10):
    req = urllib.request.Request(stream_url, headers={
        "Icy-MetaData": "1", "User-Agent": "RadioSave/" + APP_VERSION})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        metaint = r.headers.get("icy-metaint")
        if not metaint:
            return ""
        metaint = int(metaint)
        r.read(metaint)
        length = r.read(1)
        if not length:
            return ""
        n = length[0] * 16
        if n <= 0:
            return ""
        block = r.read(n).decode("utf-8", "replace")
    m = re.search(r"StreamTitle='(.*?)';", block)
    return clean_title(m.group(1)) if m else ""


def fetch_station_title(station):
    mode = station.get("meta_mode", "off")
    try:
        if mode == "json" and station.get("meta_url"):
            return fetch_title_json(station["meta_url"])
        if mode == "icy" and station.get("url"):
            return fetch_title_icy(station["url"])
    except Exception:
        return ""
    return ""


def guess_meta_url(stream_url, slug=""):
    m = re.match(r"^(https?)://([^:/]+)(?::\d+)?/", stream_url or "")
    if not m:
        return ""
    scheme, host = m.group(1), m.group(2)
    if not slug:
        return ""
    return "{}://{}/api/status/{}/current.json".format(scheme, host, slug)


def build_batch(days, from_hhmm, to_hhmm, tz_kind, station_tz, custom_minutes,
                split_minutes, prog, auto, ref=None):
    """Expand days + a time range + a split size into schedule entries.

    Times are entered in `tz_kind` and stored as station-local wall clock.
    """
    if not from_hhmm or not to_hhmm:
        return None, "Times must look like 09:00."
    if not days:
        return None, "Tick at least one day."
    ref = ref or datetime.now()

    out = []
    for d in sorted(days):
        target_py = GRID_TO_PYWD[d]
        base = ref.replace(hour=0, minute=0, second=0, microsecond=0)
        base += timedelta(days=(target_py - ref.weekday()) % 7)
        start_naive = base.replace(hour=from_hhmm[0], minute=from_hhmm[1])
        end_naive = base.replace(hour=to_hhmm[0], minute=to_hhmm[1])
        if end_naive <= start_naive:
            end_naive += timedelta(days=1)
        total = int((end_naive - start_naive).total_seconds() // 60)
        if total <= 0:
            continue
        chunk = split_minutes if split_minutes > 0 else total
        cur = start_naive
        while cur < end_naive:
            dur = min(chunk, int((end_naive - cur).total_seconds() // 60))
            in_st = localize(cur, tz_kind, station_tz, custom_minutes).astimezone(station_tz)
            out.append({
                "id": new_id(),
                "day": PYWD_TO_GRID[in_st.weekday()],
                "start": in_st.strftime("%H:%M"),
                "dur": dur,
                "prog": "" if auto else (prog or "").strip(),
                "auto": bool(auto),
                "sel": True,
            })
            cur += timedelta(minutes=chunk)
    if not out:
        return None, "That range produced no entries."
    return out, None


def seed_atlan_entries():
    out = []
    for d, hours in enumerate(ATLAN_GRID):
        for h, prog in enumerate(hours):
            out.append({"id": new_id(), "day": d, "start": "{:02d}:00".format(h),
                        "dur": 60, "prog": prog, "auto": False, "sel": False})
    return out


def default_stations():
    return [{
        "name": "Radio Atlan",
        "url": "https://s30.maxcast.com.br:8157/live",
        "tz": "America/Sao_Paulo",
        "meta_mode": "json",
        "meta_url": "https://s30.maxcast.com.br/api/status/radioatlan/current.json",
        "entries": seed_atlan_entries(),
    }]


# ===========================================================================
# Dialogs
# ===========================================================================

class EntryDialog(tk.Toplevel):
    """Add or edit a single schedule entry."""

    def __init__(self, master, station_tz, entry=None):
        super().__init__(master)
        self.title("Edit entry" if entry else "Add entry")
        self.transient(master)
        self.resizable(False, False)
        self.result = None
        self.station_tz = station_tz

        e = entry or {"day": 0, "start": "19:00", "dur": 60, "prog": "", "auto": False}
        self.v_day = tk.StringVar(value=DAYS_PT[e["day"]])
        self.v_start = tk.StringVar(value=e["start"])
        self.v_dur = tk.IntVar(value=int(e.get("dur", 60)))
        self.v_prog = tk.StringVar(value=e.get("prog", ""))
        self.v_auto = tk.BooleanVar(value=bool(e.get("auto", False)))
        self.v_tz = tk.StringVar(value=TZ_CHOICES[0])
        self.v_custom = tk.StringVar(value="0")

        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="Times entered in:").grid(row=0, column=0, sticky="e", pady=4)
        cb = ttk.Combobox(f, textvariable=self.v_tz, values=TZ_CHOICES, state="readonly", width=24)
        cb.grid(row=0, column=1, sticky="w", pady=4)
        cb.bind("<<ComboboxSelected>>", lambda ev: self._toggle_custom())
        self.ent_custom = ttk.Entry(f, textvariable=self.v_custom, width=8)
        self.lbl_custom = ttk.Label(f, text="UTC offset (minutes):")

        ttk.Label(f, text="Day:").grid(row=2, column=0, sticky="e", pady=4)
        ttk.Combobox(f, textvariable=self.v_day, values=DAYS_PT, state="readonly",
                     width=24).grid(row=2, column=1, sticky="w", pady=4)

        ttk.Label(f, text="Start (HH:MM):").grid(row=3, column=0, sticky="e", pady=4)
        ttk.Entry(f, textvariable=self.v_start, width=10).grid(row=3, column=1, sticky="w", pady=4)

        ttk.Label(f, text="Duration (minutes):").grid(row=4, column=0, sticky="e", pady=4)
        ttk.Spinbox(f, from_=1, to=1440, textvariable=self.v_dur, width=8).grid(
            row=4, column=1, sticky="w", pady=4)

        ttk.Label(f, text="Program name:").grid(row=5, column=0, sticky="e", pady=4)
        self.ent_prog = ttk.Entry(f, textvariable=self.v_prog, width=40)
        self.ent_prog.grid(row=5, column=1, sticky="we", pady=4)

        ttk.Checkbutton(f, text="Use the program name reported by the radio (if available)",
                        variable=self.v_auto, command=self._toggle_auto).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(2, 8))

        btns = ttk.Frame(f)
        btns.grid(row=7, column=0, columnspan=2, pady=(6, 0))
        ttk.Button(btns, text="OK", width=10, command=self._ok).pack(side="left", padx=5)
        ttk.Button(btns, text="Cancel", width=10, command=self.destroy).pack(side="left", padx=5)

        self._toggle_auto()
        self._toggle_custom()
        self.grab_set()
        self.wait_window()

    def _toggle_custom(self):
        if self.v_tz.get().startswith("Custom"):
            self.lbl_custom.grid(row=1, column=0, sticky="e", pady=4)
            self.ent_custom.grid(row=1, column=1, sticky="w", pady=4)
        else:
            self.lbl_custom.grid_remove()
            self.ent_custom.grid_remove()

    def _toggle_auto(self):
        self.ent_prog.config(state="disabled" if self.v_auto.get() else "normal")

    def _ok(self):
        hm = parse_hhmm(self.v_start.get())
        if not hm:
            messagebox.showwarning(APP_NAME, "Start time must look like 19:00.", parent=self)
            return
        if not self.v_auto.get() and not self.v_prog.get().strip():
            messagebox.showwarning(
                APP_NAME, "Give the entry a program name, or tick the radio-name box.", parent=self)
            return
        try:
            custom = int(self.v_custom.get() or 0)
        except ValueError:
            messagebox.showwarning(APP_NAME, "Offset must be a whole number of minutes.", parent=self)
            return

        day = DAYS_PT.index(self.v_day.get())
        hh, mm = hm
        ref = datetime.now()
        target_py = GRID_TO_PYWD[day]
        naive = ref.replace(hour=hh, minute=mm, second=0, microsecond=0)
        naive += timedelta(days=(target_py - ref.weekday()) % 7)
        aware = localize(naive, self.v_tz.get(), self.station_tz, custom)
        in_st = aware.astimezone(self.station_tz)

        self.result = {
            "id": new_id(),
            "day": PYWD_TO_GRID[in_st.weekday()],
            "start": in_st.strftime("%H:%M"),
            "dur": int(self.v_dur.get()),
            "prog": "" if self.v_auto.get() else self.v_prog.get().strip(),
            "auto": bool(self.v_auto.get()),
            "sel": True,
        }
        self.destroy()


class BatchDialog(tk.Toplevel):
    """Create many entries at once from days + a time range + a split size."""

    def __init__(self, master, station_tz):
        super().__init__(master)
        self.title("Batch add entries")
        self.transient(master)
        self.resizable(False, False)
        self.result = None
        self.station_tz = station_tz

        self.v_days = [tk.BooleanVar(value=False) for _ in range(7)]
        self.v_from = tk.StringVar(value="09:00")
        self.v_to = tk.StringVar(value="15:00")
        self.v_tz = tk.StringVar(value=TZ_CHOICES[0])
        self.v_custom = tk.StringVar(value="0")
        self.v_split = tk.StringVar(value="1 hour")
        self.v_prog = tk.StringVar(value="")
        self.v_auto = tk.BooleanVar(value=True)

        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="Days of the week:").grid(row=0, column=0, sticky="ne", pady=4)
        dayf = ttk.Frame(f)
        dayf.grid(row=0, column=1, sticky="w", pady=4)
        for i, name in enumerate(DAYS_PT):
            ttk.Checkbutton(dayf, text=name[:3], variable=self.v_days[i]).pack(side="left")

        ttk.Label(f, text="Times entered in:").grid(row=1, column=0, sticky="e", pady=4)
        cb = ttk.Combobox(f, textvariable=self.v_tz, values=TZ_CHOICES, state="readonly", width=24)
        cb.grid(row=1, column=1, sticky="w", pady=4)
        cb.bind("<<ComboboxSelected>>", lambda ev: self._toggle_custom())
        self.lbl_custom = ttk.Label(f, text="UTC offset (minutes):")
        self.ent_custom = ttk.Entry(f, textvariable=self.v_custom, width=8)

        ttk.Label(f, text="From (HH:MM):").grid(row=3, column=0, sticky="e", pady=4)
        ttk.Entry(f, textvariable=self.v_from, width=10).grid(row=3, column=1, sticky="w", pady=4)
        ttk.Label(f, text="To (HH:MM):").grid(row=4, column=0, sticky="e", pady=4)
        ttk.Entry(f, textvariable=self.v_to, width=10).grid(row=4, column=1, sticky="w", pady=4)

        ttk.Label(f, text="Split each:").grid(row=5, column=0, sticky="e", pady=4)
        ttk.Combobox(f, textvariable=self.v_split, values=SPLIT_CHOICES,
                     state="readonly", width=24).grid(row=5, column=1, sticky="w", pady=4)

        ttk.Label(f, text="Program name:").grid(row=6, column=0, sticky="e", pady=4)
        self.ent_prog = ttk.Entry(f, textvariable=self.v_prog, width=40)
        self.ent_prog.grid(row=6, column=1, sticky="we", pady=4)
        ttk.Checkbutton(f, text="Use the program name reported by the radio (if available)",
                        variable=self.v_auto, command=self._toggle_auto).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(2, 6))

        ttk.Button(f, text="Preview", command=self._preview).grid(row=8, column=0, sticky="e", pady=6)
        self.lst = tk.Listbox(f, height=9, width=64)
        self.lst.grid(row=9, column=0, columnspan=2, sticky="we", pady=(0, 8))

        btns = ttk.Frame(f)
        btns.grid(row=10, column=0, columnspan=2)
        ttk.Button(btns, text="Create", width=10, command=self._ok).pack(side="left", padx=5)
        ttk.Button(btns, text="Cancel", width=10, command=self.destroy).pack(side="left", padx=5)

        self._toggle_auto()
        self._toggle_custom()
        self._preview()
        self.grab_set()
        self.wait_window()

    def _toggle_custom(self):
        if self.v_tz.get().startswith("Custom"):
            self.lbl_custom.grid(row=2, column=0, sticky="e", pady=4)
            self.ent_custom.grid(row=2, column=1, sticky="w", pady=4)
        else:
            self.lbl_custom.grid_remove()
            self.ent_custom.grid_remove()

    def _toggle_auto(self):
        self.ent_prog.config(state="disabled" if self.v_auto.get() else "normal")

    def _compute(self):
        try:
            custom = int(self.v_custom.get() or 0)
        except ValueError:
            return None, "Offset must be a whole number of minutes."
        return build_batch(
            days=[i for i, v in enumerate(self.v_days) if v.get()],
            from_hhmm=parse_hhmm(self.v_from.get()),
            to_hhmm=parse_hhmm(self.v_to.get()),
            tz_kind=self.v_tz.get(),
            station_tz=self.station_tz,
            custom_minutes=custom,
            split_minutes=SPLIT_MINUTES[self.v_split.get()],
            prog=self.v_prog.get(),
            auto=self.v_auto.get(),
        )

    def _preview(self):
        self.lst.delete(0, "end")
        entries, err = self._compute()
        if err:
            self.lst.insert("end", err)
            return
        for e in entries[:200]:
            label = e["prog"] or "<name from radio>"
            self.lst.insert("end", "{}  {} radio time  +{} min   {}".format(
                DAYS_PT[e["day"]][:3], e["start"], e["dur"], label))
        self.lst.insert("end", "--- {} entries will be created ---".format(len(entries)))

    def _ok(self):
        entries, err = self._compute()
        if err:
            messagebox.showwarning(APP_NAME, err, parent=self)
            return
        if not self.v_auto.get() and not self.v_prog.get().strip():
            messagebox.showwarning(
                APP_NAME, "Give a program name, or tick the radio-name box.", parent=self)
            return
        self.result = entries
        self.destroy()


class StationDialog(tk.Toplevel):
    def __init__(self, master, station=None):
        super().__init__(master)
        self.title("Edit station" if station else "Add station")
        self.transient(master)
        self.resizable(False, False)
        self.result = None
        s = station or {"name": "", "url": "", "tz": DEFAULT_TZ,
                        "meta_mode": "icy", "meta_url": ""}

        self.v_name = tk.StringVar(value=s.get("name", ""))
        self.v_url = tk.StringVar(value=s.get("url", ""))
        self.v_tz = tk.StringVar(value=s.get("tz", DEFAULT_TZ))
        self.v_mode = tk.StringVar(value=s.get("meta_mode", "icy"))
        self.v_meta = tk.StringVar(value=s.get("meta_url", ""))
        self.v_slug = tk.StringVar(value="")

        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Station name:").grid(row=0, column=0, sticky="e", pady=4)
        ttk.Entry(f, textvariable=self.v_name, width=46).grid(row=0, column=1, pady=4)
        ttk.Label(f, text="Stream URL:").grid(row=1, column=0, sticky="e", pady=4)
        ttk.Entry(f, textvariable=self.v_url, width=46).grid(row=1, column=1, pady=4)

        ttk.Label(f, text="Radio time zone:").grid(row=2, column=0, sticky="e", pady=4)
        tzf = ttk.Frame(f)
        tzf.grid(row=2, column=1, sticky="we", pady=4)
        self.cmb_tz = ttk.Combobox(tzf, textvariable=self.v_tz, values=tz_name_list(), width=30)
        self.cmb_tz.pack(side="left")
        self.cmb_tz.bind("<<ComboboxSelected>>", lambda ev: self._show_offset())
        self.cmb_tz.bind("<KeyRelease>", lambda ev: self._show_offset())
        self.lbl_off = ttk.Label(tzf, text="", foreground="#0a6b0a")
        self.lbl_off.pack(side="left", padx=8)

        box = ttk.LabelFrame(f, text="Now-playing source")
        box.grid(row=3, column=0, columnspan=2, sticky="we", pady=8)
        ttk.Radiobutton(box, text="Status JSON (Maxcast / Icecast API)", value="json",
                        variable=self.v_mode).grid(row=0, column=0, columnspan=3, sticky="w", padx=6)
        ttk.Label(box, text="JSON URL:").grid(row=1, column=0, sticky="e", padx=6)
        ttk.Entry(box, textvariable=self.v_meta, width=44).grid(row=1, column=1, columnspan=2, pady=3)
        ttk.Label(box, text="Maxcast slug:").grid(row=2, column=0, sticky="e", padx=6)
        ttk.Entry(box, textvariable=self.v_slug, width=18).grid(row=2, column=1, sticky="w")
        ttk.Button(box, text="Build URL", command=self._guess).grid(row=2, column=2, sticky="w", padx=4)
        ttk.Radiobutton(box, text="ICY metadata read from the stream (works almost anywhere)",
                        value="icy", variable=self.v_mode).grid(
            row=3, column=0, columnspan=3, sticky="w", padx=6, pady=(6, 0))
        ttk.Radiobutton(box, text="Off - always use the scheduled name", value="off",
                        variable=self.v_mode).grid(row=4, column=0, columnspan=3,
                                                   sticky="w", padx=6, pady=(0, 6))

        btns = ttk.Frame(f)
        btns.grid(row=4, column=0, columnspan=2, pady=6)
        ttk.Button(btns, text="Test now", width=10, command=self._test).pack(side="left", padx=5)
        ttk.Button(btns, text="OK", width=10, command=self._ok).pack(side="left", padx=5)
        ttk.Button(btns, text="Cancel", width=10, command=self.destroy).pack(side="left", padx=5)
        self._show_offset()
        self.grab_set()
        self.wait_window()

    def _show_offset(self):
        name = self.v_tz.get().strip()
        if not name or name.startswith("---"):
            self.lbl_off.config(text="")
            return
        tz = get_tz(name)
        now = datetime.now(tz)
        self.lbl_off.config(text="now {}  {}".format(
            now.strftime("%H:%M"), offset_label(tz)))

    def _guess(self):
        u = guess_meta_url(self.v_url.get().strip(), self.v_slug.get().strip())
        if u:
            self.v_meta.set(u)
        else:
            messagebox.showinfo(APP_NAME, "Enter the stream URL and the Maxcast slug first.\n"
                                          "For player.maxcast.com.br/radioatlan the slug is 'radioatlan'.",
                                parent=self)

    def _test(self):
        st = {"url": self.v_url.get().strip(), "meta_mode": self.v_mode.get(),
              "meta_url": self.v_meta.get().strip()}
        t = fetch_station_title(st)
        messagebox.showinfo(APP_NAME, "Radio reports:\n\n{}".format(t or "(nothing)"), parent=self)

    def _ok(self):
        if not self.v_name.get().strip() or not self.v_url.get().strip():
            messagebox.showwarning(APP_NAME, "Name and stream URL are required.", parent=self)
            return
        tzname = self.v_tz.get().strip()
        if not tzname or tzname.startswith("---"):
            messagebox.showwarning(APP_NAME, "Pick a time zone for this station.", parent=self)
            return
        self.result = {"name": self.v_name.get().strip(), "url": self.v_url.get().strip(),
                       "tz": tzname, "meta_mode": self.v_mode.get(),
                       "meta_url": self.v_meta.get().strip()}
        self.destroy()


class RecordNowDialog(tk.Toplevel):
    """Start an immediate rolling capture, split on a chosen clock boundary."""

    def __init__(self, master, station, pre_min, post_min):
        super().__init__(master)
        self.title("Record Now")
        self.transient(master)
        self.resizable(False, False)
        self.result = None
        self.station = station
        self.tz = get_tz(station.get("tz"))
        self.pre_min = pre_min
        self.post_min = post_min

        now = datetime.now(self.tz)
        nxt = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))

        self.v_chunk = tk.StringVar(value="1 hour")
        self.v_chunk_custom = tk.StringVar(value="60")
        self.v_cut = tk.StringVar(value=nxt.strftime("%H:%M"))
        self.v_prog = tk.StringVar(value="")
        self.v_auto = tk.BooleanVar(value=True)

        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="Station:").grid(row=0, column=0, sticky="e", pady=4)
        ttk.Label(f, text=station.get("name", ""), font=("Segoe UI", 10, "bold")).grid(
            row=0, column=1, sticky="w", pady=4)

        ttk.Label(f, text="Radio clock:").grid(row=1, column=0, sticky="e", pady=4)
        self.lbl_now = ttk.Label(f, text="")
        self.lbl_now.grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(f, text="Length of each file:").grid(row=2, column=0, sticky="e", pady=4)
        cf = ttk.Frame(f)
        cf.grid(row=2, column=1, sticky="w", pady=4)
        cb = ttk.Combobox(cf, textvariable=self.v_chunk, values=CHUNK_CHOICES,
                          state="readonly", width=16)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda ev: (self._toggle_custom(), self._preview()))
        self.ent_chunk = ttk.Spinbox(cf, from_=5, to=720, textvariable=self.v_chunk_custom,
                                     width=6, command=self._preview)
        self.lbl_chunk = ttk.Label(cf, text="minutes")

        ttk.Label(f, text="First cut at (radio time):").grid(row=3, column=0, sticky="e", pady=4)
        ce = ttk.Entry(f, textvariable=self.v_cut, width=10)
        ce.grid(row=3, column=1, sticky="w", pady=4)
        ce.bind("<KeyRelease>", lambda ev: self._preview())

        ttk.Label(f, text="Program name:").grid(row=4, column=0, sticky="e", pady=4)
        self.ent_prog = ttk.Entry(f, textvariable=self.v_prog, width=38)
        self.ent_prog.grid(row=4, column=1, sticky="we", pady=4)
        ttk.Checkbutton(f, text="Use the program name reported by the radio (if available)",
                        variable=self.v_auto, command=self._toggle_auto).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(2, 6))

        pad = "off" if (pre_min == 0 and post_min == 0) else \
            "+{} min before / +{} min after each cut".format(pre_min, post_min)
        ttk.Label(f, text="Extra minutes: {}".format(pad), foreground="#555").grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(0, 6))

        ttk.Label(f, text="Files that will be produced:").grid(
            row=7, column=0, columnspan=2, sticky="w")
        self.lst = tk.Listbox(f, height=6, width=62)
        self.lst.grid(row=8, column=0, columnspan=2, sticky="we", pady=(2, 8))

        ttk.Label(f, text="Recording keeps rolling until you press Stop.",
                  foreground="#555").grid(row=9, column=0, columnspan=2, sticky="w")

        btns = ttk.Frame(f)
        btns.grid(row=10, column=0, columnspan=2, pady=(8, 0))
        ttk.Button(btns, text="Start", width=10, command=self._ok).pack(side="left", padx=5)
        ttk.Button(btns, text="Cancel", width=10, command=self.destroy).pack(side="left", padx=5)

        self._toggle_auto()
        self._toggle_custom()
        self._tick()
        self._preview()
        self.grab_set()
        self.wait_window()

    def _tick(self):
        try:
            self.lbl_now.config(text="{}   {}".format(
                datetime.now(self.tz).strftime("%a %d %b  %H:%M:%S"), offset_label(self.tz)))
            self.after(1000, self._tick)
        except tk.TclError:
            pass

    def _toggle_custom(self):
        if self.v_chunk.get().startswith("Custom"):
            self.ent_chunk.pack(side="left", padx=6)
            self.lbl_chunk.pack(side="left")
        else:
            self.ent_chunk.pack_forget()
            self.lbl_chunk.pack_forget()

    def _toggle_auto(self):
        self.ent_prog.config(state="disabled" if self.v_auto.get() else "normal")

    def _chunk_minutes(self):
        if self.v_chunk.get().startswith("Custom"):
            try:
                return max(5, int(self.v_chunk_custom.get()))
            except ValueError:
                return 0
        return CHUNK_MINUTES.get(self.v_chunk.get(), 60)

    def _first_cut(self):
        hm = parse_hhmm(self.v_cut.get())
        if not hm:
            return None
        now = datetime.now(self.tz)
        ref = now.replace(tzinfo=None)
        cut = ref.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
        if cut <= ref + timedelta(seconds=30):
            cut += timedelta(days=1)
        return cut.replace(tzinfo=self.tz)

    def _preview(self):
        self.lst.delete(0, "end")
        chunk = self._chunk_minutes()
        cut = self._first_cut()
        if not chunk:
            self.lst.insert("end", "Length must be a whole number of minutes.")
            return
        if not cut:
            self.lst.insert("end", "First cut must look like 11:00.")
            return
        now = datetime.now(self.tz)
        first = int((cut - now).total_seconds() // 60)
        if first > 24 * 60:
            self.lst.insert("end", "First cut is more than a day away - check the time.")
            return
        seg_start, seg_end = now, cut
        for i in range(5):
            self.lst.insert("end", "{}  {} -> {}   ({} min){}".format(
                seg_start.strftime("%d %b"), seg_start.strftime("%H:%M"),
                seg_end.strftime("%H:%M"),
                int((seg_end - seg_start).total_seconds() // 60),
                "   <- first, starts now" if i == 0 else ""))
            seg_start, seg_end = seg_end, seg_end + timedelta(minutes=chunk)
        self.lst.insert("end", "...and so on until you press Stop.")

    def _ok(self):
        chunk = self._chunk_minutes()
        cut = self._first_cut()
        if not chunk:
            messagebox.showwarning(APP_NAME, "Length must be a whole number of minutes.", parent=self)
            return
        if not cut:
            messagebox.showwarning(APP_NAME, "First cut must look like 11:00.", parent=self)
            return
        if not self.v_auto.get() and not self.v_prog.get().strip():
            messagebox.showwarning(
                APP_NAME, "Give a program name, or tick the radio-name box.", parent=self)
            return
        self.result = {
            "chunk": chunk,
            "first_cut": cut,
            "prog": "" if self.v_auto.get() else self.v_prog.get().strip(),
            "auto": bool(self.v_auto.get()),
        }
        self.destroy()


# ===========================================================================
# Main window
# ===========================================================================

class RadioSaveApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("{} {}".format(APP_NAME, APP_VERSION))
        self.geometry("1160x760")
        self.minsize(1000, 660)

        self.log_q = queue.Queue()
        self.stop_event = threading.Event()
        self.recnow_stop = threading.Event()
        self.quit_event = threading.Event()
        self.recnow_thread = None
        self.scheduler_thread = None
        self.captures = []               # live capture records
        self.active_lock = threading.Lock()
        self.awake_holds = 0
        self.row_entry = {}
        self.queue_rows = []
        self.live_title = ""
        self.live_checked = None
        self._saving = False
        self._blinking = False
        self._blink_on = False
        self._blink_until = 0.0
        self._closing = False

        cfg = self.load_config()
        self.stations = cfg.get("stations") or default_stations()
        for s in self.stations:
            s.setdefault("entries", [])
            s.setdefault("meta_mode", "off")
            s.setdefault("meta_url", "")
            s.setdefault("tz", DEFAULT_TZ)

        self.v_station = tk.StringVar(value=cfg.get("station", self.stations[0]["name"]))
        self.v_url = tk.StringVar()
        self.v_outdir = tk.StringVar(value=cfg.get(
            "outdir", os.path.join(os.path.expanduser("~"), "RadioSave")))
        self.v_ffmpeg = tk.StringVar(value=cfg.get("ffmpeg", shutil.which("ffmpeg") or "ffmpeg"))
        self.v_extra = tk.BooleanVar(value=cfg.get("extra", True))
        self.v_pre_min = tk.IntVar(value=int(cfg.get("pre_min", 5)))
        self.v_post_min = tk.IntVar(value=int(cfg.get("post_min", 5)))
        self.v_ascii = tk.BooleanVar(value=cfg.get("ascii", True))
        nametz = cfg.get("nametz", "radio")
        self.v_nametz = tk.StringVar(value="local" if nametz == "local" else "radio")
        self.v_prefer = tk.StringVar(value=cfg.get("prefer", "radio"))
        self.v_tags = tk.BooleanVar(value=cfg.get("tags", True))
        self.v_keepawake = tk.BooleanVar(value=cfg.get("keepawake", True))
        self.v_logfile = tk.BooleanVar(value=cfg.get("logfile", True))
        self.v_status = tk.StringVar(value="Idle.")
        self.v_recnow = tk.StringVar(value="")
        self.v_hide_reruns = tk.BooleanVar(value=False)
        self.v_only_sel = tk.BooleanVar(value=False)
        self.v_search = tk.StringVar()
        self.v_onair = tk.StringVar(value="On air now: (not checked yet)")
        self.v_tzinfo = tk.StringVar(value="")
        self.v_conv_in = tk.StringVar(value="19:00")
        self.v_conv_dir = tk.StringVar(value="radio2local")
        self.v_conv_out = tk.StringVar(value="")

        self._build_ui()
        self._wire_autosave()
        self.on_station_change()
        self.refresh_grid()
        self.after(200, self.drain_log)
        self.after(1000, self.tick_clocks)
        self.after(1500, self.poll_meta_idle)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        if not tz_db_available():
            self.after(600, self.warn_tzdata)

    # ------------------------------ config ------------------------------

    def load_config(self):
        try:
            with open(config_path(), "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def save_config(self):
        if self._saving:
            return
        data = {
            "version": APP_VERSION,
            "stations": self.stations,
            "station": self.v_station.get(),
            "outdir": self.v_outdir.get(),
            "ffmpeg": self.v_ffmpeg.get(),
            "extra": self.v_extra.get(),
            "pre_min": self.safe_int(self.v_pre_min, 5),
            "post_min": self.safe_int(self.v_post_min, 5),
            "ascii": self.v_ascii.get(),
            "nametz": self.v_nametz.get(),
            "prefer": self.v_prefer.get(),
            "tags": self.v_tags.get(),
            "keepawake": self.v_keepawake.get(),
            "logfile": self.v_logfile.get(),
        }
        self._saving = True
        try:
            path = config_path()
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, path)
        except Exception as exc:
            self.log("Could not save settings: {}".format(exc))
        finally:
            self._saving = False

    def _wire_autosave(self):
        """Persist immediately whenever any setting changes."""
        for var in (self.v_outdir, self.v_ffmpeg, self.v_extra, self.v_pre_min,
                    self.v_post_min, self.v_ascii, self.v_nametz, self.v_prefer,
                    self.v_tags, self.v_keepawake, self.v_logfile, self.v_station):
            var.trace_add("write", lambda *a: self.after_idle(self.save_config))

    @staticmethod
    def safe_int(var, default):
        try:
            return int(var.get())
        except Exception:
            return default

    def warn_tzdata(self):
        messagebox.showwarning(
            APP_NAME,
            "The IANA time zone database was not found, so daylight saving cannot be "
            "calculated properly.\n\n"
            "Fix it once with:\n    pip install tzdata\n\n"
            "Until then RadioSave falls back to fixed UTC offsets, which are wrong for "
            "stations that observe summer time.")

    # ------------------------------ ui ------------------------------

    def _build_ui(self):
        style = ttk.Style(self)
        try:
            style.theme_use("vista" if os.name == "nt" else "clam")
        except tk.TclError:
            pass
        style.configure("Treeview", rowheight=22)

        top = ttk.LabelFrame(self, text="Station")
        top.pack(fill="x", padx=10, pady=(10, 6))
        ttk.Label(top, text="Radio:").grid(row=0, column=0, sticky="w", padx=6, pady=6)
        self.cmb_station = ttk.Combobox(top, textvariable=self.v_station, state="readonly",
                                        values=[s["name"] for s in self.stations], width=26)
        self.cmb_station.grid(row=0, column=1, sticky="w", pady=6)
        self.cmb_station.bind("<<ComboboxSelected>>",
                              lambda e: (self.on_station_change(), self.refresh_grid()))
        ttk.Button(top, text="Add...", width=9, command=self.add_station).grid(row=0, column=2, padx=3)
        ttk.Button(top, text="Edit...", width=9, command=self.edit_station).grid(row=0, column=3, padx=3)
        ttk.Button(top, text="Remove", width=9, command=self.remove_station).grid(row=0, column=4, padx=3)

        ttk.Label(top, text="Stream URL:").grid(row=1, column=0, sticky="w", padx=6)
        ttk.Entry(top, textvariable=self.v_url, width=62).grid(
            row=1, column=1, columnspan=3, sticky="we")
        ttk.Button(top, text="Test 8s", width=9, command=self.test_stream).grid(row=1, column=4, padx=3)

        ttk.Label(top, textvariable=self.v_tzinfo, foreground="#444").grid(
            row=2, column=0, columnspan=5, sticky="w", padx=6, pady=(6, 0))

        onair = ttk.Label(top, textvariable=self.v_onair, foreground="#0a6b0a",
                          font=("Segoe UI", 10, "bold"))
        onair.grid(row=3, column=0, columnspan=4, sticky="w", padx=6, pady=(4, 8))
        ttk.Button(top, text="Refresh", width=9,
                   command=lambda: threading.Thread(target=self._meta_once, daemon=True).start()
                   ).grid(row=3, column=4, padx=3, pady=(4, 8))
        top.columnconfigure(1, weight=1)

        nb = ttk.Notebook(self)
        self.nb = nb
        nb.pack(fill="both", expand=True, padx=10, pady=4)
        self.tab_grid = ttk.Frame(nb)
        self.tab_log = ttk.Frame(nb)
        self.tab_conv = ttk.Frame(nb)
        self.tab_set = ttk.Frame(nb)
        self.tab_about = ttk.Frame(nb)
        nb.add(self.tab_grid, text="  Schedule  ")
        nb.add(self.tab_log, text="  Queue & log  ")
        nb.add(self.tab_conv, text="  Time converter  ")
        nb.add(self.tab_set, text="  Settings  ")
        nb.add(self.tab_about, text="  About  ")

        # A 10x10 blue square and a transparent one of the same size: swapping
        # them blinks the tab without the label jumping around.
        self.img_blue = tk.PhotoImage(width=10, height=10)
        self.img_blue.put("#1a6fd4", to=(0, 0, 10, 10))
        self.img_blank = tk.PhotoImage(width=10, height=10)
        nb.tab(self.tab_log, image=self.img_blank, compound="left")
        nb.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        self._build_grid_tab()
        self._build_log_tab()
        self._build_conv_tab()
        self._build_settings_tab()
        self._build_about_tab()

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=10, pady=(4, 10))
        self.btn_start = ttk.Button(bar, text="Start scheduler", command=self.start_scheduler)
        self.btn_start.pack(side="left")
        self.btn_stop = ttk.Button(bar, text="Stop", command=self.stop_scheduler, state="disabled")
        self.btn_stop.pack(side="left", padx=6)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        self.btn_recnow = ttk.Button(bar, text="Record Now...", command=self.record_now)
        self.btn_recnow.pack(side="left")
        ttk.Label(bar, textvariable=self.v_recnow, foreground="#a00000").pack(side="left", padx=10)
        ttk.Label(bar, textvariable=self.v_status).pack(side="right", padx=14)

    def _build_grid_tab(self):
        f = self.tab_grid
        r1 = ttk.Frame(f)
        r1.pack(fill="x", pady=(8, 2))
        ttk.Button(r1, text="Add...", width=11, command=self.add_entry).pack(side="left", padx=(6, 3))
        ttk.Button(r1, text="Batch add...", width=13, command=self.batch_add).pack(side="left", padx=3)
        ttk.Button(r1, text="Edit...", width=11, command=self.edit_entry).pack(side="left", padx=3)
        ttk.Button(r1, text="Remove", width=11, command=self.remove_entries).pack(side="left", padx=3)
        ttk.Separator(r1, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(r1, text="Select all shown", command=lambda: self.bulk(True)).pack(side="left", padx=3)
        ttk.Button(r1, text="Clear all", command=lambda: self.bulk(False)).pack(side="left", padx=3)

        r2 = ttk.Frame(f)
        r2.pack(fill="x", pady=(2, 6))
        ttk.Label(r2, text="Find:").pack(side="left", padx=(6, 4))
        e = ttk.Entry(r2, textvariable=self.v_search, width=28)
        e.pack(side="left")
        e.bind("<KeyRelease>", lambda ev: self.refresh_grid())
        ttk.Checkbutton(r2, text="Hide reruns", variable=self.v_hide_reruns,
                        command=self.refresh_grid).pack(side="left", padx=10)
        ttk.Checkbutton(r2, text="Only ticked", variable=self.v_only_sel,
                        command=self.refresh_grid).pack(side="left", padx=4)
        ttk.Label(r2, text="(click the first column to tick / untick, "
                           "double-click or right-click a row to edit)",
                  foreground="#666").pack(side="left", padx=10)

        cols = ("chk", "day", "rstart", "rend", "lstart", "dur", "prog")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", selectmode="extended")
        for c, txt, w, anc in (
                ("chk", "", 32, "center"), ("day", "Day", 92, "w"),
                ("rstart", "Start - Radio Time", 128, "center"),
                ("rend", "End - Radio Time", 122, "center"),
                ("lstart", "Start - Your Time", 128, "center"),
                ("dur", "Min", 48, "center"), ("prog", "Program", 430, "w")):
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w, anchor=anc, stretch=(c == "prog"))
        self.tree.tag_configure("onair", background="#bff0bf")
        self.tree.tag_configure("auto", foreground="#0645ad")

        vs = ttk.Scrollbar(f, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        vs.pack(side="right", fill="y", pady=6, padx=(0, 6))
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<Double-1>", lambda ev: self.edit_entry())
        self.tree.bind("<Button-3>", self.on_tree_right)
        self.tree.bind("<Delete>", lambda ev: self.remove_entries())

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Edit...", command=self.edit_entry)
        self.menu.add_command(label="Toggle tick", command=self.toggle_selected_rows)
        self.menu.add_separator()
        self.menu.add_command(label="Remove", command=self.remove_entries)

    def _build_conv_tab(self):
        f = self.tab_conv
        box = ttk.LabelFrame(f, text="Live clocks")
        box.pack(fill="x", padx=10, pady=12)
        self.lbl_radio = ttk.Label(box, text="", font=("Segoe UI", 11))
        self.lbl_radio.pack(anchor="w", padx=10, pady=(8, 2))
        self.lbl_loc = ttk.Label(box, text="", font=("Segoe UI", 11))
        self.lbl_loc.pack(anchor="w", padx=10, pady=(0, 8))

        c = ttk.LabelFrame(f, text="Convert a time")
        c.pack(fill="x", padx=10, pady=6)
        self.rb_r2l = ttk.Radiobutton(c, text="Radio -> my time", value="radio2local",
                                      variable=self.v_conv_dir, command=self.do_convert)
        self.rb_r2l.grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.rb_l2r = ttk.Radiobutton(c, text="My time -> radio", value="local2radio",
                                      variable=self.v_conv_dir, command=self.do_convert)
        self.rb_l2r.grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(c, text="Time (HH:MM):").grid(row=1, column=0, sticky="e", padx=8, pady=8)
        ce = ttk.Entry(c, textvariable=self.v_conv_in, width=10)
        ce.grid(row=1, column=1, sticky="w")
        ce.bind("<KeyRelease>", lambda ev: self.do_convert())
        ttk.Label(c, textvariable=self.v_conv_out, font=("Segoe UI", 11, "bold")).grid(
            row=1, column=2, sticky="w", padx=16)

        self.lbl_convnote = ttk.Label(f, text="", foreground="#555")
        self.lbl_convnote.pack(anchor="w", padx=14, pady=10)
        self.do_convert()

    def _build_log_tab(self):
        f = self.tab_log
        head = ttk.Frame(f)
        head.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(head, text="Upcoming recordings").pack(side="left")
        ttk.Button(head, text="Remove selected entry", command=self.remove_from_queue).pack(side="right")
        self.lst_queue = tk.Listbox(f, height=9, selectmode="extended")
        self.lst_queue.pack(fill="x", padx=8)
        ttk.Label(f, text="Log").pack(anchor="w", padx=8, pady=(10, 2))
        self.txt_log = tk.Text(f, height=13, wrap="word", state="disabled")
        self.txt_log.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _build_settings_tab(self):
        f = self.tab_set
        canvas = tk.Canvas(f, highlightthickness=0)
        sb = ttk.Scrollbar(f, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        g = ttk.LabelFrame(inner, text="Output")
        g.pack(fill="x", padx=10, pady=10)
        ttk.Label(g, text="Save folder:").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        ttk.Entry(g, textvariable=self.v_outdir, width=58).grid(row=0, column=1, sticky="we")
        ttk.Button(g, text="Browse...", command=self.pick_outdir).grid(row=0, column=2, padx=6)
        ttk.Label(g, text="ffmpeg:").grid(row=1, column=0, sticky="w", padx=8, pady=(0, 8))
        ttk.Entry(g, textvariable=self.v_ffmpeg, width=58).grid(row=1, column=1, sticky="we", pady=(0, 8))
        ttk.Button(g, text="Browse...", command=self.pick_ffmpeg).grid(row=1, column=2, padx=6, pady=(0, 8))
        g.columnconfigure(1, weight=1)

        p = ttk.LabelFrame(inner, text="Recording padding")
        p.pack(fill="x", padx=10, pady=6)
        ttk.Checkbutton(p, text="Record extra minutes (programmes often overrun)",
                        variable=self.v_extra, command=self._toggle_extra).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=8, pady=(8, 4))
        ttk.Label(p, text="Minutes before the start:").grid(row=1, column=0, sticky="w", padx=24, pady=3)
        self.sp_pre = ttk.Spinbox(p, from_=0, to=60, textvariable=self.v_pre_min, width=6)
        self.sp_pre.grid(row=1, column=1, sticky="w")
        ttk.Label(p, text="Minutes after the end:").grid(row=2, column=0, sticky="w", padx=24, pady=3)
        self.sp_post = ttk.Spinbox(p, from_=0, to=60, textvariable=self.v_post_min, width=6)
        self.sp_post.grid(row=2, column=1, sticky="w")
        ttk.Label(p, text="A 1h programme with 5 + 5 is recorded for 1h10. "
                          "The file name still shows the scheduled hours.",
                  foreground="#555").grid(row=3, column=0, columnspan=3,
                                          sticky="w", padx=24, pady=(4, 8))

        n = ttk.LabelFrame(inner, text="Filenames")
        n.pack(fill="x", padx=10, pady=6)
        ttk.Label(n, text="Pattern:  YYYY-MM-DD-HHh-HHh - PROGRAM NAME.mp3").grid(
            row=0, column=0, columnspan=3, sticky="w", padx=8, pady=(8, 4))
        ttk.Label(n, text="Name comes from:").grid(row=1, column=0, sticky="w", padx=8, pady=3)
        ttk.Radiobutton(n, text="What the radio reported (schedule as fallback)", value="radio",
                        variable=self.v_prefer).grid(row=1, column=1, sticky="w")
        ttk.Radiobutton(n, text="The schedule (radio as fallback)", value="grid",
                        variable=self.v_prefer).grid(row=2, column=1, sticky="w")
        ttk.Label(n, text="Times in filename:").grid(row=3, column=0, sticky="w", padx=8, pady=3)
        ttk.Radiobutton(n, text="Radio station time", value="radio",
                        variable=self.v_nametz).grid(row=3, column=1, sticky="w")
        ttk.Radiobutton(n, text="My local time", value="local",
                        variable=self.v_nametz).grid(row=4, column=1, sticky="w")
        ttk.Checkbutton(n, text="Strip accents", variable=self.v_ascii).grid(
            row=5, column=0, columnspan=2, sticky="w", padx=8, pady=(4, 8))

        x = ttk.LabelFrame(inner, text="Extras")
        x.pack(fill="x", padx=10, pady=6)
        ttk.Checkbutton(x, text="Write ID3 tags into finished files (title, station, date)",
                        variable=self.v_tags).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 3))
        ttk.Checkbutton(x, text="Keep this computer awake while a recording is running",
                        variable=self.v_keepawake).grid(row=1, column=0, sticky="w", padx=8, pady=3)
        ttk.Checkbutton(x, text="Also write the log to radiosave.log in the save folder",
                        variable=self.v_logfile).grid(row=2, column=0, sticky="w", padx=8, pady=(3, 8))

        ttk.Label(inner, text="Settings are written to disk the moment you change them.",
                  foreground="#555").pack(anchor="w", padx=14, pady=8)
        self._toggle_extra()

    def _build_about_tab(self):
        f = ttk.Frame(self.tab_about, padding=20)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text=APP_NAME, font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(f, text="Version {}".format(APP_VERSION),
                  font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 12))
        ttk.Label(f, text="Records internet radio to MP3 on a schedule, or on demand,\n"
                          "and names each file after what the station says is on air.",
                  foreground="#444").pack(anchor="w", pady=(0, 16))

        grid = ttk.Frame(f)
        grid.pack(anchor="w", pady=(0, 16))
        rows = [("Author", APP_AUTHOR), ("Contact", APP_CONTACT)]
        for i, (k, v) in enumerate(rows):
            ttk.Label(grid, text=k + ":", font=("Segoe UI", 10, "bold"), width=10).grid(
                row=i, column=0, sticky="w", pady=2)
            ttk.Label(grid, text=v).grid(row=i, column=1, sticky="w", pady=2)

        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=10)
        self.lbl_env = ttk.Label(f, text="", foreground="#444", justify="left")
        self.lbl_env.pack(anchor="w")
        ttk.Button(f, text="Re-check components", command=self.refresh_about).pack(
            anchor="w", pady=12)
        self.refresh_about()

    def refresh_about(self):
        ff = self.v_ffmpeg.get()
        ff_ok = shutil.which(ff) or (os.path.exists(ff) and ff)
        ver = "not found - set the path on Settings"
        if ff_ok:
            try:
                p = subprocess.run([ff, "-version"], capture_output=True, text=True,
                                   timeout=15, **no_window_kwargs())
                ver = (p.stdout or "").splitlines()[0] if p.stdout else str(ff_ok)
            except Exception:
                ver = str(ff_ok)
        self.lbl_env.config(text=(
            "Python      {}\n"
            "Tk          {}\n"
            "ffmpeg      {}\n"
            "Time zones  {}\n"
            "Settings    {}").format(
            sys.version.split()[0], self.tk.call("info", "patchlevel"), ver,
            "IANA database loaded" if tz_db_available()
            else "NOT available - run: pip install tzdata",
            config_path()))

    def _toggle_extra(self):
        state = "normal" if self.v_extra.get() else "disabled"
        self.sp_pre.config(state=state)
        self.sp_post.config(state=state)

    # --------------------------- tab blink ---------------------------

    def on_tab_changed(self, _event=None):
        try:
            if self.nb.select() == str(self.tab_log):
                self.stop_blink()
        except Exception:
            pass

    def flash_queue(self):
        """Draw the eye to the Queue & log tab. Safe to call repeatedly."""
        try:
            if self.nb.select() == str(self.tab_log):
                return
        except Exception:
            return
        self._blink_until = _time.monotonic() + BLINK_MAX_SEC
        if not self._blinking:
            self._blinking = True
            self._blink_step()

    def stop_blink(self):
        self._blinking = False
        self._blink_on = False
        try:
            self.nb.tab(self.tab_log, image=self.img_blank)
        except Exception:
            pass

    def _blink_step(self):
        if not self._blinking:
            return
        try:
            if self.nb.select() == str(self.tab_log) or _time.monotonic() > self._blink_until:
                self.stop_blink()
                return
            self._blink_on = not self._blink_on
            self.nb.tab(self.tab_log, image=self.img_blue if self._blink_on else self.img_blank)
            self.after(BLINK_INTERVAL_MS, self._blink_step)
        except Exception:
            self._blinking = False

    # --------------------------- stations ---------------------------

    def station(self):
        for s in self.stations:
            if s["name"] == self.v_station.get():
                return s
        return self.stations[0]

    def tz(self):
        return get_tz(self.station().get("tz"))

    def now_station(self):
        return datetime.now(self.tz())

    def entries(self):
        return self.station().setdefault("entries", [])

    def padding(self):
        if not self.v_extra.get():
            return 0, 0
        return max(0, self.safe_int(self.v_pre_min, 5)), max(0, self.safe_int(self.v_post_min, 5))

    def on_station_change(self):
        st = self.station()
        self.v_url.set(st.get("url", ""))
        tz = self.tz()
        self.v_tzinfo.set("Radio time zone: {}  -  {}   |   now {} there, {} here".format(
            st.get("tz", DEFAULT_TZ), offset_label(tz),
            datetime.now(tz).strftime("%H:%M"), datetime.now().strftime("%H:%M")))
        self.live_title = ""
        self.v_onair.set("On air now: (checking...)")
        threading.Thread(target=self._meta_once, daemon=True).start()
        self.do_convert()

    def add_station(self):
        d = StationDialog(self)
        if not d.result:
            return
        if any(s["name"] == d.result["name"] for s in self.stations):
            messagebox.showwarning(APP_NAME, "A station with that name already exists.")
            return
        d.result["entries"] = []
        self.stations.append(d.result)
        self.cmb_station["values"] = [s["name"] for s in self.stations]
        self.v_station.set(d.result["name"])
        self.on_station_change()
        self.refresh_grid()
        self.save_config()

    def edit_station(self):
        cur = self.station()
        old_tz = cur.get("tz", DEFAULT_TZ)
        d = StationDialog(self, cur)
        if not d.result:
            return
        cur.update(d.result)
        if d.result["tz"] != old_tz and cur.get("entries"):
            if messagebox.askyesno(
                    APP_NAME,
                    "The time zone changed from {} to {}.\n\n"
                    "Shift the {} existing entries so they keep the same absolute moment?\n\n"
                    "Yes  = 19:00 {} becomes the matching hour in {}\n"
                    "No   = the stored hours stay as typed (19:00 stays 19:00)".format(
                        old_tz, d.result["tz"], len(cur["entries"]), old_tz, d.result["tz"])):
                self.shift_entries(cur, old_tz, d.result["tz"])
        self.cmb_station["values"] = [s["name"] for s in self.stations]
        self.v_station.set(cur["name"])
        self.on_station_change()
        self.refresh_grid()
        self.save_config()

    def shift_entries(self, station, old_tzname, new_tzname):
        old_tz, new_tz = get_tz(old_tzname), get_tz(new_tzname)
        ref = datetime.now().replace(second=0, microsecond=0)
        moved = 0
        for e in station.get("entries", []):
            hm = parse_hhmm(e.get("start", ""))
            if not hm:
                continue
            target_py = GRID_TO_PYWD[e["day"]]
            naive = ref.replace(hour=hm[0], minute=hm[1])
            naive += timedelta(days=(target_py - ref.weekday()) % 7)
            new = naive.replace(tzinfo=old_tz).astimezone(new_tz)
            e["day"] = PYWD_TO_GRID[new.weekday()]
            e["start"] = new.strftime("%H:%M")
            moved += 1
        self.log("Shifted {} entries from {} to {}.".format(moved, old_tzname, new_tzname))

    def remove_station(self):
        if len(self.stations) <= 1:
            messagebox.showinfo(APP_NAME, "Keep at least one station.")
            return
        cur = self.station()
        if not messagebox.askyesno(APP_NAME, "Remove '{}' and its {} schedule entries?".format(
                cur["name"], len(cur.get("entries", [])))):
            return
        self.stations.remove(cur)
        self.cmb_station["values"] = [s["name"] for s in self.stations]
        self.v_station.set(self.stations[0]["name"])
        self.on_station_change()
        self.refresh_grid()
        self.save_config()

    # --------------------------- entries ---------------------------

    def find_entry(self, eid):
        for e in self.entries():
            if e["id"] == eid:
                return e
        return None

    def selected_entries(self):
        return [self.find_entry(self.row_entry[i]) for i in self.tree.selection()
                if i in self.row_entry]

    def add_entry(self):
        d = EntryDialog(self, self.tz())
        if d.result:
            self.entries().append(d.result)
            self.refresh_grid()
            self.save_config()
            self.log("Added entry: {} {} ({} min) - {}".format(
                DAYS_PT[d.result["day"]], d.result["start"], d.result["dur"],
                d.result["prog"] or "<name from radio>"))
            self.flash_queue()

    def batch_add(self):
        d = BatchDialog(self, self.tz())
        if d.result:
            self.entries().extend(d.result)
            self.refresh_grid()
            self.save_config()
            self.log("Batch added {} entries.".format(len(d.result)))
            self.flash_queue()

    def edit_entry(self):
        sel = self.selected_entries()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select a row first.")
            return
        if len(sel) > 1:
            messagebox.showinfo(APP_NAME, "Select a single row to edit.")
            return
        old = sel[0]
        d = EntryDialog(self, self.tz(), old)
        if d.result:
            keep_id, keep_sel = old["id"], old.get("sel", False)
            old.update(d.result)
            old["id"], old["sel"] = keep_id, keep_sel
            self.refresh_grid()
            self.save_config()

    def remove_entries(self):
        sel = self.selected_entries()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select one or more rows first.")
            return
        if not messagebox.askyesno(APP_NAME, "Remove {} entr{}?".format(
                len(sel), "y" if len(sel) == 1 else "ies")):
            return
        ids = {e["id"] for e in sel}
        self.station()["entries"] = [e for e in self.entries() if e["id"] not in ids]
        self.refresh_grid()
        self.save_config()
        self.log("Removed {} entr{}.".format(len(ids), "y" if len(ids) == 1 else "ies"))

    def toggle_selected_rows(self):
        for e in self.selected_entries():
            e["sel"] = not e.get("sel", False)
        self.refresh_grid()
        self.save_config()
        self.flash_queue()

    def bulk(self, on):
        shown = {self.row_entry[i] for i in self.tree.get_children() if i in self.row_entry}
        for e in self.entries():
            if on:
                if e["id"] in shown:
                    e["sel"] = True
            else:
                e["sel"] = False
        self.refresh_grid()
        self.save_config()
        self.flash_queue()

    def on_tree_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#1":
            return
        iid = self.tree.identify_row(event.y)
        e = self.find_entry(self.row_entry.get(iid, ""))
        if e:
            e["sel"] = not e.get("sel", False)
            self.refresh_grid()
            self.save_config()
            self.flash_queue()
            return "break"

    def on_tree_right(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            if iid not in self.tree.selection():
                self.tree.selection_set(iid)
            self.menu.tk_popup(event.x_root, event.y_root)

    def refresh_grid(self):
        keep = {self.row_entry[i] for i in self.tree.selection() if i in self.row_entry}
        self.tree.delete(*self.tree.get_children())
        self.row_entry.clear()
        needle = self.v_search.get().strip().lower()
        tz = self.tz()
        now_st = datetime.now(tz)

        def sortkey(e):
            hm = parse_hhmm(e["start"]) or (0, 0)
            return (e["day"], hm[0], hm[1])

        restore = []
        for e in sorted(self.entries(), key=sortkey):
            label = e.get("prog") or "<name from radio>"
            if self.v_hide_reruns.get() and is_rerun(e.get("prog", "")):
                continue
            if self.v_only_sel.get() and not e.get("sel"):
                continue
            if needle and needle not in label.lower():
                continue
            hh, mm = parse_hhmm(e["start"]) or (0, 0)
            nxt = next_occurrence(e["day"], hh, mm, now_st, tz)
            end = nxt + timedelta(minutes=int(e.get("dur", 60)))
            loc = to_local(nxt)
            tags = []
            if entry_is_on_air(e, now_st, tz):
                tags.append("onair")
            if e.get("auto"):
                tags.append("auto")
            iid = self.tree.insert("", "end", values=(
                "X" if e.get("sel") else "",
                "{} / {}".format(DAYS_PT[e["day"]], DAYS_EN[e["day"]][:3]),
                nxt.strftime("%H:%M"), end.strftime("%H:%M"),
                "{} {}".format(DAYS_EN[(loc.weekday() + 1) % 7][:3], loc.strftime("%H:%M")),
                int(e.get("dur", 60)), label,
            ), tags=tuple(tags))
            self.row_entry[iid] = e["id"]
            if e["id"] in keep:
                restore.append(iid)
        if restore:
            self.tree.selection_set(restore)
        self.update_queue_view()

    def update_queue_view(self):
        self.lst_queue.delete(0, "end")
        self.queue_rows = []
        tz = self.tz()
        now_st = datetime.now(tz)
        pre_m, post_m = self.padding()
        rows = []
        for e in self.entries():
            if not e.get("sel"):
                continue
            rows.append((entry_next_start(e, now_st, tz), e))
        for start, e in sorted(rows, key=lambda x: x[0])[:80]:
            loc = to_local(start)
            dur = int(e.get("dur", 60))
            self.lst_queue.insert("end", "{}   (your time {})   {} min{}   {}".format(
                start.strftime("%a %Y-%m-%d %H:%M"), loc.strftime("%a %d %H:%M"), dur,
                "" if (pre_m + post_m) == 0 else " +{}".format(pre_m + post_m),
                e.get("prog") or "<name from radio>"))
            self.queue_rows.append(e["id"])
        self.v_status.set("{} entr{} ticked for recording.".format(
            len(rows), "y" if len(rows) == 1 else "ies"))

    def remove_from_queue(self):
        idxs = list(self.lst_queue.curselection())
        if not idxs:
            messagebox.showinfo(APP_NAME, "Select an upcoming recording first.")
            return
        ids = {self.queue_rows[i] for i in idxs if i < len(self.queue_rows)}
        if not ids:
            return
        if not messagebox.askyesno(APP_NAME, "Delete {} schedule entr{}?".format(
                len(ids), "y" if len(ids) == 1 else "ies")):
            return
        self.station()["entries"] = [e for e in self.entries() if e["id"] not in ids]
        self.refresh_grid()
        self.save_config()
        self.log("Deleted {} entr{} from the schedule.".format(
            len(ids), "y" if len(ids) == 1 else "ies"))

    # --------------------------- metadata ---------------------------

    def _meta_once(self):
        st = self.station()
        title = fetch_station_title(st)
        self.live_title = title
        self.live_checked = datetime.now()
        stamp = self.live_checked.strftime("%H:%M:%S")
        if st.get("meta_mode", "off") == "off":
            self.v_onair.set("On air now: (metadata turned off for this station)")
        elif title:
            self.v_onair.set("On air now: {}    (checked {})".format(title, stamp))
        else:
            self.v_onair.set("On air now: (no title reported)    (checked {})".format(stamp))

    def poll_meta_idle(self):
        threading.Thread(target=self._meta_once, daemon=True).start()
        self.refresh_grid()
        self.after(META_IDLE_SEC * 1000, self.poll_meta_idle)

    # --------------------------- converter ---------------------------

    def do_convert(self):
        st = self.station()
        tzname = st.get("tz", DEFAULT_TZ)
        tz = get_tz(tzname)
        try:
            self.rb_r2l.config(text="{} -> my time".format(st.get("name", "Radio")))
            self.rb_l2r.config(text="My time -> {}".format(st.get("name", "Radio")))
            self.lbl_convnote.config(text=(
                "Radio time zone for {}: {} ({}). Daylight saving is applied automatically "
                "from the IANA time zone database.\nYour own zone comes from the operating "
                "system and is DST-aware too.".format(
                    st.get("name", ""), tzname, offset_label(tz))))
        except (tk.TclError, AttributeError):
            pass

        hm = parse_hhmm(self.v_conv_in.get())
        if not hm:
            self.v_conv_out.set("--:--")
            return
        hh, mm = hm
        base = datetime.now().replace(second=0, microsecond=0)
        if self.v_conv_dir.get() == "radio2local":
            src = base.replace(hour=hh, minute=mm, tzinfo=tz)
            dst = src.astimezone()
            label = "= {} your time".format(dst.strftime("%H:%M"))
        else:
            src = base.replace(hour=hh, minute=mm).astimezone()
            dst = src.astimezone(tz)
            label = "= {} radio time".format(dst.strftime("%H:%M"))
        if dst.date() > src.date():
            label += "  (next day)"
        elif dst.date() < src.date():
            label += "  (previous day)"
        self.v_conv_out.set(label)

    def tick_clocks(self):
        st = self.station()
        tz = self.tz()
        self.lbl_radio.config(text="{}:   {}   [{}]".format(
            st.get("name", "Radio"), datetime.now(tz).strftime("%a %d %b %Y  %H:%M:%S"),
            offset_label(tz)))
        loc = datetime.now().astimezone()
        self.lbl_loc.config(text="Your time:  {}   [{}]".format(
            loc.strftime("%a %d %b %Y  %H:%M:%S"), local_tz_label()))
        self.after(1000, self.tick_clocks)

    # --------------------------- misc ---------------------------

    def pick_outdir(self):
        d = filedialog.askdirectory(initialdir=self.v_outdir.get() or os.path.expanduser("~"))
        if d:
            self.v_outdir.set(d)

    def pick_ffmpeg(self):
        f = filedialog.askopenfilename(title="Locate ffmpeg.exe",
                                       filetypes=[("ffmpeg", "ffmpeg.exe"), ("All files", "*.*")])
        if f:
            self.v_ffmpeg.set(f)

    def log(self, msg):
        self.log_q.put("[{}] {}".format(datetime.now().strftime("%H:%M:%S"), msg))

    def write_log_file(self, lines):
        if not self.v_logfile.get():
            return
        try:
            folder = self.v_outdir.get()
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, "radiosave.log")
            if os.path.exists(path) and os.path.getsize(path) > LOG_MAX_BYTES:
                old = path + ".1"
                if os.path.exists(old):
                    os.remove(old)
                os.replace(path, old)
            day = datetime.now().strftime("%Y-%m-%d ")
            with open(path, "a", encoding="utf-8") as fh:
                for line in lines:
                    fh.write(day + line + "\n")
        except Exception:
            pass

    def drain_log(self):
        lines = []
        try:
            while True:
                lines.append(self.log_q.get_nowait())
        except queue.Empty:
            pass
        if lines:
            self.txt_log.config(state="normal")
            for line in lines:
                self.txt_log.insert("end", line + "\n")
            self.txt_log.see("end")
            self.txt_log.config(state="disabled")
            self.write_log_file(lines)
        self.after(250, self.drain_log)

    def test_stream(self):
        url = self.v_url.get().strip()
        if not url:
            messagebox.showwarning(APP_NAME, "Enter a stream URL first.")
            return
        os.makedirs(self.v_outdir.get(), exist_ok=True)
        out = os.path.join(self.v_outdir.get(), "_streamtest.mp3")

        def run():
            self.log("Testing stream for 8 seconds...")
            try:
                p = subprocess.run(
                    ffmpeg_command(self.v_ffmpeg.get(), url, 8, out, interactive=False),
                    capture_output=True, text=True, timeout=90, **no_window_kwargs())
                size = os.path.getsize(out) if os.path.exists(out) else 0
                if size > 5000:
                    self.log("Stream OK - captured {} KB.".format(size // 1024))
                else:
                    self.log("Test captured almost nothing. ffmpeg: {}".format(
                        (p.stderr or "").strip()[:400] or "(no output)"))
            except FileNotFoundError:
                self.log("ffmpeg not found. Set its path on the Settings tab.")
            except Exception as exc:
                self.log("Test failed: {}".format(exc))

        threading.Thread(target=run, daemon=True).start()

    # --------------------------- awake / activity ---------------------------

    def _apply_awake(self):
        """Runs on the Tk main thread so the execution state sticks."""
        if self.awake_holds > 0 and self.v_keepawake.get():
            _set_execution_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED)
        else:
            _set_execution_state(ES_CONTINUOUS)

    def capture_started(self, cap):
        with self.active_lock:
            self.captures.append(cap)
            self.awake_holds += 1
            n = len(self.captures)
        self.after(0, self._apply_awake)
        self.ui(self.flash_queue)
        if n > 1:
            self.log("Note: {} recordings are running at the same time "
                     "({} connections to the station).".format(n, n))

    def capture_finished(self, cap):
        with self.active_lock:
            if cap in self.captures:
                self.captures.remove(cap)
            self.awake_holds = max(0, self.awake_holds - 1)
        self.after(0, self._apply_awake)

    def live_captures(self, source=None):
        with self.active_lock:
            return [c for c in self.captures
                    if source is None or c.get("source") == source]

    def stop_captures(self, source=None, reason="stopped"):
        """Ask the running ffmpeg processes to close their files cleanly."""
        caps = self.live_captures(source)
        if not caps:
            return 0
        self.log("Finishing {} recording{} in progress ({})...".format(
            len(caps), "" if len(caps) == 1 else "s", reason))
        for cap in caps:
            cap["early"] = True
        threads = []
        for cap in caps:
            t = threading.Thread(target=self._stop_one, args=(cap,), daemon=True)
            t.start()
            threads.append(t)
        return len(caps)

    def _stop_one(self, cap):
        # A capture may have been registered a moment before ffmpeg started.
        deadline = _time.monotonic() + 3
        while cap.get("proc") is None and _time.monotonic() < deadline:
            _time.sleep(0.1)
        how = graceful_stop(cap.get("proc"))
        if how == "clean":
            self.log("Saved partial file for '{}'.".format(cap.get("label") or "recording"))
        elif how in ("terminated", "killed"):
            self.log("ffmpeg did not respond to the stop request for '{}' ({}); "
                     "the file may end abruptly.".format(cap.get("label") or "recording", how))

    # --------------------------- scheduler ---------------------------

    def preflight(self):
        if not self.v_url.get().strip():
            messagebox.showwarning(APP_NAME, "This station has no stream URL.")
            return False
        if not shutil.which(self.v_ffmpeg.get()) and not os.path.exists(self.v_ffmpeg.get()):
            messagebox.showwarning(APP_NAME, "ffmpeg was not found.\nSet the path on Settings.")
            return False
        try:
            os.makedirs(self.v_outdir.get(), exist_ok=True)
        except Exception as exc:
            messagebox.showerror(APP_NAME, "Cannot create the save folder:\n{}".format(exc))
            return False
        self.station()["url"] = self.v_url.get().strip()
        return True

    def start_scheduler(self):
        if not any(e.get("sel") for e in self.entries()):
            messagebox.showinfo(APP_NAME, "Tick at least one entry on the Schedule tab.")
            return
        if not self.preflight():
            return
        self.stop_event.clear()
        self.scheduler_thread = threading.Thread(target=self.scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        pre_m, post_m = self.padding()
        self.log("Scheduler started (padding {} min before / {} min after). "
                 "You can minimise this window.".format(pre_m, post_m))
        self.save_config()

    def stop_scheduler(self):
        self.stop_event.set()
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        n = self.stop_captures("Schedule", "scheduler stopped")
        self.log("Scheduler stopped.{}".format(
            "" if not n else " Whatever was captured is being saved."))
        self.flash_queue()

    def scheduler_loop(self):
        fired = set()
        grace = timedelta(minutes=GRACE_MINUTES)
        while not self.stop_event.is_set():
            st = self.station()
            tz = get_tz(st.get("tz"))
            now_st = datetime.now(tz)
            pre_m, post_m = self.padding()
            for e in list(self.entries()):
                if not e.get("sel"):
                    continue
                start = entry_next_start(e, now_st - grace - timedelta(minutes=pre_m), tz)
                launch = start - timedelta(minutes=pre_m)
                stamp = "{}@{}".format(e["id"], start.isoformat())
                if stamp in fired:
                    continue
                if launch <= now_st < start + grace:
                    fired.add(stamp)
                    dur = int(e.get("dur", 60))
                    self.spawn_capture(st, start, start + timedelta(minutes=dur),
                                       e.get("prog") or "", bool(e.get("auto")), "Schedule")
            cutoff = now_st - timedelta(hours=6)
            keep = set()
            for s in fired:
                try:
                    if datetime.fromisoformat(s.split("@", 1)[1]) > cutoff:
                        keep.add(s)
                except Exception:
                    pass
            fired = keep
            self.stop_event.wait(2.0)

    # --------------------------- record now ---------------------------

    def record_now(self):
        if self.recnow_thread and self.recnow_thread.is_alive():
            self.stop_record_now()
            return
        if not self.preflight():
            return
        pre_m, post_m = self.padding()
        d = RecordNowDialog(self, self.station(), pre_m, post_m)
        if not d.result:
            return
        self.recnow_stop.clear()
        self.recnow_thread = threading.Thread(
            target=self.recnow_loop, args=(dict(self.station()), d.result), daemon=True)
        self.recnow_thread.start()
        self.btn_recnow.config(text="Stop Record Now")
        self.log("Record Now started: {} min per file, first cut {}.".format(
            d.result["chunk"], d.result["first_cut"].strftime("%H:%M")))

    def ui(self, fn, *args):
        """Run a Tk call on the main thread from a worker thread."""
        try:
            self.after(0, lambda: fn(*args))
        except Exception:
            pass

    def stop_record_now(self):
        self.recnow_stop.set()
        self.btn_recnow.config(text="Record Now...")
        self.v_recnow.set("")
        n = self.stop_captures("Record Now", "Record Now stopped")
        self.log("Record Now stopped.{}".format(
            "" if not n else " The file in progress is being closed and kept, "
                             "marked {}.".format(INCOMPLETE_MARK)))
        self.flash_queue()

    def recnow_loop(self, station, opts):
        tz = get_tz(station.get("tz"))
        chunk = int(opts["chunk"])
        cut = opts["first_cut"]
        seg_start = datetime.now(tz)
        idx = 0
        while not self.recnow_stop.is_set() and not self.quit_event.is_set():
            pre_m, post_m = self.padding()
            launch = seg_start if idx == 0 else seg_start - timedelta(minutes=pre_m)
            wait = (launch - datetime.now(tz)).total_seconds()
            if wait > 0:
                self.ui(self.v_recnow.set, "Record Now: next file starts {}".format(
                    launch.strftime("%H:%M")))
                if self.recnow_stop.wait(wait):
                    break
            if self.recnow_stop.is_set():
                break
            self.ui(self.v_recnow.set, "Record Now: capturing {} -> {}".format(
                seg_start.strftime("%H:%M"), cut.strftime("%H:%M")))
            self.spawn_capture(station, seg_start, cut, opts["prog"], opts["auto"],
                               "Record Now", from_now=(idx == 0))
            seg_start, cut = cut, cut + timedelta(minutes=chunk)
            idx += 1
        self.ui(self.v_recnow.set, "")
        self.ui(self.btn_recnow.config, {"text": "Record Now..."})

    # --------------------------- capture ---------------------------

    def spawn_capture(self, station, nom_start, nom_end, sched_name, auto,
                      source="Schedule", from_now=False):
        """Record one file covering nom_start..nom_end plus the padding minutes."""
        st = dict(station)
        tz = get_tz(st.get("tz"))
        pre_m, post_m = self.padding()
        now = datetime.now(tz)
        seconds = (nom_end - now).total_seconds() + post_m * 60
        if seconds <= 5:
            self.log("Skipped '{}' - its slot has already ended.".format(sched_name or "?"))
            return

        if self.v_nametz.get() == "local":
            n_start, n_end = to_local(nom_start), to_local(nom_end)
        else:
            n_start, n_end = nom_start, nom_end

        provisional = sched_name or "RECORDING"
        outpath = self.unique_path(build_filename(n_start, n_end, provisional, self.v_ascii.get()))
        cmd = ffmpeg_command(self.v_ffmpeg.get(), st.get("url", ""), seconds, outpath)
        samples = []
        stop_sampling = threading.Event()
        dur_min = int(round((nom_end - nom_start).total_seconds() / 60.0))
        label = sched_name or os.path.basename(outpath)
        cap = {"proc": None, "source": source, "early": False, "label": label,
               "started": datetime.now(tz), "tz": tz}

        def sampler():
            while not stop_sampling.is_set():
                t = fetch_station_title(st)
                if t:
                    samples.append(t)
                stop_sampling.wait(META_SAMPLE_SEC)

        def run():
            self.capture_started(cap)
            self.log("RECORDING [{}]  {}  {} min +{} pad  -> {}".format(
                source, sched_name or "<name from radio>", dur_min,
                (0 if from_now else pre_m) + post_m, os.path.basename(outpath)))
            if st.get("meta_mode", "off") != "off":
                threading.Thread(target=sampler, daemon=True).start()
            err_lines = []
            try:
                p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.PIPE, text=True, bufsize=1,
                                     **no_window_kwargs())
                cap["proc"] = p

                def drain_err():
                    try:
                        for line in p.stderr:
                            err_lines.append(line)
                    except Exception:
                        pass

                threading.Thread(target=drain_err, daemon=True).start()
                p.wait()
                try:
                    if p.stdin and not p.stdin.closed:
                        p.stdin.close()
                except Exception:
                    pass
            except FileNotFoundError:
                self.log("ffmpeg not found - recording aborted.")
                stop_sampling.set()
                self.capture_finished(cap)
                return
            except Exception as exc:
                self.log("Recording error: {}".format(exc))
                stop_sampling.set()
                self.capture_finished(cap)
                return
            stop_sampling.set()
            err = "".join(err_lines[-12:])
            cut_short = bool(cap.get("early"))
            stopped_at = datetime.now(tz)

            radio_name = pick_dominant(samples)
            if samples:
                self.log("Radio reported '{}' in {} of {} samples ({} distinct).".format(
                    radio_name, samples.count(radio_name), len(samples), len(set(samples))))

            final = decide_name(self.v_prefer.get(), radio_name, sched_name, auto)
            file_name = final + " " + INCOMPLETE_MARK if cut_short else final

            path = outpath
            wanted = build_filename(n_start, n_end, file_name, self.v_ascii.get())
            if os.path.basename(outpath) != wanted and os.path.exists(outpath):
                target = self.unique_path(wanted)
                try:
                    os.replace(outpath, target)
                    path = target
                    self.log("Renamed to: {}".format(os.path.basename(target)))
                except Exception as exc:
                    self.log("Could not rename ({}). Kept {}".format(exc, os.path.basename(outpath)))

            if self.v_tags.get():
                note = "{} {} - {} ({})".format(
                    n_start.strftime("%Y-%m-%d"), n_start.strftime("%H:%M"),
                    n_end.strftime("%H:%M"), source)
                if cut_short:
                    note += " INCOMPLETE - stopped at {}".format(stopped_at.strftime("%H:%M"))
                ok, terr = tag_mp3(
                    self.v_ffmpeg.get(), path, file_name, st.get("name", APP_NAME), n_start,
                    note + " recorded by {} {}".format(APP_NAME, APP_VERSION))
                if not ok and terr:
                    self.log("ID3 tagging skipped: {}".format(terr))

            size = os.path.getsize(path) if os.path.exists(path) else 0
            if size > 100000:
                self.log("{}  {}  ({:.1f} MB){}".format(
                    "SAVED (INCOMPLETE)" if cut_short else "DONE",
                    os.path.basename(path), size / 1048576,
                    "  stopped at {}".format(stopped_at.strftime("%H:%M")) if cut_short else ""))
            else:
                self.log("WARNING  {} is only {} bytes. ffmpeg: {}".format(
                    os.path.basename(path), size, (err or "").strip()[:300]))
            self.capture_finished(cap)
            self.ui(self.flash_queue)

        threading.Thread(target=run, daemon=True).start()

    def unique_path(self, filename):
        path = os.path.join(self.v_outdir.get(), filename)
        base, ext = os.path.splitext(path)
        n = 2
        while os.path.exists(path):
            path = "{} ({}){}".format(base, n, ext)
            n += 1
        return path

    def on_close(self):
        if self._closing:
            return
        self._closing = True
        self.quit_event.set()
        self.stop_event.set()
        self.recnow_stop.set()
        self.station()["url"] = self.v_url.get().strip()
        self.save_config()

        if not self.live_captures():
            self._finish_close()
            return

        # Never discard audio: ask ffmpeg to close its files, then wait.
        self.dlg_close = tk.Toplevel(self)
        self.dlg_close.title(APP_NAME)
        self.dlg_close.resizable(False, False)
        self.dlg_close.protocol("WM_DELETE_WINDOW", lambda: None)
        body = ttk.Frame(self.dlg_close, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Saving recordings in progress...",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.v_closing = tk.StringVar(value="")
        ttk.Label(body, textvariable=self.v_closing).pack(anchor="w", pady=(6, 8))
        bar = ttk.Progressbar(body, mode="indeterminate", length=280)
        bar.pack(fill="x")
        bar.start(60)
        self.dlg_close.transient(self)
        self.dlg_close.grab_set()

        self.stop_captures(None, "application closing")
        self._close_deadline = _time.monotonic() + CLOSE_WAIT_SEC
        self._await_close()

    def _await_close(self):
        left = self.live_captures()
        if left and _time.monotonic() < self._close_deadline:
            self.v_closing.set("{} file{} still being written and tagged - "
                               "{}s left before giving up.".format(
                                   len(left), "" if len(left) == 1 else "s",
                                   int(self._close_deadline - _time.monotonic())))
            self.after(300, self._await_close)
            return
        if left:
            for cap in left:
                p = cap.get("proc")
                if p and p.poll() is None:
                    try:
                        p.kill()
                    except Exception:
                        pass
        self._finish_close()

    def _finish_close(self):
        try:
            if getattr(self, "dlg_close", None):
                self.dlg_close.grab_release()
                self.dlg_close.destroy()
        except Exception:
            pass
        self.awake_holds = 0
        self._apply_awake()
        self.save_config()
        self.destroy()


def main():
    if sys.version_info < (3, 8):
        print("RadioSave needs Python 3.8 or newer.")
        sys.exit(1)
    RadioSaveApp().mainloop()


if __name__ == "__main__":
    main()

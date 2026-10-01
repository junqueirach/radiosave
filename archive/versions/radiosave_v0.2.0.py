#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RadioSave 2.0 - schedule-based internet radio recorder with live metadata.

Entries in the schedule are fully editable: add, batch-add, edit, remove.
While recording, RadioSave polls the station's "now playing" feed and names the
finished file after whatever the radio itself says was on air, falling back to
the scheduled name when the station is silent or offline.

Requirements: Python 3.8+ (tkinter, standard library only) and ffmpeg.
Filenames:    YYYY-MM-DD-HHh-HHh - PROGRAM NAME.mp3
"""

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
from datetime import date, datetime, time, timedelta, timezone
from tkinter import filedialog, messagebox, ttk

APP_NAME = "RadioSave"
APP_VERSION = "2.0"

# Brazil abolished DST in 2019, so Brasilia is a fixed UTC-03:00 all year.
BRT = timezone(timedelta(hours=-3), "BRT")

# Join a programme already in progress for up to this many minutes.
GRACE_MINUTES = 10
# How often to sample the station's now-playing feed while recording.
META_SAMPLE_SEC = 30
# How often to refresh the "on air now" banner while the window is open.
META_IDLE_SEC = 20

DAYS_PT = ["Domingo", "Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado"]
DAYS_EN = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
# Grid index (0 = Domingo) -> Python weekday (Monday = 0 .. Sunday = 6)
GRID_TO_PYWD = {0: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}
PYWD_TO_GRID = {v: k for k, v in GRID_TO_PYWD.items()}

TZ_CHOICES = ["Brasilia (UTC-3)", "My local time", "UK (London)", "Custom offset..."]
SPLIT_CHOICES = ["No split (one entry)", "30 minutes", "1 hour", "90 minutes", "2 hours", "3 hours"]
SPLIT_MINUTES = {"No split (one entry)": 0, "30 minutes": 30, "1 hour": 60,
                 "90 minutes": 90, "2 hours": 120, "3 hours": 180}

# ---------------------------------------------------------------------------
# Rádio Atlan weekly grid, Brasilia time. Taken from radioatlan.com/programacao/
# and cross-checked against the site's WordPress REST API. Used only to seed the
# schedule on first run - after that your edits live in the config file.
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
    """YYYY-MM-DD-HHh-HHh - PROGRAM NAME.mp3"""
    stem = "{}-{:02d}h-{:02d}h - {}".format(
        start_dt.strftime("%Y-%m-%d"), start_dt.hour, end_dt.hour, program)
    return sanitize(stem, ascii_only) + ".mp3"


def clean_title(raw):
    """Turn 'Projeto Orbum - -' into 'Projeto Orbum'."""
    if not raw:
        return ""
    t = str(raw).strip()
    t = re.sub(r"\s*-\s*-\s*$", "", t)        # trailing ' - -'
    t = re.sub(r"\s*[-–]\s*$", "", t)     # trailing dash
    t = re.sub(r"^\s*[-–]\s*", "", t)     # leading dash
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


def last_sunday(year, month):
    d = date(year, month, 31)
    while d.weekday() != 6:
        d -= timedelta(days=1)
    return d


def uk_offset_hours(naive_dt):
    """British Summer Time: last Sunday of March to last Sunday of October."""
    y = naive_dt.year
    start = datetime.combine(last_sunday(y, 3), time(1, 0))
    end = datetime.combine(last_sunday(y, 10), time(1, 0))
    return 1 if start <= naive_dt < end else 0


def localize(naive_dt, tz_kind, custom_minutes=0):
    """Attach a timezone to a naive datetime according to the user's choice."""
    if tz_kind.startswith("Brasilia"):
        return naive_dt.replace(tzinfo=BRT)
    if tz_kind.startswith("My local"):
        return naive_dt.astimezone()          # naive -> assumed system local
    if tz_kind.startswith("UK"):
        off = uk_offset_hours(naive_dt)
        return naive_dt.replace(tzinfo=timezone(timedelta(hours=off)))
    return naive_dt.replace(tzinfo=timezone(timedelta(minutes=custom_minutes)))


def to_local(dt_aware):
    return dt_aware.astimezone()


def local_tz_label():
    now = datetime.now().astimezone()
    off = now.utcoffset() or timedelta(0)
    total = int(off.total_seconds() // 60)
    sign = "+" if total >= 0 else "-"
    hh, mm = divmod(abs(total), 60)
    return "{} (UTC{}{:02d}:{:02d})".format(now.tzname() or "Local", sign, hh, mm)


def next_occurrence(grid_day, hh, mm, ref):
    """Next datetime (Brasilia) for this weekday + time, strictly after ref."""
    target = GRID_TO_PYWD[grid_day]
    delta = (target - ref.weekday()) % 7
    cand = ref.replace(hour=hh, minute=mm, second=0, microsecond=0) + timedelta(days=delta)
    if cand <= ref:
        cand += timedelta(days=7)
    return cand


def entry_next_start(entry, ref_brt):
    hh, mm = parse_hhmm(entry["start"]) or (0, 0)
    return next_occurrence(entry["day"], hh, mm, ref_brt)


def entry_is_on_air(entry, now_brt):
    """True if this entry's window contains now (checked against this week)."""
    hh, mm = parse_hhmm(entry["start"]) or (0, 0)
    target = GRID_TO_PYWD[entry["day"]]
    # look at the occurrence on or before now
    delta = (now_brt.weekday() - target) % 7
    start = (now_brt - timedelta(days=delta)).replace(
        hour=hh, minute=mm, second=0, microsecond=0)
    if start > now_brt:
        start -= timedelta(days=7)
    return start <= now_brt < start + timedelta(minutes=int(entry.get("dur", 60)))


def ffmpeg_command(ffmpeg, url, duration, outfile):
    return [
        ffmpeg, "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
        "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "30",
        "-i", url, "-t", str(int(duration)), "-c", "copy", "-f", "mp3", outfile,
    ]


def no_window_kwargs():
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": si, "creationflags": 0x08000000}
    return {}


def decide_name(prefer, radio_name, sched_name, entry_auto):
    """Choose the programme name for the finished file.

    Entries flagged `auto` always take the radio's word when it has one.
    Otherwise `prefer` decides which side wins, with the other as fallback.
    """
    radio_name = (radio_name or "").strip()
    sched_name = (sched_name or "").strip()
    if entry_auto:
        return radio_name or sched_name or "UNKNOWN PROGRAM"
    if prefer == "radio":
        return radio_name or sched_name or "UNKNOWN PROGRAM"
    return sched_name or radio_name or "UNKNOWN PROGRAM"


def pick_dominant(titles):
    """Most frequent non-empty title; ties break toward the earliest seen."""
    vals = [t for t in titles if t]
    if not vals:
        return ""
    counts = Counter(vals)
    best = max(counts.values())
    for t in vals:                       # preserve first-seen order on ties
        if counts[t] == best:
            return t
    return vals[0]


# --------------------------- metadata readers ------------------------------

def fetch_title_json(url, timeout=8):
    """Read a Maxcast/Icecast style status JSON and return the current title."""
    req = urllib.request.Request(url, headers={"User-Agent": "RadioSave/2.0"})
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
    """Read StreamTitle straight from the Shoutcast/Icecast stream."""
    req = urllib.request.Request(stream_url, headers={
        "Icy-MetaData": "1", "User-Agent": "RadioSave/2.0"})
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
    """Best-effort Maxcast status URL from a stream URL."""
    m = re.match(r"^(https?)://([^:/]+)(?::\d+)?/", stream_url or "")
    if not m:
        return ""
    scheme, host = m.group(1), m.group(2)
    if not slug:
        return ""
    return "{}://{}/api/status/{}/current.json".format(scheme, host, slug)


def build_batch(days, from_hhmm, to_hhmm, tz_kind, custom_minutes,
                split_minutes, prog, auto, ref=None):
    """Expand days + a time range + a split size into schedule entries.

    Times are given in `tz_kind` and stored in Brasilia time, so a range that
    crosses midnight - or that lands on a different weekday once converted -
    is handled here rather than by the caller.
    Returns (entries, error_message).
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
        if end_naive <= start_naive:                 # range crosses midnight
            end_naive += timedelta(days=1)
        total = int((end_naive - start_naive).total_seconds() // 60)
        if total <= 0:
            continue
        chunk = split_minutes if split_minutes > 0 else total
        cur = start_naive
        while cur < end_naive:
            dur = min(chunk, int((end_naive - cur).total_seconds() // 60))
            in_brt = localize(cur, tz_kind, custom_minutes).astimezone(BRT)
            out.append({
                "id": new_id(),
                "day": PYWD_TO_GRID[in_brt.weekday()],
                "start": in_brt.strftime("%H:%M"),
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
        "meta_mode": "json",
        "meta_url": "https://s30.maxcast.com.br/api/status/radioatlan/current.json",
        "entries": seed_atlan_entries(),
    }]


# ===========================================================================
# Dialogs
# ===========================================================================

class EntryDialog(tk.Toplevel):
    """Add or edit a single schedule entry."""

    def __init__(self, master, entry=None):
        super().__init__(master)
        self.title("Edit entry" if entry else "Add entry")
        self.transient(master)
        self.resizable(False, False)
        self.result = None

        e = entry or {"day": 0, "start": "19:00", "dur": 60, "prog": "", "auto": False}
        self.v_day = tk.StringVar(value=DAYS_PT[e["day"]])
        self.v_start = tk.StringVar(value=e["start"])
        self.v_dur = tk.IntVar(value=int(e.get("dur", 60)))
        self.v_prog = tk.StringVar(value=e.get("prog", ""))
        self.v_auto = tk.BooleanVar(value=bool(e.get("auto", False)))
        self.v_tz = tk.StringVar(value="Brasilia (UTC-3)")
        self.v_custom = tk.StringVar(value="0")

        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="Times entered in:").grid(row=0, column=0, sticky="e", pady=4)
        cb = ttk.Combobox(f, textvariable=self.v_tz, values=TZ_CHOICES, state="readonly", width=22)
        cb.grid(row=0, column=1, sticky="w", pady=4)
        cb.bind("<<ComboboxSelected>>", lambda ev: self._toggle_custom())
        self.ent_custom = ttk.Entry(f, textvariable=self.v_custom, width=8)
        self.lbl_custom = ttk.Label(f, text="UTC offset (minutes):")

        ttk.Label(f, text="Day:").grid(row=2, column=0, sticky="e", pady=4)
        ttk.Combobox(f, textvariable=self.v_day, values=DAYS_PT, state="readonly",
                     width=22).grid(row=2, column=1, sticky="w", pady=4)

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
        # Convert the entered wall-clock time into Brasilia time for storage.
        ref = datetime.now()
        target_py = GRID_TO_PYWD[day]
        naive = ref.replace(hour=hh, minute=mm, second=0, microsecond=0)
        naive += timedelta(days=(target_py - ref.weekday()) % 7)
        aware = localize(naive, self.v_tz.get(), custom)
        in_brt = aware.astimezone(BRT)

        self.result = {
            "id": new_id(),
            "day": PYWD_TO_GRID[in_brt.weekday()],
            "start": in_brt.strftime("%H:%M"),
            "dur": int(self.v_dur.get()),
            "prog": "" if self.v_auto.get() else self.v_prog.get().strip(),
            "auto": bool(self.v_auto.get()),
            "sel": True,
        }
        self.destroy()


class BatchDialog(tk.Toplevel):
    """Create many entries at once from days + a time range + a split size."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Batch add entries")
        self.transient(master)
        self.resizable(False, False)
        self.result = None

        self.v_days = [tk.BooleanVar(value=False) for _ in range(7)]
        self.v_from = tk.StringVar(value="09:00")
        self.v_to = tk.StringVar(value="15:00")
        self.v_tz = tk.StringVar(value="Brasilia (UTC-3)")
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
        cb = ttk.Combobox(f, textvariable=self.v_tz, values=TZ_CHOICES, state="readonly", width=22)
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
                     state="readonly", width=22).grid(row=5, column=1, sticky="w", pady=4)

        ttk.Label(f, text="Program name:").grid(row=6, column=0, sticky="e", pady=4)
        self.ent_prog = ttk.Entry(f, textvariable=self.v_prog, width=40)
        self.ent_prog.grid(row=6, column=1, sticky="we", pady=4)
        ttk.Checkbutton(f, text="Use the program name reported by the radio (if available)",
                        variable=self.v_auto, command=self._toggle_auto).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(2, 6))

        ttk.Button(f, text="Preview", command=self._preview).grid(row=8, column=0, sticky="e", pady=6)
        self.lst = tk.Listbox(f, height=9, width=62)
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
            self.lst.insert("end", "{}  {} BRT  +{} min   {}".format(
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
        s = station or {"name": "", "url": "", "meta_mode": "icy", "meta_url": ""}

        self.v_name = tk.StringVar(value=s.get("name", ""))
        self.v_url = tk.StringVar(value=s.get("url", ""))
        self.v_mode = tk.StringVar(value=s.get("meta_mode", "icy"))
        self.v_meta = tk.StringVar(value=s.get("meta_url", ""))
        self.v_slug = tk.StringVar(value="")

        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Station name:").grid(row=0, column=0, sticky="e", pady=4)
        ttk.Entry(f, textvariable=self.v_name, width=46).grid(row=0, column=1, pady=4)
        ttk.Label(f, text="Stream URL:").grid(row=1, column=0, sticky="e", pady=4)
        ttk.Entry(f, textvariable=self.v_url, width=46).grid(row=1, column=1, pady=4)

        box = ttk.LabelFrame(f, text="Now-playing source")
        box.grid(row=2, column=0, columnspan=2, sticky="we", pady=8)
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
        btns.grid(row=3, column=0, columnspan=2, pady=6)
        ttk.Button(btns, text="Test now", width=10, command=self._test).pack(side="left", padx=5)
        ttk.Button(btns, text="OK", width=10, command=self._ok).pack(side="left", padx=5)
        ttk.Button(btns, text="Cancel", width=10, command=self.destroy).pack(side="left", padx=5)
        self.grab_set()
        self.wait_window()

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
        self.result = {"name": self.v_name.get().strip(), "url": self.v_url.get().strip(),
                       "meta_mode": self.v_mode.get(), "meta_url": self.v_meta.get().strip()}
        self.destroy()


# ===========================================================================
# Main window
# ===========================================================================

class RadioSaveApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("{} {}".format(APP_NAME, APP_VERSION))
        self.geometry("1120x720")
        self.minsize(980, 640)

        self.log_q = queue.Queue()
        self.stop_event = threading.Event()
        self.scheduler_thread = None
        self.active_procs = []
        self.row_entry = {}          # treeview iid -> entry id
        self.queue_rows = []         # listbox index -> entry id
        self.live_title = ""
        self.live_checked = None

        cfg = self.load_config()
        self.stations = cfg.get("stations") or default_stations()
        for s in self.stations:                       # tolerate older configs
            s.setdefault("entries", [])
            s.setdefault("meta_mode", "off")
            s.setdefault("meta_url", "")

        self.v_station = tk.StringVar(value=cfg.get("station", self.stations[0]["name"]))
        self.v_url = tk.StringVar()
        self.v_outdir = tk.StringVar(value=cfg.get(
            "outdir", os.path.join(os.path.expanduser("~"), "RadioSave")))
        self.v_ffmpeg = tk.StringVar(value=cfg.get("ffmpeg", shutil.which("ffmpeg") or "ffmpeg"))
        self.v_pre = tk.IntVar(value=cfg.get("pre", 15))
        self.v_post = tk.IntVar(value=cfg.get("post", 30))
        self.v_ascii = tk.BooleanVar(value=cfg.get("ascii", True))
        self.v_nametz = tk.StringVar(value=cfg.get("nametz", "brasilia"))
        self.v_prefer = tk.StringVar(value=cfg.get("prefer", "radio"))
        self.v_status = tk.StringVar(value="Idle.")
        self.v_hide_reruns = tk.BooleanVar(value=False)
        self.v_only_sel = tk.BooleanVar(value=False)
        self.v_search = tk.StringVar()
        self.v_onair = tk.StringVar(value="On air now: (not checked yet)")
        self.v_conv_in = tk.StringVar(value="19:00")
        self.v_conv_dir = tk.StringVar(value="brt2local")
        self.v_conv_out = tk.StringVar(value="")

        self._build_ui()
        self.on_station_change()
        self.refresh_grid()
        self.after(200, self.drain_log)
        self.after(1000, self.tick_clocks)
        self.after(1500, self.poll_meta_idle)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------ config ------------------------------

    def load_config(self):
        try:
            with open(config_path(), "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def save_config(self):
        data = {
            "stations": self.stations,
            "station": self.v_station.get(),
            "outdir": self.v_outdir.get(),
            "ffmpeg": self.v_ffmpeg.get(),
            "pre": self.v_pre.get(),
            "post": self.v_post.get(),
            "ascii": self.v_ascii.get(),
            "nametz": self.v_nametz.get(),
            "prefer": self.v_prefer.get(),
        }
        try:
            with open(config_path(), "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
        except Exception as exc:
            self.log("Could not save settings: {}".format(exc))

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

        onair = ttk.Label(top, textvariable=self.v_onair, foreground="#0a6b0a",
                          font=("Segoe UI", 10, "bold"))
        onair.grid(row=2, column=0, columnspan=4, sticky="w", padx=6, pady=(6, 8))
        ttk.Button(top, text="Refresh", width=9,
                   command=lambda: threading.Thread(target=self._meta_once, daemon=True).start()
                   ).grid(row=2, column=4, padx=3, pady=(6, 8))
        top.columnconfigure(1, weight=1)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=4)
        self.tab_grid = ttk.Frame(nb)
        self.tab_conv = ttk.Frame(nb)
        self.tab_log = ttk.Frame(nb)
        self.tab_set = ttk.Frame(nb)
        nb.add(self.tab_grid, text="  Schedule  ")
        nb.add(self.tab_conv, text="  Time converter  ")
        nb.add(self.tab_log, text="  Queue & log  ")
        nb.add(self.tab_set, text="  Settings  ")
        self._build_grid_tab()
        self._build_conv_tab()
        self._build_log_tab()
        self._build_settings_tab()

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=10, pady=(4, 10))
        self.btn_start = ttk.Button(bar, text="Start scheduler", command=self.start_scheduler)
        self.btn_start.pack(side="left")
        self.btn_stop = ttk.Button(bar, text="Stop", command=self.stop_scheduler, state="disabled")
        self.btn_stop.pack(side="left", padx=6)
        ttk.Label(bar, textvariable=self.v_status).pack(side="left", padx=14)

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

        cols = ("chk", "day", "brt", "end", "local", "dur", "prog")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", selectmode="extended")
        for c, txt, w, anc in (
                ("chk", "", 32, "center"), ("day", "Day", 92, "w"),
                ("brt", "Start BRT", 78, "center"), ("end", "End BRT", 74, "center"),
                ("local", "Your time", 120, "center"), ("dur", "Min", 48, "center"),
                ("prog", "Program", 470, "w")):
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
        self.lbl_brt = ttk.Label(box, text="", font=("Segoe UI", 11))
        self.lbl_brt.pack(anchor="w", padx=10, pady=(8, 2))
        self.lbl_loc = ttk.Label(box, text="", font=("Segoe UI", 11))
        self.lbl_loc.pack(anchor="w", padx=10, pady=(0, 8))

        c = ttk.LabelFrame(f, text="Convert a time")
        c.pack(fill="x", padx=10, pady=6)
        ttk.Radiobutton(c, text="Brasilia -> my time", value="brt2local",
                        variable=self.v_conv_dir, command=self.do_convert).grid(
            row=0, column=0, sticky="w", padx=8, pady=6)
        ttk.Radiobutton(c, text="My time -> Brasilia", value="local2brt",
                        variable=self.v_conv_dir, command=self.do_convert).grid(
            row=0, column=1, sticky="w", padx=8)
        ttk.Label(c, text="Time (HH:MM):").grid(row=1, column=0, sticky="e", padx=8, pady=8)
        ce = ttk.Entry(c, textvariable=self.v_conv_in, width=10)
        ce.grid(row=1, column=1, sticky="w")
        ce.bind("<KeyRelease>", lambda ev: self.do_convert())
        ttk.Label(c, textvariable=self.v_conv_out, font=("Segoe UI", 11, "bold")).grid(
            row=1, column=2, sticky="w", padx=16)

        ttk.Label(f, text=(
            "Brasilia is fixed at UTC-03:00 (Brazil dropped daylight saving in 2019).\n"
            "Your timezone comes from Windows and is DST-aware for the date of each recording."),
            foreground="#555").pack(anchor="w", padx=14, pady=10)
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
        g = ttk.LabelFrame(f, text="Output")
        g.pack(fill="x", padx=10, pady=10)
        ttk.Label(g, text="Save folder:").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        ttk.Entry(g, textvariable=self.v_outdir, width=58).grid(row=0, column=1, sticky="we")
        ttk.Button(g, text="Browse...", command=self.pick_outdir).grid(row=0, column=2, padx=6)
        ttk.Label(g, text="ffmpeg:").grid(row=1, column=0, sticky="w", padx=8, pady=(0, 8))
        ttk.Entry(g, textvariable=self.v_ffmpeg, width=58).grid(row=1, column=1, sticky="we", pady=(0, 8))
        ttk.Button(g, text="Browse...", command=self.pick_ffmpeg).grid(row=1, column=2, padx=6, pady=(0, 8))
        g.columnconfigure(1, weight=1)

        n = ttk.LabelFrame(f, text="Filenames")
        n.pack(fill="x", padx=10, pady=6)
        ttk.Label(n, text="Pattern:  YYYY-MM-DD-HHh-HHh - PROGRAM NAME.mp3").grid(
            row=0, column=0, columnspan=3, sticky="w", padx=8, pady=(8, 4))
        ttk.Label(n, text="Name comes from:").grid(row=1, column=0, sticky="w", padx=8, pady=3)
        ttk.Radiobutton(n, text="What the radio reported (schedule as fallback)", value="radio",
                        variable=self.v_prefer).grid(row=1, column=1, sticky="w")
        ttk.Radiobutton(n, text="The schedule (radio as fallback)", value="grid",
                        variable=self.v_prefer).grid(row=2, column=1, sticky="w")
        ttk.Label(n, text="Times in filename:").grid(row=3, column=0, sticky="w", padx=8, pady=3)
        ttk.Radiobutton(n, text="Brasilia", value="brasilia",
                        variable=self.v_nametz).grid(row=3, column=1, sticky="w")
        ttk.Radiobutton(n, text="My local time", value="local",
                        variable=self.v_nametz).grid(row=4, column=1, sticky="w")
        ttk.Checkbutton(n, text="Strip accents", variable=self.v_ascii).grid(
            row=5, column=0, columnspan=2, sticky="w", padx=8, pady=(4, 8))

        p = ttk.LabelFrame(f, text="Padding")
        p.pack(fill="x", padx=10, pady=6)
        ttk.Label(p, text="Start this many seconds early:").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        ttk.Spinbox(p, from_=0, to=300, textvariable=self.v_pre, width=6).grid(row=0, column=1, sticky="w")
        ttk.Label(p, text="Keep recording past the end (seconds):").grid(
            row=1, column=0, sticky="w", padx=8, pady=(0, 8))
        ttk.Spinbox(p, from_=0, to=600, textvariable=self.v_post, width=6).grid(
            row=1, column=1, sticky="w", pady=(0, 8))

        ttk.Label(f, text="Everything is saved when you close the window.",
                  foreground="#555").pack(anchor="w", padx=14, pady=8)

    # --------------------------- stations ---------------------------

    def station(self):
        for s in self.stations:
            if s["name"] == self.v_station.get():
                return s
        return self.stations[0]

    def entries(self):
        return self.station().setdefault("entries", [])

    def on_station_change(self):
        self.v_url.set(self.station().get("url", ""))
        self.live_title = ""
        self.v_onair.set("On air now: (checking...)")
        threading.Thread(target=self._meta_once, daemon=True).start()

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

    def edit_station(self):
        cur = self.station()
        d = StationDialog(self, cur)
        if not d.result:
            return
        cur.update(d.result)
        self.cmb_station["values"] = [s["name"] for s in self.stations]
        self.v_station.set(cur["name"])
        self.on_station_change()
        self.refresh_grid()

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
        d = EntryDialog(self)
        if d.result:
            self.entries().append(d.result)
            self.refresh_grid()
            self.log("Added entry: {} {} ({} min)".format(
                DAYS_PT[d.result["day"]], d.result["start"], d.result["dur"]))

    def batch_add(self):
        d = BatchDialog(self)
        if d.result:
            self.entries().extend(d.result)
            self.refresh_grid()
            self.log("Batch added {} entries.".format(len(d.result)))

    def edit_entry(self):
        sel = self.selected_entries()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select a row first.")
            return
        if len(sel) > 1:
            messagebox.showinfo(APP_NAME, "Select a single row to edit.")
            return
        old = sel[0]
        d = EntryDialog(self, old)
        if d.result:
            keep_id, keep_sel = old["id"], old.get("sel", False)
            old.update(d.result)
            old["id"], old["sel"] = keep_id, keep_sel
            self.refresh_grid()

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
        self.log("Removed {} entr{}.".format(len(ids), "y" if len(ids) == 1 else "ies"))

    def toggle_selected_rows(self):
        for e in self.selected_entries():
            e["sel"] = not e.get("sel", False)
        self.refresh_grid()

    def bulk(self, on):
        shown = {self.row_entry[i] for i in self.tree.get_children() if i in self.row_entry}
        for e in self.entries():
            if on:
                if e["id"] in shown:
                    e["sel"] = True
            else:
                e["sel"] = False
        self.refresh_grid()

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
        now_brt = datetime.now(BRT)

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
            nxt = next_occurrence(e["day"], hh, mm, now_brt)
            end = nxt + timedelta(minutes=int(e.get("dur", 60)))
            loc = to_local(nxt)
            tags = []
            if entry_is_on_air(e, now_brt):
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
        now_brt = datetime.now(BRT)
        rows = []
        for e in self.entries():
            if not e.get("sel"):
                continue
            start = entry_next_start(e, now_brt)
            rows.append((start, e))
        for start, e in sorted(rows, key=lambda x: x[0])[:80]:
            loc = to_local(start)
            self.lst_queue.insert("end", "{}   (your time {})   {} min   {}".format(
                start.strftime("%a %Y-%m-%d %H:%M BRT"), loc.strftime("%a %d %H:%M"),
                int(e.get("dur", 60)), e.get("prog") or "<name from radio>"))
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
        hm = parse_hhmm(self.v_conv_in.get())
        if not hm:
            self.v_conv_out.set("--:--")
            return
        hh, mm = hm
        if self.v_conv_dir.get() == "brt2local":
            src = datetime.now(BRT).replace(hour=hh, minute=mm, second=0, microsecond=0)
            dst = src.astimezone()
            label = "= {} your time".format(dst.strftime("%H:%M"))
        else:
            src = datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0).astimezone()
            dst = src.astimezone(BRT)
            label = "= {} in Brasilia".format(dst.strftime("%H:%M"))
        if dst.date() > src.date():
            label += "  (next day)"
        elif dst.date() < src.date():
            label += "  (previous day)"
        self.v_conv_out.set(label)

    def tick_clocks(self):
        self.lbl_brt.config(text="Brasilia:   {}".format(
            datetime.now(BRT).strftime("%a %d %b %Y  %H:%M:%S")))
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

    def drain_log(self):
        try:
            while True:
                line = self.log_q.get_nowait()
                self.txt_log.config(state="normal")
                self.txt_log.insert("end", line + "\n")
                self.txt_log.see("end")
                self.txt_log.config(state="disabled")
        except queue.Empty:
            pass
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
                p = subprocess.run(ffmpeg_command(self.v_ffmpeg.get(), url, 8, out),
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

    # --------------------------- scheduler ---------------------------

    def start_scheduler(self):
        if not any(e.get("sel") for e in self.entries()):
            messagebox.showinfo(APP_NAME, "Tick at least one entry on the Schedule tab.")
            return
        if not self.v_url.get().strip():
            messagebox.showwarning(APP_NAME, "This station has no stream URL.")
            return
        if not shutil.which(self.v_ffmpeg.get()) and not os.path.exists(self.v_ffmpeg.get()):
            messagebox.showwarning(APP_NAME, "ffmpeg was not found.\nSet the path on Settings.")
            return
        try:
            os.makedirs(self.v_outdir.get(), exist_ok=True)
        except Exception as exc:
            messagebox.showerror(APP_NAME, "Cannot create the save folder:\n{}".format(exc))
            return
        self.station()["url"] = self.v_url.get().strip()
        self.stop_event.clear()
        self.scheduler_thread = threading.Thread(target=self.scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.log("Scheduler started. You can minimise this window.")

    def stop_scheduler(self):
        self.stop_event.set()
        for p in list(self.active_procs):
            try:
                p.terminate()
            except Exception:
                pass
        self.active_procs.clear()
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.log("Scheduler stopped.")

    def scheduler_loop(self):
        fired = set()
        grace = timedelta(minutes=GRACE_MINUTES)
        while not self.stop_event.is_set():
            now_brt = datetime.now(BRT)
            for e in list(self.entries()):
                if not e.get("sel"):
                    continue
                start = entry_next_start(e, now_brt - grace)
                launch = start - timedelta(seconds=int(self.v_pre.get()))
                stamp = "{}@{}".format(e["id"], start.isoformat())
                if stamp in fired:
                    continue
                if launch <= now_brt < start + grace:
                    fired.add(stamp)
                    self.spawn_recording(e, start)
            cutoff = now_brt - timedelta(hours=6)
            fired = {s for s in fired
                     if datetime.fromisoformat(s.split("@", 1)[1]) > cutoff}
            self.stop_event.wait(2.0)

    def spawn_recording(self, entry, start_brt):
        st = dict(self.station())
        post = int(self.v_post.get())
        dur_min = int(entry.get("dur", 60))
        end_brt = start_brt + timedelta(minutes=dur_min)
        now_brt = datetime.now(BRT)
        seconds = (end_brt - now_brt).total_seconds() + post
        if seconds <= 0:
            self.log("Skipped '{}' - its slot has already ended.".format(entry.get("prog")))
            return

        if self.v_nametz.get() == "local":
            n_start, n_end = to_local(start_brt), to_local(end_brt)
        else:
            n_start, n_end = start_brt, end_brt

        sched_name = entry.get("prog") or ""
        provisional = sched_name or "RECORDING"
        outpath = self.unique_path(build_filename(n_start, n_end, provisional, self.v_ascii.get()))
        cmd = ffmpeg_command(self.v_ffmpeg.get(), st.get("url", ""), seconds, outpath)
        samples = []
        stop_sampling = threading.Event()

        def sampler():
            while not stop_sampling.is_set():
                t = fetch_station_title(st)
                if t:
                    samples.append(t)
                stop_sampling.wait(META_SAMPLE_SEC)

        def run():
            self.log("RECORDING  {}  ({} min)  -> {}".format(
                sched_name or "<name from radio>", dur_min, os.path.basename(outpath)))
            sthread = None
            if st.get("meta_mode", "off") != "off":
                sthread = threading.Thread(target=sampler, daemon=True)
                sthread.start()
            err = ""
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                     text=True, **no_window_kwargs())
                self.active_procs.append(p)
                _, err = p.communicate()
                if p in self.active_procs:
                    self.active_procs.remove(p)
            except FileNotFoundError:
                self.log("ffmpeg not found - recording aborted.")
                stop_sampling.set()
                return
            except Exception as exc:
                self.log("Recording error: {}".format(exc))
                stop_sampling.set()
                return
            stop_sampling.set()

            radio_name = pick_dominant(samples)
            if samples:
                uniq = len(set(samples))
                self.log("Radio reported '{}' in {} of {} samples ({} distinct).".format(
                    radio_name, samples.count(radio_name), len(samples), uniq))

            final = decide_name(self.v_prefer.get(), radio_name, sched_name,
                                entry.get("auto"))

            path = outpath
            wanted = build_filename(n_start, n_end, final, self.v_ascii.get())
            if os.path.basename(outpath) != wanted and os.path.exists(outpath):
                target = self.unique_path(wanted)
                try:
                    os.replace(outpath, target)
                    path = target
                    self.log("Renamed to: {}".format(os.path.basename(target)))
                except Exception as exc:
                    self.log("Could not rename ({}). Kept {}".format(exc, os.path.basename(outpath)))

            size = os.path.getsize(path) if os.path.exists(path) else 0
            if size > 100000:
                self.log("DONE  {}  ({:.1f} MB)".format(os.path.basename(path), size / 1048576))
            else:
                self.log("WARNING  {} is only {} bytes. ffmpeg: {}".format(
                    os.path.basename(path), size, (err or "").strip()[:300]))

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
        if self.active_procs and not messagebox.askyesno(
                APP_NAME, "A recording is still running. Quit anyway?"):
            return
        self.stop_event.set()
        for p in list(self.active_procs):
            try:
                p.terminate()
            except Exception:
                pass
        self.station()["url"] = self.v_url.get().strip()
        self.save_config()
        self.destroy()


def main():
    if sys.version_info < (3, 8):
        print("RadioSave needs Python 3.8 or newer.")
        sys.exit(1)
    RadioSaveApp().mainloop()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RadioSave - schedule-based internet radio recorder.

Pick programs from an embedded weekly grid, and RadioSave waits for them and
records each one to its own file using ffmpeg.

Requirements: Python 3.9+ (tkinter, standard library only) and ffmpeg on PATH.

Files are named:   YYYY-MM-DD-HHh-HHh - PROGRAM NAME.mp3
"""

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import unicodedata
from datetime import datetime, timedelta, timezone
from tkinter import filedialog, messagebox, ttk

APP_NAME = "RadioSave"
APP_VERSION = "1.0"

# Brazil abolished DST in 2019, so Brasilia is a fixed UTC-03:00 year round.
# This avoids depending on the tzdata package, which is not bundled on Windows.
BRT = timezone(timedelta(hours=-3), "BRT")

# If the app is started (or wakes up) after a programme has already begun, it
# will still join in progress for this many minutes and record the remainder.
GRACE_MINUTES = 10

DAYS = ["Domingo", "Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado"]
DAYS_EN = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
# Grid index (0=Domingo) -> Python weekday (Monday=0 .. Sunday=6)
GRID_TO_PYWD = {0: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}

DEFAULT_RADIOS = [
    {"name": "Radio Atlan", "url": "https://s30.maxcast.com.br:8157/live"},
]

# ---------------------------------------------------------------------------
# Weekly schedule, Brasilia time, pulled from radioatlan.com/programacao/
# and cross-checked against the site's WordPress REST API
# (/wp-json/wp/v2/programacao-semanal filtered by the dia-da-semana taxonomy).
# Index 0 = Domingo ... index 6 = Sabado. Each list is hours 00..23.
# ---------------------------------------------------------------------------
SCHEDULE = {
    "Radio Atlan": [
        # ---- Domingo ----
        [
            "CONVERSAS SOBRE ESPIRITUALIDADE - REPRISE",
            "COSMIC REVELATION",
            "LIVROS QUE FAZEM PENSAR - REPRISE",
            "PARA ONDE CAMINHA A HUMANIDADE - REPRISE",
            "ARVORE DA VIDA - REPRISE",
            "DESPERTAR DA CONSCIENCIA COSMICA - REPRISE",
            "PONTO DE MUTACAO - REPRISE",
            "SALUTEM - SAUDE E DESENV. HUMANO - REPRISE",
            "VIVER COM SAUDE - REPRISE",
            "NA BUSCA DA VERDADE - REPRISE",
            "NO MUNDO DO SER - REPRISE",
            "PROJETO ORBUM - REPRISE",
            "REINVENCAO DA VIDA - REPRISE",
            "ATLAN PAINEL - REPRISE",
            "MITOS E CONSPIRACOES - REPRISE",
            "PONTO DE MUTACAO - REPRISE",
            "MUSICA, ARTE E FILOSOFIA - REPRISE",
            "IMAGENS E REFLEXOES - REPRISE",
            "A LIRA DE ORFEU",
            "PAINEIS DA REVELACAO COSMICA",
            "PROJETO ORBUM",
            "CONVERSAS SOBRE ESPIRITUALIDADE",
            "ACOMPANHANDO O MUNDO - REPRISE",
            "CONEXOES COSMICAS - REPRISE",
        ],
        # ---- Segunda ----
        [
            "REINVENCAO DA VIDA - REPRISE",
            "COSMIC REVELATION - REPRISE",
            "PROJETO ORBUM - REPRISE",
            "NA BUSCA DA VERDADE - REPRISE",
            "PAINEIS DA REVELACAO COSMICA - REPRISE",
            "VIVER COM SAUDE - REPRISE",
            "NO MUNDO DO SER - REPRISE",
            "PAINEIS DA REVELACAO COSMICA - REPRISE",
            "PARA ONDE CAMINHA A HUMANIDADE - REPRISE",
            "ARVORE DA VIDA - REPRISE",
            "DESPERTAR DA CONSCIENCIA COSMICA - REPRISE",
            "SALUTEM - SAUDE E DESENV. HUMANO - REPRISE",
            "A LIRA DE ORFEU - REPRISE",
            "PONTO DE MUTACAO - REPRISE",
            "CONVERSAS SOBRE ESPIRITUALIDADE - REPRISE",
            "MITOS E CONSPIRACOES - REPRISE",
            "DESPERTAR DA CONSCIENCIA COSMICA - REPRISE",
            "ALEM DAS FRONTEIRAS FILOSOFICAS - REPRISE",
            "A LIRA DE ORFEU - REPRISE",
            "MUSICA, ARTE E FILOSOFIA - REPRISE",
            "CONEXOES COSMICAS",
            "LIVROS QUE FAZEM PENSAR",
            "ATLAN PAINEL - REPRISE",
            "PONTO DE MUTACAO - REPRISE",
        ],
        # ---- Terca ----
        [
            "DESPERTAR DA CONSCIENCIA COSMICA - REPRISE",
            "ALEM DAS FRONTEIRAS FILOSOFICAS - REPRISE",
            "NO MUNDO DO SER - REPRISE",
            "MITOS E CONSPIRACOES - REPRISE",
            "PONTO DE MUTACAO - REPRISE",
            "CONVERSAS SOBRE ESPIRITUALIDADE - REPRISE",
            "PARA ONDE CAMINHA A HUMANIDADE - REPRISE",
            "IMAGENS E REFLEXOES - REPRISE",
            "SALUTEM - SAUDE E DESENV. HUMANO - REPRISE",
            "ACOMPANHANDO O MUNDO - REPRISE",
            "ALEM DAS FRONTEIRAS FILOSOFICAS - REPRISE",
            "VIVER COM SAUDE - REPRISE",
            "MUSICA, ARTE E FILOSOFIA - REPRISE",
            "PROJETO ORBUM - REPRISE",
            "LIVROS QUE FAZEM PENSAR - REPRISE",
            "ATLAN PAINEL - REPRISE",
            "TRANSMUTACAO MUSICAL - REPRISE",
            "PROJETO ORBUM - REPRISE",
            "MUSICA",
            "REINVENCAO DA VIDA",
            "EGREGORA DE MAGIA",
            "ALEM DAS FRONTEIRAS FILOSOFICAS",
            "CONEXOES COSMICAS - REPRISE",
            "MUSICA, ARTE E FILOSOFIA - REPRISE",
        ],
        # ---- Quarta ----
        [
            "MITOS E CONSPIRACOES - REPRISE",
            "TRANSMUTACAO MUSICAL - REPRISE",
            "A LIRA DE ORFEU - REPRISE",
            "ALEM DAS FRONTEIRAS FILOSOFICAS - REPRISE",
            "CONEXOES COSMICAS - REPRISE",
            "MUSICA",
            "CONVERSAS SOBRE ESPIRITUALIDADE - REPRISE",
            "REINVENCAO DA VIDA - REPRISE",
            "PONTO DE MUTACAO - REPRISE",
            "LIVROS QUE FAZEM PENSAR - REPRISE",
            "ALEM DAS FRONTEIRAS FILOSOFICAS - REPRISE",
            "MITOS E CONSPIRACOES - REPRISE",
            "VIVER COM SAUDE - REPRISE",
            "SALUTEM - SAUDE E DESENV. HUMANO - REPRISE",
            "NA BUSCA DA VERDADE - REPRISE",
            "DESPERTAR DA CONSCIENCIA COSMICA - REPRISE",
            "IMAGENS E REFLEXOES - REPRISE",
            "PAINEIS DA REVELACAO COSMICA - REPRISE",
            "TRANSMUTACAO MUSICAL - REPRISE",
            "NO MUNDO DO SER",
            "ARVORE DA VIDA",
            "PARA ONDE CAMINHA A HUMANIDADE",
            "A LIRA DE ORFEU - REPRISE",
            "ATLAN PAINEL - REPRISE",
        ],
        # ---- Quinta ----
        [
            "CONEXOES COSMICAS - REPRISE",
            "VIVER COM SAUDE - REPRISE",
            "PAINEIS DA REVELACAO COSMICA - REPRISE",
            "A LIRA DE ORFEU - REPRISE",
            "SALUTEM - SAUDE E DESENV. HUMANO - REPRISE",
            "MUSICA - REPRISE",
            "TRANSMUTACAO MUSICAL - REPRISE",
            "ALEM DAS FRONTEIRAS FILOSOFICAS - REPRISE",
            "ARVORE DA VIDA - REPRISE",
            "PARA ONDE CAMINHA A HUMANIDADE - REPRISE",
            "IMAGENS E REFLEXOES - REPRISE",
            "MUSICA, ARTE E FILOSOFIA - REPRISE",
            "LIVROS QUE FAZEM PENSAR - REPRISE",
            "PROJETO ORBUM - REPRISE",
            "A LIRA DE ORFEU - REPRISE",
            "CONVERSAS SOBRE ESPIRITUALIDADE - REPRISE",
            "CONEXOES COSMICAS - REPRISE",
            "VIVER COM SAUDE - REPRISE",
            "NO MUNDO DO SER - REPRISE",
            "DESPERTAR DA CONSCIENCIA COSMICA",
            "SALUTEM - SAUDE E DESENV. HUMANO",
            "ATLAN PAINEL",
            "TRANSMUTACAO MUSICAL",
            "PONTO DE MUTACAO - REPRISE",
        ],
        # ---- Sexta ----
        [
            "VIVER COM SAUDE - REPRISE",
            "PARA ONDE CAMINHA A HUMANIDADE - REPRISE",
            "PONTO DE MUTACAO - REPRISE",
            "ARVORE DA VIDA - REPRISE",
            "NO MUNDO DO SER - REPRISE",
            "PAINEIS DA REVELACAO COSMICA - REPRISE",
            "LIVROS QUE FAZEM PENSAR - REPRISE",
            "MUSICA, ARTE E FILOSOFIA - REPRISE",
            "DESPERTAR DA CONSCIENCIA COSMICA - REPRISE",
            "TRANSMUTACAO MUSICAL - REPRISE",
            "NA BUSCA DA VERDADE - REPRISE",
            "CONVERSAS SOBRE ESPIRITUALIDADE - REPRISE",
            "IMAGENS E REFLEXOES - REPRISE",
            "ACOMPANHANDO O MUNDO - REPRISE",
            "ALEM DAS FRONTEIRAS FILOSOFICAS - REPRISE",
            "NO MUNDO DO SER - REPRISE",
            "NA BUSCA DA VERDADE - REPRISE",
            "DESPERTAR DA CONSCIENCIA COSMICA - REPRISE",
            "ARVORE DA VIDA - REPRISE",
            "REINVENCAO DA VIDA - REPRISE",
            "MUSICA, ARTE E FILOSOFIA",
            "VIVER COM SAUDE",
            "IMAGENS E REFLEXOES",
            "SALUTEM - SAUDE E DESENV. HUMANO - REPRISE",
        ],
        # ---- Sabado ----
        [
            "ACOMPANHANDO O MUNDO - REPRISE",
            "CONEXOES COSMICAS - REPRISE",
            "NO MUNDO DO SER - REPRISE",
            "DESPERTAR DA CONSCIENCIA COSMICA - REPRISE",
            "CONVERSAS SOBRE ESPIRITUALIDADE - REPRISE",
            "MUSICA - REPRISE",
            "PAINEIS DA REVELACAO COSMICA - REPRISE",
            "ARVORE DA VIDA - REPRISE",
            "PONTO DE MUTACAO - REPRISE",
            "IMAGENS E REFLEXOES - REPRISE",
            "A LIRA DE ORFEU - REPRISE",
            "TRANSMUTACAO MUSICAL - REPRISE",
            "PROJETO ORBUM - REPRISE",
            "ATLAN PAINEL - REPRISE",
            "REINVENCAO DA VIDA - REPRISE",
            "ACOMPANHANDO O MUNDO - REPRISE",
            "PONTO DE MUTACAO",
            "ARVORE DA VIDA - REPRISE",
            "PARA ONDE CAMINHA A HUMANIDADE - REPRISE",
            "ATLAN PAINEL - REPRISE",
            "NA BUSCA DA VERDADE",
            "MITOS E CONSPIRACOES",
            "CONEXOES COSMICAS - REPRISE",
            "ACOMPANHANDO O MUNDO - REPRISE",
        ],
    ]
}


# ---------------------------------------------------------------------------
# Helpers (pure functions - unit tested separately)
# ---------------------------------------------------------------------------

def is_rerun(title):
    return "REPRISE" in title.upper()


def config_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, APP_NAME)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "config.json")


def sanitize(name, ascii_only=False):
    """Make a string safe for a Windows filename."""
    if ascii_only:
        name = unicodedata.normalize("NFKD", name)
        name = name.encode("ascii", "ignore").decode("ascii")
    name = re.sub(r'[<>:"/\\|?*]', "-", name)
    name = re.sub(r"\s+", " ", name).strip().strip(".")
    return name[:150] or "recording"


def build_filename(start_dt, end_dt, program, ascii_only=False):
    """YYYY-MM-DD-HHh-HHh - PROGRAM NAME.mp3"""
    stem = "{}-{:02d}h-{:02d}h - {}".format(
        start_dt.strftime("%Y-%m-%d"), start_dt.hour, end_dt.hour, program
    )
    return sanitize(stem, ascii_only) + ".mp3"


def next_occurrence(grid_day, hour, now_brt):
    """Next datetime (Brasilia) matching this grid day + hour, strictly ahead."""
    target_wd = GRID_TO_PYWD[grid_day]
    delta = (target_wd - now_brt.weekday()) % 7
    candidate = now_brt.replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=delta)
    if candidate <= now_brt:
        candidate += timedelta(days=7)
    return candidate


def to_local(dt_brt):
    """Convert a Brasilia-aware datetime to the machine's local time."""
    return dt_brt.astimezone()


def local_tz_label():
    now = datetime.now().astimezone()
    off = now.utcoffset() or timedelta(0)
    total = int(off.total_seconds() // 60)
    sign = "+" if total >= 0 else "-"
    hh, mm = divmod(abs(total), 60)
    name = now.tzname() or "Local"
    return "{} (UTC{}{:02d}:{:02d})".format(name, sign, hh, mm)


def fmt_hhmm(dt):
    return dt.strftime("%H:%M")


def ffmpeg_command(ffmpeg, url, duration, outfile):
    return [
        ffmpeg, "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "30",
        "-i", url,
        "-t", str(int(duration)),
        "-c", "copy",
        "-f", "mp3",
        outfile,
    ]


def no_window_kwargs():
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": si, "creationflags": 0x08000000}  # CREATE_NO_WINDOW
    return {}


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class RadioSaveApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("{} {}".format(APP_NAME, APP_VERSION))
        self.geometry("1020x680")
        self.minsize(900, 600)

        self.log_q = queue.Queue()
        self.scheduler_thread = None
        self.stop_event = threading.Event()
        self.active_procs = []
        self.selected = set()          # {(grid_day, hour)}
        self.row_index = {}            # treeview iid -> (grid_day, hour)

        self.cfg = self.load_config()
        self.radios = self.cfg.get("radios") or list(DEFAULT_RADIOS)

        self.var_radio = tk.StringVar(value=self.cfg.get("radio", self.radios[0]["name"]))
        self.var_url = tk.StringVar()
        self.var_outdir = tk.StringVar(value=self.cfg.get("outdir", os.path.join(os.path.expanduser("~"), "RadioSave")))
        self.var_ffmpeg = tk.StringVar(value=self.cfg.get("ffmpeg", shutil.which("ffmpeg") or "ffmpeg"))
        self.var_pre = tk.IntVar(value=self.cfg.get("pre", 15))
        self.var_post = tk.IntVar(value=self.cfg.get("post", 30))
        self.var_ascii = tk.BooleanVar(value=self.cfg.get("ascii", True))
        self.var_nametz = tk.StringVar(value=self.cfg.get("nametz", "brasilia"))
        self.var_status = tk.StringVar(value="Idle.")
        self.var_hide_reruns = tk.BooleanVar(value=False)
        self.var_search = tk.StringVar()

        for key in self.cfg.get("selected", []):
            try:
                d, h = key.split(":")
                self.selected.add((int(d), int(h)))
            except Exception:
                pass

        self._build_ui()
        self.on_radio_change()
        self.refresh_grid()
        self.after(200, self.drain_log)
        self.after(1000, self.tick_clocks)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------- config ----------------

    def load_config(self):
        try:
            with open(config_path(), "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def save_config(self):
        data = {
            "radios": self.radios,
            "radio": self.var_radio.get(),
            "outdir": self.var_outdir.get(),
            "ffmpeg": self.var_ffmpeg.get(),
            "pre": self.var_pre.get(),
            "post": self.var_post.get(),
            "ascii": self.var_ascii.get(),
            "nametz": self.var_nametz.get(),
            "selected": ["{}:{}".format(d, h) for d, h in sorted(self.selected)],
        }
        try:
            with open(config_path(), "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
        except Exception as exc:
            self.log("Could not save settings: {}".format(exc))

    # ---------------- ui construction ----------------

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
        self.cmb_radio = ttk.Combobox(top, textvariable=self.var_radio, state="readonly",
                                      values=[r["name"] for r in self.radios], width=28)
        self.cmb_radio.grid(row=0, column=1, sticky="w", pady=6)
        self.cmb_radio.bind("<<ComboboxSelected>>", lambda e: (self.on_radio_change(), self.refresh_grid()))

        ttk.Button(top, text="Add...", width=9, command=self.add_radio).grid(row=0, column=2, padx=3)
        ttk.Button(top, text="Edit...", width=9, command=self.edit_radio).grid(row=0, column=3, padx=3)
        ttk.Button(top, text="Remove", width=9, command=self.remove_radio).grid(row=0, column=4, padx=3)

        ttk.Label(top, text="Stream URL:").grid(row=1, column=0, sticky="w", padx=6, pady=(0, 8))
        ent = ttk.Entry(top, textvariable=self.var_url, width=64)
        ent.grid(row=1, column=1, columnspan=3, sticky="we", pady=(0, 8))
        ttk.Button(top, text="Test 8s", width=9, command=self.test_stream).grid(row=1, column=4, padx=3, pady=(0, 8))
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
        ttk.Label(bar, textvariable=self.var_status).pack(side="left", padx=14)

    def _build_grid_tab(self):
        f = self.tab_grid
        ctr = ttk.Frame(f)
        ctr.pack(fill="x", pady=(8, 4))

        ttk.Label(ctr, text="Find:").pack(side="left", padx=(4, 4))
        e = ttk.Entry(ctr, textvariable=self.var_search, width=30)
        e.pack(side="left")
        e.bind("<KeyRelease>", lambda ev: self.refresh_grid())
        ttk.Checkbutton(ctr, text="Hide reruns (REPRISE)", variable=self.var_hide_reruns,
                        command=self.refresh_grid).pack(side="left", padx=12)
        ttk.Button(ctr, text="Select all shown", command=lambda: self.bulk(True)).pack(side="right", padx=4)
        ttk.Button(ctr, text="Clear all", command=self.clear_all).pack(side="right", padx=4)

        cols = ("chk", "day", "brt", "local", "prog")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", selectmode="none")
        self.tree.heading("chk", text="")
        self.tree.heading("day", text="Day (Brasilia)")
        self.tree.heading("brt", text="Brasilia")
        self.tree.heading("local", text="Your time")
        self.tree.heading("prog", text="Program")
        self.tree.column("chk", width=34, anchor="center", stretch=False)
        self.tree.column("day", width=110, anchor="w", stretch=False)
        self.tree.column("brt", width=95, anchor="center", stretch=False)
        self.tree.column("local", width=125, anchor="center", stretch=False)
        self.tree.column("prog", width=460, anchor="w")
        self.tree.tag_configure("orig", background="#eaf5ea")
        self.tree.tag_configure("sel", background="#cfe6ff")

        vs = ttk.Scrollbar(f, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        vs.pack(side="right", fill="y", pady=6, padx=(0, 6))
        self.tree.bind("<Button-1>", self.on_tree_click)

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

        self.var_conv_in = tk.StringVar(value="19:00")
        self.var_conv_dir = tk.StringVar(value="brt2local")
        self.var_conv_out = tk.StringVar(value="")

        ttk.Radiobutton(c, text="Brasilia -> my time", value="brt2local",
                        variable=self.var_conv_dir, command=self.do_convert).grid(row=0, column=0, sticky="w", padx=8, pady=6)
        ttk.Radiobutton(c, text="My time -> Brasilia", value="local2brt",
                        variable=self.var_conv_dir, command=self.do_convert).grid(row=0, column=1, sticky="w", padx=8)

        ttk.Label(c, text="Time (HH:MM):").grid(row=1, column=0, sticky="e", padx=8, pady=8)
        ce = ttk.Entry(c, textvariable=self.var_conv_in, width=10)
        ce.grid(row=1, column=1, sticky="w")
        ce.bind("<KeyRelease>", lambda ev: self.do_convert())
        ttk.Label(c, textvariable=self.var_conv_out, font=("Segoe UI", 11, "bold")).grid(
            row=1, column=2, sticky="w", padx=16)

        note = ("Brasilia is fixed at UTC-03:00 (Brazil dropped daylight saving in 2019).\n"
                "Your timezone is read from Windows, and the conversion accounts for your\n"
                "own DST on the actual date of each recording.")
        ttk.Label(f, text=note, foreground="#555").pack(anchor="w", padx=14, pady=10)
        self.do_convert()

    def _build_log_tab(self):
        f = self.tab_log
        ttk.Label(f, text="Upcoming recordings").pack(anchor="w", padx=8, pady=(8, 2))
        self.lst_queue = tk.Listbox(f, height=8)
        self.lst_queue.pack(fill="x", padx=8)
        ttk.Label(f, text="Log").pack(anchor="w", padx=8, pady=(10, 2))
        self.txt_log = tk.Text(f, height=14, wrap="word", state="disabled")
        self.txt_log.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _build_settings_tab(self):
        f = self.tab_set
        g = ttk.LabelFrame(f, text="Output")
        g.pack(fill="x", padx=10, pady=10)
        ttk.Label(g, text="Save folder:").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        ttk.Entry(g, textvariable=self.var_outdir, width=60).grid(row=0, column=1, sticky="we")
        ttk.Button(g, text="Browse...", command=self.pick_outdir).grid(row=0, column=2, padx=6)
        ttk.Label(g, text="ffmpeg:").grid(row=1, column=0, sticky="w", padx=8, pady=(0, 8))
        ttk.Entry(g, textvariable=self.var_ffmpeg, width=60).grid(row=1, column=1, sticky="we", pady=(0, 8))
        ttk.Button(g, text="Browse...", command=self.pick_ffmpeg).grid(row=1, column=2, padx=6, pady=(0, 8))
        g.columnconfigure(1, weight=1)

        n = ttk.LabelFrame(f, text="Filenames")
        n.pack(fill="x", padx=10, pady=6)
        ttk.Label(n, text="Pattern:  YYYY-MM-DD-HHh-HHh - PROGRAM NAME.mp3").grid(
            row=0, column=0, columnspan=3, sticky="w", padx=8, pady=(8, 4))
        ttk.Label(n, text="Times in filename:").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        ttk.Radiobutton(n, text="Brasilia (matches the grid)", value="brasilia",
                        variable=self.var_nametz).grid(row=1, column=1, sticky="w")
        ttk.Radiobutton(n, text="My local time", value="local",
                        variable=self.var_nametz).grid(row=1, column=2, sticky="w", padx=10)
        ttk.Checkbutton(n, text="Strip accents (safest for old players / USB sticks)",
                        variable=self.var_ascii).grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=(4, 8))

        p = ttk.LabelFrame(f, text="Padding (guards against clock drift and early starts)")
        p.pack(fill="x", padx=10, pady=6)
        ttk.Label(p, text="Start this many seconds early:").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        ttk.Spinbox(p, from_=0, to=300, textvariable=self.var_pre, width=6).grid(row=0, column=1, sticky="w")
        ttk.Label(p, text="Keep recording this many seconds past the hour:").grid(row=1, column=0, sticky="w", padx=8, pady=(0, 8))
        ttk.Spinbox(p, from_=0, to=600, textvariable=self.var_post, width=6).grid(row=1, column=1, sticky="w", pady=(0, 8))

        ttk.Label(f, text="Settings are saved automatically when you close the window.",
                  foreground="#555").pack(anchor="w", padx=14, pady=8)

    # ---------------- radio management ----------------

    def current_radio(self):
        for r in self.radios:
            if r["name"] == self.var_radio.get():
                return r
        return self.radios[0] if self.radios else {"name": "", "url": ""}

    def on_radio_change(self):
        self.var_url.set(self.current_radio().get("url", ""))

    def _radio_dialog(self, title, name="", url=""):
        dlg = tk.Toplevel(self)
        dlg.title(title)
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)
        vn, vu = tk.StringVar(value=name), tk.StringVar(value=url)
        ttk.Label(dlg, text="Station name:").grid(row=0, column=0, sticky="e", padx=8, pady=8)
        e1 = ttk.Entry(dlg, textvariable=vn, width=44)
        e1.grid(row=0, column=1, padx=8, pady=8)
        ttk.Label(dlg, text="Stream URL:").grid(row=1, column=0, sticky="e", padx=8, pady=(0, 8))
        ttk.Entry(dlg, textvariable=vu, width=44).grid(row=1, column=1, padx=8, pady=(0, 8))
        result = {}

        def ok():
            if not vn.get().strip() or not vu.get().strip():
                messagebox.showwarning(APP_NAME, "Both fields are required.", parent=dlg)
                return
            result["name"] = vn.get().strip()
            result["url"] = vu.get().strip()
            dlg.destroy()

        btns = ttk.Frame(dlg)
        btns.grid(row=2, column=0, columnspan=2, pady=(0, 10))
        ttk.Button(btns, text="OK", width=10, command=ok).pack(side="left", padx=5)
        ttk.Button(btns, text="Cancel", width=10, command=dlg.destroy).pack(side="left", padx=5)
        e1.focus_set()
        dlg.wait_window()
        return result or None

    def add_radio(self):
        r = self._radio_dialog("Add station")
        if not r:
            return
        if any(x["name"] == r["name"] for x in self.radios):
            messagebox.showwarning(APP_NAME, "A station with that name already exists.")
            return
        self.radios.append(r)
        self.cmb_radio["values"] = [x["name"] for x in self.radios]
        self.var_radio.set(r["name"])
        self.on_radio_change()
        self.refresh_grid()

    def edit_radio(self):
        cur = self.current_radio()
        r = self._radio_dialog("Edit station", cur["name"], cur["url"])
        if not r:
            return
        old = cur["name"]
        cur["name"], cur["url"] = r["name"], r["url"]
        if old in SCHEDULE and r["name"] != old:
            SCHEDULE[r["name"]] = SCHEDULE[old]
        self.cmb_radio["values"] = [x["name"] for x in self.radios]
        self.var_radio.set(r["name"])
        self.on_radio_change()
        self.refresh_grid()

    def remove_radio(self):
        if len(self.radios) <= 1:
            messagebox.showinfo(APP_NAME, "Keep at least one station.")
            return
        cur = self.current_radio()
        if not messagebox.askyesno(APP_NAME, "Remove '{}'?".format(cur["name"])):
            return
        self.radios.remove(cur)
        self.cmb_radio["values"] = [x["name"] for x in self.radios]
        self.var_radio.set(self.radios[0]["name"])
        self.on_radio_change()
        self.refresh_grid()

    # ---------------- grid ----------------

    def grid_for_current(self):
        return SCHEDULE.get(self.var_radio.get())

    def refresh_grid(self):
        self.tree.delete(*self.tree.get_children())
        self.row_index.clear()
        grid = self.grid_for_current()
        if not grid:
            self.tree.insert("", "end", values=(
                "", "", "", "",
                "No schedule stored for this station - use it as a manual stream, or add the grid in the source."))
            return

        needle = self.var_search.get().strip().lower()
        now_brt = datetime.now(BRT)
        for d, hours in enumerate(grid):
            for h, prog in enumerate(hours):
                if self.var_hide_reruns.get() and is_rerun(prog):
                    continue
                if needle and needle not in prog.lower():
                    continue
                nxt = next_occurrence(d, h, now_brt)
                loc = to_local(nxt)
                key = (d, h)
                checked = key in self.selected
                tags = ("sel",) if checked else (("orig",) if not is_rerun(prog) else ())
                iid = self.tree.insert("", "end", values=(
                    "X" if checked else "",
                    "{} / {}".format(DAYS[d], DAYS_EN[d][:3]),
                    "{:02d}:00".format(h),
                    "{} {}".format(DAYS_EN[(loc.weekday() + 1) % 7][:3], fmt_hhmm(loc)),
                    prog,
                ), tags=tags)
                self.row_index[iid] = key
        self.update_queue_view()

    def on_tree_click(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid or iid not in self.row_index:
            return
        key = self.row_index[iid]
        if key in self.selected:
            self.selected.discard(key)
        else:
            self.selected.add(key)
        vals = list(self.tree.item(iid, "values"))
        vals[0] = "X" if key in self.selected else ""
        prog = vals[4]
        self.tree.item(iid, values=vals,
                       tags=("sel",) if key in self.selected else (("orig",) if not is_rerun(prog) else ()))
        self.update_queue_view()

    def bulk(self, on):
        for iid, key in self.row_index.items():
            if on:
                self.selected.add(key)
            else:
                self.selected.discard(key)
        self.refresh_grid()

    def clear_all(self):
        self.selected.clear()
        self.refresh_grid()

    def update_queue_view(self):
        self.lst_queue.delete(0, "end")
        now_brt = datetime.now(BRT)
        grid = self.grid_for_current()
        items = []
        for d, h in self.selected:
            if not grid:
                continue
            prog = grid[d][h]
            start = next_occurrence(d, h, now_brt)
            items.append((start, prog))
        for start, prog in sorted(items)[:60]:
            loc = to_local(start)
            self.lst_queue.insert("end", "{}  (your time {})  -  {}".format(
                start.strftime("%a %Y-%m-%d %H:%M BRT"), loc.strftime("%a %d %H:%M"), prog))
        self.var_status.set("{} program(s) selected.".format(len(self.selected)))

    # ---------------- converter ----------------

    def do_convert(self):
        raw = self.var_conv_in.get().strip()
        m = re.match(r"^(\d{1,2})\s*[:hH]?\s*(\d{2})?$", raw)
        if not m:
            self.var_conv_out.set("--:--")
            return
        hh = int(m.group(1))
        mm = int(m.group(2) or 0)
        if hh > 23 or mm > 59:
            self.var_conv_out.set("--:--")
            return
        today = datetime.now()
        if self.var_conv_dir.get() == "brt2local":
            src = datetime.now(BRT).replace(hour=hh, minute=mm, second=0, microsecond=0)
            dst = src.astimezone()
            label = "= {} your time".format(dst.strftime("%H:%M"))
            if dst.date() > src.date():
                label += "  (next day)"
            elif dst.date() < src.date():
                label += "  (previous day)"
        else:
            local_now = today.astimezone()
            src = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            dst = src.astimezone(BRT)
            label = "= {} in Brasilia".format(dst.strftime("%H:%M"))
            if dst.date() > src.date():
                label += "  (next day)"
            elif dst.date() < src.date():
                label += "  (previous day)"
        self.var_conv_out.set(label)

    def tick_clocks(self):
        now_brt = datetime.now(BRT)
        self.lbl_brt.config(text="Brasilia:   {}".format(now_brt.strftime("%a %d %b %Y  %H:%M:%S")))
        loc = datetime.now().astimezone()
        self.lbl_loc.config(text="Your time:  {}   [{}]".format(
            loc.strftime("%a %d %b %Y  %H:%M:%S"), local_tz_label()))
        self.after(1000, self.tick_clocks)

    # ---------------- misc ui actions ----------------

    def pick_outdir(self):
        d = filedialog.askdirectory(initialdir=self.var_outdir.get() or os.path.expanduser("~"))
        if d:
            self.var_outdir.set(d)

    def pick_ffmpeg(self):
        f = filedialog.askopenfilename(title="Locate ffmpeg.exe",
                                       filetypes=[("ffmpeg", "ffmpeg.exe"), ("All files", "*.*")])
        if f:
            self.var_ffmpeg.set(f)

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
        url = self.var_url.get().strip()
        if not url:
            messagebox.showwarning(APP_NAME, "Enter a stream URL first.")
            return
        os.makedirs(self.var_outdir.get(), exist_ok=True)
        out = os.path.join(self.var_outdir.get(), "_streamtest.mp3")

        def run():
            self.log("Testing stream for 8 seconds...")
            cmd = ffmpeg_command(self.var_ffmpeg.get(), url, 8, out)
            try:
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=90, **no_window_kwargs())
                size = os.path.getsize(out) if os.path.exists(out) else 0
                if size > 5000:
                    self.log("Stream OK - captured {} KB. Test file: {}".format(size // 1024, out))
                else:
                    self.log("Test produced almost nothing. ffmpeg said: {}".format(
                        (p.stderr or "").strip()[:400] or "(no output)"))
            except FileNotFoundError:
                self.log("ffmpeg not found. Set its path on the Settings tab.")
            except Exception as exc:
                self.log("Test failed: {}".format(exc))

        threading.Thread(target=run, daemon=True).start()

    # ---------------- scheduler ----------------

    def start_scheduler(self):
        if not self.selected:
            messagebox.showinfo(APP_NAME, "Tick at least one program on the Schedule tab.")
            return
        if not self.var_url.get().strip():
            messagebox.showwarning(APP_NAME, "This station has no stream URL.")
            return
        if not shutil.which(self.var_ffmpeg.get()) and not os.path.exists(self.var_ffmpeg.get()):
            messagebox.showwarning(APP_NAME, "ffmpeg was not found.\nSet the path on the Settings tab.")
            return
        try:
            os.makedirs(self.var_outdir.get(), exist_ok=True)
        except Exception as exc:
            messagebox.showerror(APP_NAME, "Cannot create the save folder:\n{}".format(exc))
            return

        self.stop_event.clear()
        self.scheduler_thread = threading.Thread(target=self.scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.log("Scheduler started. Watching {} slot(s). You can minimise this window.".format(len(self.selected)))

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
        # Slots already handled, keyed by their exact start instant.
        fired = set()
        # How late we are still willing to join a programme that has begun.
        grace = timedelta(minutes=GRACE_MINUTES)

        while not self.stop_event.is_set():
            now_brt = datetime.now(BRT)
            grid = self.grid_for_current()
            if grid:
                for d, h in sorted(self.selected):
                    # Look up the occurrence from a point slightly in the past, so a
                    # slot whose hour has just started is still returned instead of
                    # silently rolling forward to next week.
                    start = next_occurrence(d, h, now_brt - grace)
                    launch_at = start - timedelta(seconds=int(self.var_pre.get()))
                    stamp = start.isoformat()
                    if stamp in fired:
                        continue
                    if launch_at <= now_brt < start + grace:
                        fired.add(stamp)
                        self.spawn_recording(d, h, start, grid[d][h])
            fired = {s for s in fired if datetime.fromisoformat(s) > now_brt - timedelta(hours=3)}
            self.stop_event.wait(2.0)

    def spawn_recording(self, day, hour, start_brt, program):
        pre = int(self.var_pre.get())
        post = int(self.var_post.get())
        end_brt = start_brt + timedelta(hours=1)

        if self.var_nametz.get() == "local":
            name_start, name_end = to_local(start_brt), to_local(end_brt)
        else:
            name_start, name_end = start_brt, end_brt

        fname = build_filename(name_start, name_end, program, self.var_ascii.get())
        outpath = os.path.join(self.var_outdir.get(), fname)
        base, ext = os.path.splitext(outpath)
        n = 2
        while os.path.exists(outpath):
            outpath = "{} ({}){}".format(base, n, ext)
            n += 1

        now_brt = datetime.now(BRT)
        duration = (end_brt - now_brt).total_seconds() + post
        if duration <= 0:
            self.log("Skipped '{}' - its hour has already passed.".format(program))
            return

        cmd = ffmpeg_command(self.var_ffmpeg.get(), self.var_url.get().strip(), duration, outpath)

        def run():
            self.log("RECORDING  {}  ->  {}  ({} min)".format(program, os.path.basename(outpath), int(duration // 60)))
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                     text=True, **no_window_kwargs())
                self.active_procs.append(p)
                _, err = p.communicate()
                if p in self.active_procs:
                    self.active_procs.remove(p)
                size = os.path.getsize(outpath) if os.path.exists(outpath) else 0
                if size > 100000:
                    self.log("DONE  {}  ({:.1f} MB)".format(os.path.basename(outpath), size / 1048576))
                else:
                    self.log("WARNING  {} is only {} bytes. ffmpeg: {}".format(
                        os.path.basename(outpath), size, (err or "").strip()[:300]))
            except FileNotFoundError:
                self.log("ffmpeg not found - recording aborted.")
            except Exception as exc:
                self.log("Recording error: {}".format(exc))

        threading.Thread(target=run, daemon=True).start()

    def on_close(self):
        if self.active_procs:
            if not messagebox.askyesno(APP_NAME, "A recording is still running. Quit anyway?"):
                return
        self.stop_event.set()
        for p in list(self.active_procs):
            try:
                p.terminate()
            except Exception:
                pass
        self.save_config()
        self.destroy()


def main():
    if sys.version_info < (3, 8):
        print("RadioSave needs Python 3.8 or newer.")
        sys.exit(1)
    RadioSaveApp().mainloop()


if __name__ == "__main__":
    main()

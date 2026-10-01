# RadioSave

Schedule-based internet radio recorder. Pick programs from the weekly grid and it
waits for them, records each one with ffmpeg, and names the file after the program.

## Running it

Copy `radiosave.py` to the other laptop and double-click it, or:

```
python radiosave.py
```

Needs Python 3.8+ and ffmpeg. Nothing to install — tkinter ships with Python on Windows.

If ffmpeg isn't on your PATH, point at `ffmpeg.exe` directly on the **Settings** tab.

## Tabs

**Schedule** — the full Rádio Atlan week, 168 slots. Click a row to tick it.
Green rows are first-run broadcasts; everything else is a rerun. "Hide reruns"
cuts the list to the 25 originals. The search box filters by program name, so
typing `orbum` shows every Projeto Orbum airing with its time in both zones.

**Time converter** — live Brasília and local clocks, plus a two-way HH:MM
converter. Flags when a conversion lands on the previous or next day.

**Queue & log** — next 60 scheduled recordings and a running log.

**Settings** — save folder, ffmpeg path, filename options, padding.

## Filenames

```
2026-08-02-19h-20h - PAINEIS DA REVELACAO COSMICA.mp3
```

Times default to Brasília so they line up with the published grid; switch to
local time on the Settings tab if you prefer. Accents are stripped by default
(safer on car stereos and USB sticks) — turn that off to keep `MÚSICA`.
Existing files are never overwritten; a `(2)` is appended instead.

## Stations

Rádio Atlan ships preloaded with `https://s30.maxcast.com.br:8157/live`. Add
your own with **Add...** — name and stream URL are saved and appear in the
dropdown. Use **Test 8s** to confirm a URL works before relying on it; it writes
`_streamtest.mp3` to your save folder and reports the captured size.

Other stations have no schedule grid stored, so the Schedule tab will say so.
To add one, extend the `SCHEDULE` dictionary near the top of `radiosave.py`
(7 lists of 24 titles, Sunday first).

## Padding

Recording starts 15 seconds early and runs 30 seconds past the hour by default,
which absorbs clock drift and stream buffering. Adjust on the Settings tab.

If the app is launched after a program has already started, it joins in progress
and records the remainder — up to 10 minutes late. Past that it skips the slot
rather than leaving you a truncated stub.

## Notes

Brasília is treated as a fixed UTC−03:00. Brazil abolished daylight saving in
2019, so this is correct and avoids depending on the `tzdata` package, which
Windows doesn't bundle. Your own timezone comes from Windows and *is* DST-aware,
evaluated for the actual date of each recording.

Settings and ticked programs are saved to
`%APPDATA%\RadioSave\config.json` when you close the window.

The laptop has to be awake and online at broadcast time — check your sleep
settings before relying on an overnight recording.

Schedule data came from radioatlan.com/programacao/, cross-checked against the
site's WordPress REST API. Stations do change their grids; if a recording comes
back with the wrong program, re-check the site.

Recording for personal listening is ordinary time-shifting. Don't redistribute
the files.

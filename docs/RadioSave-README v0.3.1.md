# RadioSave 0.3.1

Schedule-based internet radio recorder. Everything from 2.0 still works the same
way; this page covers only what changed.

Author: Luiz Junqueira & Claude AI — USEReira.ch@gmail.com
(also shown in the app on the About tab)

Needs Python 3.9+ and ffmpeg, plus one one-off install on Windows:

```
pip install tzdata
```

That package is the IANA time zone database. Without it RadioSave falls back to
fixed UTC offsets and warns you on startup — daylight saving would be wrong for
any station outside Brazil.

```
python radiosave_v3.py
```

---

## 1. Record extra minutes

Settings → **Recording padding**. Ticked by default, 5 minutes before and
5 minutes after.

A 19:00–20:00 entry is now captured from 18:55 to 20:05 — 70 minutes of audio.
The file is still named `2026-07-30-19h-20h - PROGRAM.mp3`, because the nominal
programme hours are what you want to sort and search by.

The old seconds-based padding (`Start this many seconds early` / `Keep recording
past the end`) is gone. Untick the box to record exactly the scheduled window.

Consecutive hourly entries now overlap by 10 minutes, which means two ffmpeg
processes pull the stream at once during the handover. That is deliberate — both
files get their full padding. The log notes it when it happens, in case a station
ever limits simultaneous connections.

## 2. Record Now

Button on the bottom bar, next to the scheduler controls. It opens a dialog with:

- **Length of each file** — 30 min, 1 h, 90 min, 2 h, 3 h or a custom number.
- **First cut at** — in radio time, pre-filled with the next whole hour.
- **Program name** — or leave the radio-name box ticked, which is the default.

Click Start at 10:30 with a 1 h length and a first cut of 11:00 and you get:

```
10:30 -> 11:00   (30 min)   <- starts immediately
11:00 -> 12:00   (60 min)
12:00 -> 13:00   (60 min)
...until you press Stop
```

The dialog previews exactly this before you commit. Files are named with the same
`YYYY-MM-DD-HHh-HHh - PROGRAM.mp3` pattern and the same live-metadata logic as a
scheduled recording — the station is sampled every 30 seconds and the dominant
title wins.

Padding applies here too: every cut after the first gets its 5 minutes on each
side. The very first file cannot have a "before" (the audio is already gone), so
it starts at the moment you click Start.

Record Now is independent of the scheduler — you can run both at once.

## 3. Per-station time zones

Each station now carries an IANA time zone, set in the Add/Edit station dialog
(the dialog shows that zone's current clock and offset as you pick). Schedule
times are stored as the station's own wall clock, so an entry that says 19:00
means 19:00 *there*, all year, and RadioSave works out what that is for you —
including summer time, which it reads from the tz database rather than assuming.

Change a station's zone and RadioSave offers to shift its existing entries so
they keep the same absolute moment, or leave the typed hours alone.

Existing schedules are unaffected: Rádio Atlan is seeded as `America/Sao_Paulo`,
which is the fixed UTC−3 that 2.0 hard-coded.

The Time converter tab follows the selected station: "Radio → my time" and
"My time → radio", with both live clocks labelled with their current offset.

## 3b. Nothing is thrown away  *(0.3.1)*

Press **Stop**, press **Stop Record Now**, or close the window, and the audio
captured so far is kept.

Before 0.3.1 the ffmpeg process was killed outright and the file went with it.
Now RadioSave sends ffmpeg a `q`, which is the same thing as pressing q in an
ffmpeg console: it closes the MP3 properly and exits, typically within a fifth of
a second. If ffmpeg ignores that for 8 seconds it is terminated, and killed 3
seconds after that — even then the partial file survives, because MP3 is a
frame stream with no trailer to miss.

A file that was cut short is named with a marker so you can tell at a glance:

```
2026-07-30-10h-11h - PROJETO ORBUM (INCOMPLETE).mp3
```

Its ID3 comment records the time it actually stopped. Closing the app shows a
small "Saving recordings in progress..." window while the files are finalised
and tagged; it never asks, it just saves, and gives up after 60 seconds in the
unlikely event something hangs.

Stopping the scheduler no longer stops a Record Now session, and vice versa —
they are independent.

## 3c. The Queue & log tab blinks  *(0.3.1)*

A blue square blinks next to the **Queue & log** tab name when a recording
starts, when one finishes, and when you tick or add schedule entries — so you
know the click registered and where to look. It stops the moment you open the
tab, or after 15 seconds.

The tab has also moved to sit directly after **Schedule**.

## 4. Schedule columns

`Start BRT` → **Start - Radio Time**
`End BRT` → **End - Radio Time**
`Your time` → **Start - Your Time**

The station's zone and both current clocks are shown above the Schedule tab.

## 5. Other changes

**ID3 tags.** Every finished file gets title (programme), album and artist
(station), date, genre and a comment recording the exact window captured. Written
with a stream copy, so nothing is re-encoded and it takes a second or two.

**Keep the machine awake.** While any recording is running, Windows is prevented
from sleeping or hibernating. Released as soon as the last one finishes. This is
the difference between a 03:00 capture existing and not existing.

**Settings saved immediately.** 2.0 only wrote the config file on a clean exit, so
a crash or a forced shutdown lost your schedule edits. 3.0 writes on every change,
atomically.

**Log file.** The log is also appended to `radiosave.log` in your save folder,
rotating at 2 MB. Turn it off in Settings → Extras.

**About tab.** Version, author and contact, plus a live check of the things
RadioSave depends on — Python, Tk, the ffmpeg build it found, whether the time
zone database loaded, and where your config file lives.

---

## Version history

- **0.3.1** — partial files are saved instead of discarded, Queue & log tab
  blinks and moves up, About tab.
- **0.3.0** — per-station time zones, extra-minutes padding, Record Now, ID3
  tags, immediate config saving, keep-awake.
- **2.0** — live metadata naming, editable schedule, multiple stations.

---

## Config file

`%APPDATA%\RadioSave\config.json`. A 2.0 config is read without complaint — the
old `pre`/`post` second values are dropped and replaced by the 5 + 5 minute
defaults, and every station gets `"tz": "America/Sao_Paulo"` unless you change it.

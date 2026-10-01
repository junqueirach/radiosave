# RadioSave 2.0

Schedule-based internet radio recorder. Pick or create entries, and RadioSave
waits for them, records with ffmpeg, and names each file after **what the radio
actually said was on air** — falling back to your schedule when the station
reports nothing.

Needs Python 3.8+ and ffmpeg. Standard library only, nothing to install.

```
python radiosave.py
```

---

## Naming files from the live broadcast

Rádio Atlan publishes its now-playing feed at

```
https://s30.maxcast.com.br/api/status/radioatlan/current.json
```

which returns `"playing": { "title": "Projeto Orbum - -" }`. That is the same
text the banner shows on the website, and — as you spotted — it frequently
disagrees with the published grid.

RadioSave samples that feed **every 30 seconds** for the whole recording,
collects the titles, and names the file after whichever one dominated. Sampling
rather than reading once matters, because a song or jingle mid-programme would
otherwise become the filename.

```
19:00  Projeto Orbum
19:12  Projeto Orbum
19:24  <a song title>
19:36  Projeto Orbum
19:48  Projeto Orbum      ->  winner: Projeto Orbum (4/5)
```

The file records under its scheduled name first and is **renamed when the
recording ends**, so a crash still leaves you an identifiable file. The log
reports what the radio said and how many samples agreed.

Order of precedence: the radio's title wins, the scheduled name is the fallback.
Flip it on the Settings tab. Entries with **"use the program name from the
radio"** ticked always take the radio's word.

### Other stations

Two sources are supported per station:

- **Status JSON** — for Maxcast/Icecast. Enter the URL, or type the station's
  slug and press *Build URL*.
- **ICY metadata** — read straight from the audio stream. No configuration and
  works on almost any Shoutcast/Icecast station, so try this first for a new one.

*Test now* in the station dialog shows what the radio reports right this second.

---

## Schedule tab

Every entry is editable. The Rádio Atlan grid is only a starting point — it is
copied into your config on first run, and after that it is yours.

| Action | How |
|---|---|
| Tick / untick | Click the first column |
| Edit | Double-click, right-click, or the **Edit...** button |
| Remove | Select rows, then **Remove**, right-click, or the Delete key |
| Add one | **Add...** |
| Add many | **Batch add...** |

Multi-select works with Ctrl and Shift, so you can remove or edit in bulk.

**Green rows are the programme on air right now** — nothing else is highlighted.
Blue text marks entries that take their name from the radio.

### Batch add

Tick the weekdays, give a range, choose a split, done. Your example — Wednesday
and Thursday, 09:00 to 15:00, split every 1 hour — creates 12 entries. *Preview*
shows exactly what you'll get before committing.

Times can be entered in **Brasília, your local time, UK, or a custom UTC
offset**, and are converted to station time on the way in. Conversions that
cross midnight move to the correct weekday: 01:00 Wednesday UK becomes 21:00
Tuesday in Brasília, and that's where the entry lands.

Ranges may cross midnight (23:00→02:00 gives you three entries spanning two
days). A ragged last chunk keeps its real length — 09:00→12:30 split hourly
gives 60/60/60/**30**.

Leave the program name blank and tick the radio-name box when you don't know
what's actually scheduled — which, on this station, is often.

---

## Queue & log

Lists the next 80 recordings. Select one and **Remove selected entry** deletes
that schedule entry outright.

---

## Filenames

```
2026-08-02-19h-20h - Projeto Orbum.mp3
```

Times default to Brasília so they match the grid; switch to local time in
Settings. Accents are stripped by default. Existing files are never overwritten
— a `(2)` is appended.

---

## Notes

Recording starts 15 s early and runs 30 s past the end by default. If RadioSave
starts after a programme has begun it joins in progress and keeps the remainder,
up to 10 minutes late; past that it skips rather than leaving a stub.

Brasília is treated as a fixed UTC−03:00 (Brazil dropped DST in 2019). Your own
timezone comes from Windows and is DST-aware. UK time follows the standard
BST rule (last Sunday in March to last Sunday in October).

Config, including all your entries, lives in `%APPDATA%\RadioSave\config.json`.
Back that file up once you've built a schedule you like.

The laptop must be awake and online at broadcast time.

Recording for personal listening is ordinary time-shifting. Don't redistribute.

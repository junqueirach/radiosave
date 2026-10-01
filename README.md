# RadioSave

**A schedule-based internet radio recorder for Windows, built for unattended 24/7 use.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE) ![Python](https://img.shields.io/badge/Python-3.9%2B-blue)

## What it does

- Records stations on a weekly schedule using ffmpeg and names each file `YYYY-MM-DD-HHh-HHh - PROGRAM.mp3`
- **Per-station time zones**: schedule in the station's own clock; daylight saving is handled from the IANA database
- **Extra minutes padding** (default 5 before and after) so programmes are never clipped
- **Record Now** with fixed-length cuts
- **Nothing is lost**: stopping or closing keeps the audio captured so far, marked `(INCOMPLETE)`
- **Working folder plus NAS**: records locally, then moves files with copy, size check and rename; unreachable NAS goes to a retry queue that survives restarts
- **Live metadata naming** and ID3 tags on every file
- **Keeps Windows awake** while recording
- **Control page on your local network** (off by default) to monitor and control from a phone
- Atomic config writes, rotating log, low-disk warning

## Quick start

```
pip install tzdata
python radiosave.py
```

Needs Python 3.9+ and ffmpeg. Full notes in [docs](docs), including a setup guide for an unattended Windows machine.

## Responsible use

Respect each station's terms and copyright law. Recordings are for personal use. The repository contains no recordings.

## Project facts

- About 3,700 lines of Python; versions 0.1.0 to 0.3.3 are in `archive/versions/` with the README for each release

---

## How this was built

Built with **Claude (Anthropic)** as the coding partner. I wrote the requirements and the revision prompts, tested every build on real data, and decided what to fix next. The `archive/versions/` folder keeps every earlier release so the iteration history is visible, and `prompts/` shows the briefs I gave Claude. See [ai-assisted-development](https://github.com/junqueirach/ai-assisted-development) for the method.

**Security note:** the app stores any API keys you enter in a local settings file outside this repository. `.gitignore` excludes config and settings files so keys are never committed.

## Licence

MIT. See [LICENSE](LICENSE).

## Author

Luiz Junqueira - [junqueira.ch](https://www.junqueira.ch) - [LinkedIn](https://www.linkedin.com/in/luizjunqueira/)

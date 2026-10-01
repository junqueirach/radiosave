# RadioSave on the HP ProDesk 400 G5 — 24/7 setup

Target: Windows 11 Pro, RadioSave running unattended, recordings landing on the
NAS, controlled from your own network over RDP and the built-in web page.

The hardware is far more than this needs. An i5-9500T records a 128 kbps stream
at roughly 1–2% CPU. What actually matters is that the box never reboots on its
own and never sleeps.

---

## 0. Check the BIOS before you install

Windows 11 will refuse to install if TPM or Secure Boot are off, and the error it
gives is unhelpful. Two minutes now saves an hour later.

Reboot, press **F10** at the HP logo:

| Setting | Where | Wanted |
|---|---|---|
| TPM Device / TPM State | Security → TPM Embedded Security | **Available / Enabled**, TPM 2.0 |
| Secure Boot | Security → Secure Boot Configuration | **Enabled** |
| Boot mode | Advanced → Boot Options | **UEFI**, not Legacy/CSM |

If TPM shows 1.2, switch it to 2.0 in the same menu — the G5 supports both and
ships either way depending on who configured it.

The disk must be **GPT**, not MBR. A clean install onto an empty disk does this
for you; if the SSD came out of another machine, delete all partitions in Windows
Setup and let it repartition.

### Does the hardware qualify?

| Requirement | Minimum | Your ProDesk |
|---|---|---|
| CPU generation | Intel 8th gen or newer | i5-9500T, 9th gen — **passes** |
| CPU instructions | SSE4.2 + POPCNT | Coffee Lake has both — **passes** |
| RAM | 4 GB | 16 GB — **4× over** |
| Storage | 64 GB | 1 TB SSD — **far over** |
| TPM | 2.0 | present, check it is enabled |
| Firmware | UEFI + Secure Boot | present, check it is enabled |
| Graphics | DirectX 12 / WDDM 2.0 | UHD 630 — **passes** |

Ignore reports that Microsoft dropped 8th–10th gen Intel support in 24H2. That
was a documentation error, corrected in February 2025; the processor list in
question is guidance for manufacturers building new machines, not a rule for
existing hardware. Windows 11 26H2 still supports Core 8th gen and up.

One honest caveat: 9th gen is now the oldest supported tier, and Microsoft's
direction of travel is clear. This machine will very likely not qualify for
whatever follows Windows 11. That is years away and irrelevant to a dedicated
recorder — but it is the argument for putting Debian on it instead, if you ever
want to revisit that.

---

## 1. Windows 11 **Pro**, not Home

Home cannot host Remote Desktop and cannot reach the group policy editor, which
is how you stop update reboots. Pay for Pro.

During setup choose **"Set up for personal use"**, then create a **local
account** (no Microsoft account). Offline is simpler for a machine that lives in
a cupboard: no OneDrive, no account sync, no surprise lock screens.

Name it something you will recognise on the network, e.g. `RADIOSAVE`.

---

## 2. Stop it rebooting itself

This is the single biggest threat to a 24/7 recorder. Two settings.

**a. Never auto-restart while someone is logged on**

Press `Win+R`, run `gpedit.msc`, then navigate to:

```
Computer Configuration
  └ Administrative Templates
      └ Windows Components
          └ Windows Update
              └ Manage end user experience
```

Set **"No auto-restart with logged on users for scheduled automatic updates
installations"** to **Enabled**.

Because the machine will be permanently auto-logged-in (step 5), this means
Windows will download and install updates but wait for *you* to restart.

**b. Defer feature updates**

In the same folder, under *Manage updates offered from Windows Update*, set
**"Select when Preview Builds and Feature Updates are received"** to Enabled,
with a deferral of **365 days**. Feature updates are the ones that take twenty
minutes and reboot twice.

**c. Once a month, restart it yourself**

Pick a dead hour, check nothing is recording, and reboot. Updates apply then.

---

## 3. Never sleep, never spin down

Settings → System → Power:

- Screen and sleep → **Never** for both
- Power mode → **Best performance**

Then in Control Panel → Power Options → Change plan settings → Change advanced
power settings:

- **Hard disk → Turn off hard disk after → 0 (Never)**
- **Sleep → Allow hybrid sleep → Off**, **Hibernate after → Never**
- **USB settings → USB selective suspend → Disabled**

RadioSave also holds a wake lock while recording (Settings → Extras → *Keep this
computer awake*), but belt and braces.

**Fast Startup off.** Control Panel → Power Options → Choose what the power
buttons do → Change settings that are currently unavailable → untick **Turn on
fast startup**. It interferes with clean boots after a power cut.

---

## 4. Power on again after a power cut

This is a BIOS setting, not Windows. Reboot, press **F10** at the HP logo, then:

```
Advanced → Power Management Options → After Power Loss → Power On
```

Save and exit. Now a blackout at 3am does not mean a dead machine until you
notice.

While you are in there, also check **Advanced → Boot Options → Fast Boot** is on
to shorten the restart, and that **Wake on LAN** is enabled if you ever want to
power it up remotely.

---

## 5. Auto-login and auto-start

RadioSave has a window, so it needs a logged-in desktop session.

**Auto-login.** `Win+R` → `netplwiz` → untick **"Users must enter a user name
and password to use this computer"** → OK → type the password twice.

> If that checkbox is missing (common on Windows 11), open `regedit`, go to
> `HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\PasswordLess\Device`,
> set `DevicePasswordLessBuildVersion` to `0`, then reopen `netplwiz`.

**Auto-start.** Press `Win+R`, run `shell:startup`, and drop a shortcut to
`RadioSave.bat` in the folder that opens. It launches at login, which now
happens at boot.

That is what you asked for — no watchdog. If you later want the app relaunched
when it crashes, tell me and I will add a Task Scheduler entry with a restart
policy instead.

---

## 6. Python, ffmpeg, tzdata

Install **Python 3.12** from python.org. On the first screen tick **"Add
python.exe to PATH"**.

Then in a terminal:

```
pip install tzdata
```

**ffmpeg**: download a build from gyan.dev (`ffmpeg-release-essentials.zip`),
extract to `C:\ffmpeg`, and either add `C:\ffmpeg\bin` to PATH or just point
RadioSave at `C:\ffmpeg\bin\ffmpeg.exe` on the Settings tab.

Check both on the RadioSave **About** tab — it reports the Python version, the
ffmpeg build it found, and whether the time zone database loaded.

---

## 7. The NAS

RadioSave now records to a local folder and moves each finished file to the NAS.
That way a NAS reboot or a network blip mid-programme cannot damage a recording.

**Working folder** (Settings → Output): `C:\RadioSave\work`
**Final folder**: `\\NAS\Radio` — type the UNC path directly.

> Use the UNC path, not a mapped drive letter. Mapped drives belong to an
> interactive session and behave unpredictably for anything running unattended.

**Make the credentials survive a reboot.** Open Credential Manager → Windows
Credentials → **Add a Windows credential**:

```
Internet or network address:  NAS            (the hostname, as in \\NAS\Radio)
User name:                    your NAS user
Password:                     your NAS password
```

Also give the NAS a **fixed IP or a DHCP reservation** in your router. If the NAS
address moves, the UNC path breaks silently.

Press **Test now** next to the final folder in Settings. It writes and deletes a
probe file and reports free space.

If the NAS is unreachable when a recording finishes, the file stays in the
working folder, appears as *"n files waiting to move"* in the status bar and on
the web page, and is retried every 5 minutes and again at startup. Nothing is
lost.

**Sizing:** at 128 kbps, an hour is about 56 MB, so 24/7 is roughly 1.3 GB a day
and 40 GB a month. The 1 TB SSD is a generous buffer; the NAS is where the
archive lives.

---

## 8. Remote control from your network

**Remote Desktop.** Settings → System → Remote Desktop → **On**. Connect from
another PC with the Remote Desktop app, from a Mac or iPad with *Microsoft
Remote Desktop*, using `RADIOSAVE` or its IP.

Give the ProDesk a **DHCP reservation** in your router so its address never
changes.

> RDP disconnects the local console session. That is fine — RadioSave keeps
> running and keeps recording. Do not *sign out*, just close the RDP window.

**The web page.** Settings → *Control page on your network* → tick it. The app
shows the address, e.g. `http://192.168.1.50:8080`. Open it from a phone on the
same Wi-Fi.

It shows what is capturing now with a progress bar, upcoming recordings, the
schedule with tick boxes, the live log, pending NAS moves and free disk space —
and it can start and stop the scheduler and Record Now.

Windows will ask to allow Python through the firewall the first time. Choose
**Private networks only**. If you miss the prompt, in an admin PowerShell:

```powershell
New-NetFirewallRule -DisplayName "RadioSave web" -Direction Inbound `
  -LocalPort 8080 -Protocol TCP -Action Allow -Profile Private
```

**There is no password on that page.** Anyone on your network can stop a
recording. That was your choice and it is reasonable for a home LAN — just do
not forward port 8080 on your router, and do not enable it on a network you
share with guests.

---

## 9. Sanity check before you walk away

1. About tab — Python, ffmpeg, time zones and the final folder all look right
2. **Test 8s** on the station — captures a few hundred KB
3. **Test now** on the final folder — reachable and writable
4. Tick one entry that starts in a few minutes, press **Start scheduler**
5. Watch the Queue & log tab blink, then confirm the file lands on the NAS
6. Open the web page from your phone and confirm the recording shows there
7. Pull the power cord. It should come back on its own, log in, and relaunch
   RadioSave

Step 7 is the one people skip and regret.

---

## 10. What is not automated

You declined these; say the word and I will add them.

- **Crash watchdog** — nothing relaunches RadioSave if the process dies
- **Scheduler auto-arming** — after a reboot the app starts, but you must press
  *Start scheduler* yourself, or do it from the web page
- **Local safety copies** — files are deleted from the SSD once the NAS confirms
  the copy

Given the machine is unattended, the first two are worth reconsidering. A single
Task Scheduler entry covers both.

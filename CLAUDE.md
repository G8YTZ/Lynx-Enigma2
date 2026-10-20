# Lynx-Enigma2: notes for Claude

Lynx for Enigma2 satellite receivers: watch UK amateur TV repeaters on a shop-bought box. Owner: Justin Cockett, G8YTZ (broadcast engineer, GB3OO repeater keeper). Sister projects: G8YTZ/lynx-datv-receiver (Pi receiver, GPL-3) and G8YTZ/Lynx-DATV-Tx (ROCK 5T transmitter, GPL-3). This repo is **GPL-2.0-or-later**, because the plugin runs inside Enigma2 (GPL-2).

## Style

British English, metric. No long dashes (use a colon, semicolon, comma, brackets or a new sentence). In documents: a capital letter after a colon. Direct, no padding. Question Justin's approach and suggest better ones, but go with his decision once made. Commit and push to main as you go.

## Where it stands (20 Oct 2026)

- `plugin/LynxRepeaters/`: The plugin (plan steps 1 to 4). **Works on the box (20 Oct 2026):** Lynx-Tx on 1312 MHz at 1000 kS/s, picked as GB3EN in the list, scanned, locked and played. So `eComponentScan` hookup and `newService` work on this OpenATV.
  - `repeaters.py`: The arithmetic (band, LNB, box frequency, locator, distance, list rows). No Enigma2 imports.
  - `tuning.py`: `RepeaterTuner`: stop the service, `eComponentScan` of one transponder per symbol rate (flags keep the rest of the service list), collect refs from `newService`, play the first TV type; watchdog 20 s per rate. `signal()` reads SNR from `frontendInfo().getFrontendStatus()`.
  - `screens.py`: `RepeaterList` (OK/green watch on air, yellow watch BATC stream on LIVE rows, blue settings, MENU everything incl. the symbol-rate hunt), `LynxBar` (bottom strip while watching), `LynxSettings` (`config.plugins.lynxrepeaters`). Skins drawn at 1920x1080, scaled by `_scale()`.
  - `streams.py`: BATC live list (same API and filters as Lynx Rx), matched to repeaters by callsign; RTMP address always built as `rtmp://rtmp.batc.org.uk/live/<name>` (names checked against `[A-Za-z0-9_.-]`); "BATC Live" bouquet `userbouquet.lynx_batc.tv` added to `bouquets.tv`; cache `/etc/enigma2/lynx_streams.json`. Unverified HTTPS only as a fallback when the box lacks CA certificates.
  - `sync.py`: `StreamSync`, hourly, first check a minute after boot; network in a worker thread, files and `reloadBouquets()` on Enigma2's thread; keeps the last list on error.
  - `plugin.py`: Descriptor, Plugins and Extensions menus, session start (stream sync, Open Lynx at start-up).
  - The Lynx bar shows the broadcast (SDT) name live, large, with the list's callsign, town and distance beside it.
- `data/repeaters.json`: 31 repeaters, 27 watchable outputs. `tools/deploy.sh` copies it beside the plugin.
- `tests/test_plugin.py`: List and tuner logic against stand-ins for Enigma2 (`tests/fake_enigma.py`).
- Next: **First run on the box** (`tools/deploy.sh`, then watch GB3OO; `tools/foreground.sh` for the traceback if it fails). Still to confirm: that a rescan of a known transponder plays again, the SNR shown on the Lynx bar, the symbol-rate hunt, skin look. BATC streams are written (20 Oct) but not yet run on the box; Streams play via exteplayer3 (5002); the built-in 4097 player is flaky. The box's clock is now right (NTP working). Then plan step 5.

## The test box

Zgemma H11S, OpenATV, at **192.168.0.164** (it was .163; DHCP). Root SSH has no password; OpenWebif API at `http://192.168.0.164/api/...` (`getcurrent`, `tunersignal`). Justin can run commands on it from his Mac. Back it up (OpenATV full image) before changing anything system-wide.

**Python 2.7.16, no Python 3** (an older OpenATV, kernel from April 2021). All plugin code must run on Python 2.7 and 3: no type hints, f-strings or `open(encoding=)`; `from __future__ import absolute_import, division, print_function`; check with `parso==0.7.1` (`load_grammar(version="2.7")`). **`4097:` streams go to HiSilicon's own player (`eServiceHisilicon`), not GStreamer**, and it often gives sound without picture on live RTMP (H.264 GB3HV included): it probes too briefly to see the first keyframe. **ServiceApp** (`enigma2-plugin-systemplugins-serviceapp`, `exteplayer3`, `gstplayer`, from the OpenATV feed; installed 20 Oct 2026) fixes most: type **5002** (exteplayer3) much better. Lynx uses 5002 automatically when ServiceApp and `/usr/bin/exteplayer3` are there (setting "Player for streams"). GB3NQ still no video on the box: even `ffprobe` on a Mac finds only AAC in its stream at its default probe length, though VLC shows a picture, and with `-analyzeduration 20M -probesize 20M` it finds H.264 1920x1080: **its keyframes are too far apart for the players' probe** (source side; fix is a ~2 s keyframe interval at GB3NQ).

**Tuner:** Montage RS6060, DVB-S2X, blind scan supported (`/proc/bus/nim_sockets`). No demodulator status in `/proc/msp` or `/proc/stb/frontend/0` (only current limiting). **Its tuner driver echoes the request:** `frontendInfo().getAll(False)` after lock gives back FEC, pilot, inversion as auto and system/modulation as asked, so none of those are measured. Symbol rate is safe (it only locks if right); picture size comes from the decoder and is right (3840x2160 seen). The Lynx bar shows system, modulation and FEC only when the driver reports a real FEC.

Proven on it: DVB-S2 on 23 cm straight into the satellite tuner, **1000 kS/s and up** (lower is unreliable). 19 dB SNR from Lynx-Tx at 2000 kS/s.

## How Enigma2 sees 23 cm (measured on the box)

- Tuner A is factory "advanced", a universal LNB at **position 192 (Astra 19.2E)**: 9750 MHz oscillator, low band, no 22 kHz tone. A signal arriving at IF MHz is tuned by asking for **IF + 9750 MHz**. GB3OO at 1304 MHz is stored as 11054000 kHz. `repeaters.box_frequency_khz()` does this; nothing in the box's tuner set-up needs changing.
- lamedb transponder for GB3OO: `s 11054000:2000000:0:0:192:2:0:1:1:0:2` (freq:SR:pol H:FEC auto:pos:inversion auto:flags:S2:QPSK:roll-off:pilot auto).
- Service: ONID 0xFF01, TSID 1, SID 1; namespace `0x00C02B2E` = position 192 << 16 | 11054 (MHz) & 0xFFFF. Ref `1:0:1:1:1:FF01:C02B2E:0:0:0:`.
- Repeaters' SID/TSID/ONID are **not published**, so the plugin does not pre-build channels: it **scans the one transponder** (a second or two) and plays what it finds. For an unknown symbol rate it tries `COMMON_SR_KS` in turn.
- **LNB power stays ON.** Justin, like many, feeds small inline preamps from the LNB supply. Horizontal = 18 V, vertical = 13 V (default vertical is fine and cooler). Make it a setting; never switch it off by default.
- The box takes DVB-S or DVB-S2 without being told; FEC auto.

## Bands (decided)

| Band | Into the box | Oscillator |
|---|---|---|
| 23 cm | Direct | none |
| 9 cm | C-band LNB, spectrum inverted (S2 copes) | 5150 MHz |
| 3 cm | LNB with a 9 GHz oscillator (Justin has one); a 9750 LNB puts 10 GHz repeaters at 315 to 490 MHz, below the tuner | 9000 MHz |

Oscillators are per-band settings. 13 cm (GB3TZ) is out. Analogue outputs and anything below 1000 kS/s are left off the list.

## Repeater data

- **ukrepeater.net (RSGB ETCC) is the authority** for frequency, location, locator, lat/lon, keeper and status. List: `https://ukrepeater.net/tvrepeaterlist.html`. Each callsign links to `https://ukrepeater.net/my_repeater.php?id=<n>` (GB3OO 6597, GB3HV 4836, GB3DO 4948), which adds **ERP (dBW), TX antenna height**, NoV dates and region, but its "modes" just says "Television": **no symbol rate or FEC.** Change feed: `https://rsgb.online/ukrepeaters.xml`.
- **Symbol rate and FEC** come from the BATC wiki per-repeater pages (free text, patchy; raw wikitext at `https://wiki.batc.org.uk/index.php?title=<CALL>&action=raw`) and from Justin's corrections (marked `"source": "G8YTZ, <date>"` in the JSON; they win). Unreadable/empty wiki pages so far: GB3DO, GB3FV, GB3FW, GB3TG, GB3TT, GB3TV, GB3XY.
- This cloud session cannot fetch ukrepeater.net or the BATC wiki directly (and WebFetch refuses unseen URLs); ask Justin to run `curl` on his Mac and paste (`... | pbcopy`).
- Plan: the repo holds the checked list; a generator only *flags* changes (ETCC status/frequency, BATC edits) for a person to accept.
- Later: blind scan (the RS6060 supports it) could find an unknown symbol rate in one pass instead of the hunt.
- Later: ERP and height + distance to rank "likely receivable", not just nearest.

## Plugin plan

1. Repeater screen (Enigma2 `Screen`, Python 2.7 and 3): list by distance, status shown, 3 cm marked "needs a 9 GHz LNB".
2. Tune: build the transponder, one-transponder scan, zap to the first TV service found; SR hunt if unknown.
3. On screen: callsign, town, distance, signal (SNR from the frontend).
4. Settings: locator, per-band LNB oscillator, LNB voltage (13/18 V).
5. List update from GitHub; then an installable `.ipk`, then a ready-made box image to sell. Justin would be the support desk: keep set-up minimal.

Test by running `tools/deploy.sh [box]` on Justin's Mac: it copies the plugin and list to `/usr/lib/enigma2/python/Plugins/Extensions/LynxRepeaters/` and restarts the GUI (`/sbin/init 4`, `killall -9 enigma2`, `/sbin/init 3`), clearing stray `enigma2` copies. `tools/foreground.sh` runs the GUI in the terminal for tracebacks (log in `~/lynx-run.log`); **never leave a foreground `enigma2` running**: three copies at once hung the box on 20 Oct. **SSH's PATH on the box has no `/sbin`**: use full paths. The box's clock was about 5 years slow until NTP was switched on (20 Oct 2026); now right.

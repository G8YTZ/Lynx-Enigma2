# Lynx-Enigma2: notes for Claude

Lynx for Enigma2 satellite receivers: watch UK amateur TV repeaters on a shop-bought box. Owner: Justin Cockett, G8YTZ (broadcast engineer, GB3OO repeater keeper). Sister projects: G8YTZ/lynx-datv-receiver (Pi receiver, GPL-3) and G8YTZ/Lynx-DATV-Tx (ROCK 5T transmitter, GPL-3). This repo is **GPL-2.0-or-later**, because the plugin runs inside Enigma2 (GPL-2).

## Style

British English, metric. No long dashes (use a colon, semicolon, comma, brackets or a new sentence). In documents: a capital letter after a colon. Direct, no padding. Question Justin's approach and suggest better ones, but go with his decision once made. Commit and push to main as you go.

## Where it stands (20 Oct 2026)

- `src/repeaters.py`: The arithmetic (band, LNB, box frequency, locator, distance, which outputs a box can show). No Enigma2 imports, so it tests on any PC.
- `data/repeaters.json`: 31 repeaters, 27 watchable outputs.
- Next: **the plugin itself.** A "UK ATV Repeaters" screen listing repeaters by distance from the user's locator; OK tunes the chosen one and plays it.

## The test box

Zgemma H11S, OpenATV, at **192.168.0.164** (it was .163; DHCP). Root SSH has no password; OpenWebif API at `http://192.168.0.164/api/...` (`getcurrent`, `tunersignal`). Justin can run commands on it from his Mac. Back it up (OpenATV full image) before changing anything system-wide.

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
- Later: ERP and height + distance to rank "likely receivable", not just nearest.

## Plugin plan

1. Repeater screen (Enigma2 `Screen`, Python 3 on OpenATV): list by distance, status shown, 3 cm marked "needs a 9 GHz LNB".
2. Tune: build the transponder, one-transponder scan, zap to the first TV service found; SR hunt if unknown.
3. On screen: callsign, town, distance, signal (SNR from the frontend).
4. Settings: locator, per-band LNB oscillator, LNB voltage (13/18 V).
5. List update from GitHub; then an installable `.ipk`, then a ready-made box image to sell. Justin would be the support desk: keep set-up minimal.

Test by copying files to the box over SSH (`/usr/lib/enigma2/python/Plugins/Extensions/LynxRepeaters/`) and restarting the GUI (`init 4; init 3`, or the OpenWebif restart).

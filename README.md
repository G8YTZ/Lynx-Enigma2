# Lynx-Enigma2

Lynx for Enigma2 satellite receivers: watch UK amateur TV repeaters on a shop-bought box, with every repeater listed and ready to tune, and their BATC streams too.

Part of the Lynx family, with the [Lynx DATV Receiver](https://github.com/G8YTZ/lynx-datv-receiver) and [Lynx-Tx](https://github.com/G8YTZ/Lynx-DATV-Tx).

**Status: Working, in testing.** Proven on a Zgemma H11S with OpenATV 8.0.1: 23 cm DVB-S2 straight into the box's satellite tuner from 1000 kS/s up, 4K HEVC on air, BATC streams, channel hopping between the two.

## The idea

A satellite receiver's tuner covers 950 to 2150 MHz, so 23 cm repeaters go straight in, and the box already decodes HEVC to HDMI. What it lacks is knowing where the repeaters are. Lynx adds:

- **Every UK repeater, ready to tune:** From the RSGB ETCC list (frequencies, locations, status) and the BATC wiki (symbol rates), sorted by distance from you.
- **Pick and watch:** Choose a repeater and the box finds its programme by itself; no channel numbers, and it still works if a repeater changes its service name or IDs.
- **BATC streams:** Repeaters streaming on the BATC streamer are marked LIVE and play over the internet, so you can see a repeater beyond radio range, or check it is on before pointing an antenna.
- **Lynx on screen:** The broadcast name, callsign, town, distance, frequency, symbol rate, picture size, LNB supply and live SNR.
- **Other bands** (3.4 and 10 GHz) through a suitable LNB, each with its own local oscillator.

LNB power stays on, to feed the small inline preamplifiers that run from it.

## 1. Setting up the box

Tested on a Zgemma H11S. Other Enigma2 boxes with a DVB-S2 tuner should work the same way.

1. **A current image:** OpenATV 8 or later (7.x is end of life). Older images (Python 2, 2021 and before) run Lynx, but their stream players miss the picture on many BATC streams.

   On a multiboot box such as the H11S, put OpenATV 8 in a spare slot, so the old image stays as it was: **Menu, Setup, Software Management, Flash online**, the newest OpenATV 8 build for your box, then a free slot.

   Flash online needs a USB stick or disc to download to; without one it says "could not find suitable media". Then flash from a PC over SSH instead. For the H11S, the newest `_multi.zip` is at `images.mynonpublic.com/openatv/8.0/zgemmah11s/`:
   ```
   ssh root@<box> 'mkdir -p /home/root/flash && cd /home/root/flash && wget -O image.zip <multi.zip address> && unzip -o image.zip'
   ssh root@<box> 'nohup /usr/bin/ofgwrite -r -k -m2 /home/root/flash/h11 > /home/root/flash/ofgwrite.log 2>&1 &'
   ```
   `-m2` writes slot 2 and leaves the others alone. When the screen says it has flashed, choose slot 2 in the **Multiboot Image Selector** (Menu, Standby / Restart) and work through the setup wizard. No channel scan is needed.

2. **Tuner:** **Menu, Setup, Tuner Configuration, Tuner A**: configuration mode **Simple**, **Single**, satellite **Astra 1KR/1L/1M/1N (19.2E)**, then save. Check this even after the wizard: on OpenATV 8 it can leave tuner A "not configured", and Lynx cannot tune anything until it is set (it says so). Nothing else needs changing for 23 cm; Lynx works out the frequencies.

3. **Time:** **Menu, Setup, System, Time**: time synchronisation by NTP. Lynx also puts the clock right after a power cut, since the box has no battery-backed clock.

4. **Stream players:** ServiceApp with gstplayer and exteplayer3, from the box's own feed. From a PC:
   ```
   ssh root@<box> 'opkg update && opkg install enigma2-plugin-systemplugins-serviceapp gstplayer exteplayer3'
   ```
   Without them the box's own player is used for streams, and on the H11S most streams then give sound without a picture.

## 2. Installing Lynx

You need a Mac or Linux PC (on Windows, use WSL) with `git` and `ssh`, on the same network as the box. The box's root login over SSH has no password by default.

1. **Get Lynx:**
   ```
   git clone https://github.com/G8YTZ/Lynx-Enigma2.git
   cd Lynx-Enigma2
   ```
   The repository is private for now: ask G8YTZ for access.

2. **Put it on the box:**
   ```
   tools/deploy.sh <box address>
   ```
   This copies Lynx to `/usr/lib/enigma2/python/Plugins/Extensions/LynxRepeaters/` and restarts the box's GUI.

3. **First run:** Open **Plugins, UK ATV Repeaters**. Press **blue** for Settings, enter your locator (such as JO01 or JO01AJ), and switch on **Open Lynx at start-up** if the box is to be a repeater receiver first. Save with **green**.

## 3. Updating

**Lynx:** In the `Lynx-Enigma2` folder on the PC:
```
git pull
tools/deploy.sh <box address>
```
Your settings stay as they are: they live in the box's own settings file, not in the plugin folder. The repeater list comes with Lynx, so updating Lynx updates the list too. The BATC stream list updates itself every hour.

**The box's own software:** **Menu, Setup, Software Management, Software update** updates OpenATV, ServiceApp and the players from the feed. Lynx is not part of the feed, so an update leaves it alone; if Lynx ever goes missing after one, run `tools/deploy.sh` again.

**Removing Lynx:**
```
ssh root@<box> 'rm -rf /usr/lib/enigma2/python/Plugins/Extensions/LynxRepeaters; /sbin/init 4; sleep 2; /sbin/init 3'
```

## 4. Using Lynx

**The list:**
- **OK or green:** Watch the highlighted repeater on air. Lynx scans its one transponder and plays the programme it finds.
- **Yellow:** Watch its BATC stream instead (repeaters marked LIVE).
- **Blue:** Settings: locator, LNB supply (13 V vertical or 18 V horizontal), the 9 cm and 3 cm LNB oscillators, whether to show repeaters listed as off air, Open Lynx at start-up, the BATC live streams, and the player for streams.
- **MENU:** Every choice in one place, including watching on air while trying every symbol rate (for a listed rate that is wrong), checking BATC now, and **Leave Lynx**.
- **EXIT or red** (**Stop** or **Close menu**): Stops a tune in progress, or takes you back to the picture. Left alone for 10 seconds while something is playing, the list goes back to the picture by itself.
- **Stream only:** Repeaters on the BATC streamer but not on the UK list (DB0OZ Bremen, say) are at the end; OK or yellow watches them.

**The Lynx bar,** while watching:
- **CH+ and CH-** (or up and down): The next or previous repeater in the list, by the same route (on air or stream). Keep pressing to scroll; each press moves straight on.
- **OK:** Hides or shows the bar.
- **Yellow,** on a stream: Swaps between gstplayer and exteplayer3, for a stream that gives sound but no picture.
- **EXIT:** Back to the list.

**Leaving Lynx:** Only through **MENU, Leave Lynx**, so a stray press never throws you out. What is playing carries on.

**BATC Live:** Lynx also keeps a **BATC Live** channel list, refreshed every hour, so live streams can be watched from the box's ordinary channel list.

## 5. Troubleshooting

- **"No tuner set up":** Tuner A is not configured; see step 2 of setting up.
- **"No signal" on a repeater you can receive:** Its listed symbol rate may be wrong. Use **MENU, Watch ... trying every symbol rate**.
- **Sound but no picture on a stream:** Press **yellow** on the bar to try the other player, or select the stream again: these players can miss the picture when they join a stream between keyframes. A stream whose keyframes are far apart (GB3NQ, October 2026) can stay sound-only; that is for its keeper to fix.
- **Lynx's log:** `ssh root@<box> cat /tmp/lynx.log` (cleared at each restart).

## For developers

Tests run on any PC: `python3 tests/test_plugin.py`. The code must run on Python 2.7 and 3, for older images. `CLAUDE.md` holds the working notes: how Enigma2 sees 23 cm, the box's quirks, and the decisions so far.

## Licence

GNU General Public License, version 2 or (at your option) any later version, like Enigma2 itself. See [LICENSE](LICENSE).

Justin Cockett, G8YTZ

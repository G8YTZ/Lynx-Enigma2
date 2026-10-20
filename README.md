# Lynx-Enigma2

Lynx for Enigma2 satellite receivers: watch UK amateur TV repeaters on a shop-bought box, with every repeater listed and ready to tune, and their BATC streams too.

Part of the Lynx family, with the [Lynx DATV Receiver](https://github.com/G8YTZ/lynx-datv-receiver) and [Lynx-Tx](https://github.com/G8YTZ/Lynx-DATV-Tx).

**Status: Working, in testing.** Proven on a Zgemma H11S with OpenATV 8.0.1: 23 cm DVB-S2 straight into the box's satellite tuner from 1000 kS/s up, 4K HEVC on air, BATC streams, channel hopping between the two.

## The idea

A satellite receiver's tuner covers 950 to 2150 MHz, so 23 cm repeaters go straight in, and the box already decodes HEVC to HDMI. What it lacks is knowing where the repeaters are. Lynx adds:

- **Every UK repeater, ready to tune:** From the RSGB ETCC list (frequencies, locations, status) and the BATC wiki (symbol rates), sorted by distance from you.
- **Pick and watch:** Choose a repeater and the box finds its programme by itself; no channel numbers, and it still works if a repeater changes its service name or IDs.
- **BATC streams:** Repeaters streaming on the BATC streamer are marked LIVE and play over the internet, so you can see a repeater beyond radio range, or check it is on before pointing an antenna.
- **Lynx on screen:** The broadcast name, callsign, town, distance, frequency, symbol rate, picture size and LNB supply, with the real modulation and FEC, signal level, SNR and margin read from the demodulator, and a **magic eye** for pointing antennas.
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

4. **Stream players:** Lynx's installer adds ServiceApp with gstplayer and exteplayer3 from the box's own feed, so there is nothing to do here. Without them the box's own player is used for streams, and on the H11S most streams then give sound without a picture.

## 2. Installing Lynx

Lynx installs from the box itself, over the network. You need a way to type commands on the box:

- **Mac or Linux:** Open Terminal and type `ssh root@<box address>`.
- **Windows 10 or 11:** Open PowerShell and type the same.

The box's address is under **Menu, Setup, System, Network**. OpenATV's root login has no password; answer `yes` if asked whether to trust the box the first time.

Then, on the box:
```
opkg update && opkg upgrade
wget -qO- https://raw.githubusercontent.com/G8YTZ/Lynx-Enigma2/main/tools/install.sh | sh
```
The first line brings the box's own software up to date. The second installs the stream players, downloads the latest Lynx from GitHub, installs it and restarts the box's GUI. Then open **Plugins, UK ATV Repeaters**, press **blue** for Settings, enter your locator (such as JO01 or JO01AJ), and switch on **Open Lynx at start-up** if the box is to be a repeater receiver first. Save with **green**.

**From a PC instead** (for working on Lynx itself): clone this repository, or download it with GitHub's **Code, Download ZIP**, and from its folder run `tools/deploy.sh <box address>`. That copies your copy of Lynx to the box and restarts the GUI.

## 3. Updating

**Everything:** Run the same two lines on the box again:
```
opkg update && opkg upgrade
wget -qO- https://raw.githubusercontent.com/G8YTZ/Lynx-Enigma2/main/tools/install.sh | sh
```
The first updates the box's own software (OpenATV, ServiceApp and the players); the second updates Lynx.

Your settings stay as they are: they live in the box's own settings file, not with Lynx. The repeater list comes with Lynx, so updating Lynx updates the list too. The BATC stream list updates itself every hour.

**From the remote instead:** **Menu, Setup, Software Management, Software update** does what the first line does. Lynx is not part of the feed, so a software update leaves it alone; if Lynx ever goes missing after one, run the second line again.

**Removing Lynx,** on the box:
```
rm -rf /usr/lib/enigma2/python/Plugins/Extensions/LynxRepeaters; /sbin/init 4; sleep 2; /sbin/init 3
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
- **The magic eye:** Its dark wedge narrows as the signal improves above what the received modulation and FEC need, and closes at about 10 dB in hand. Wide open means you are at the edge; dark means no lock. Beside the SNR the margin shows as a figure, such as +8.0, and the level shows in dBm on the line below (uncalibrated: good for comparing antenna positions).
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
- **Lynx's log:** On the box, `cat /tmp/lynx.log` (cleared at each restart). Include it when reporting a problem.

## Help and feedback

Report problems and ideas on the [GitHub issues page](https://github.com/G8YTZ/Lynx-Enigma2/issues), with your box, its OpenATV version (**Menu, Information, About**) and Lynx's log. Repeater details that are wrong are welcome too: the list is checked against the RSGB ETCC list and the BATC wiki, but symbol rates in particular change.

## For developers

Tests run on any PC: `python3 tests/test_plugin.py`. The code must run on Python 2.7 and 3, for older images. `CLAUDE.md` holds the working notes: how Enigma2 sees 23 cm, the box's quirks, and the decisions so far.

## Licence

GNU General Public License, version 2 or (at your option) any later version, like Enigma2 itself. See [LICENSE](LICENSE).

Justin Cockett, G8YTZ

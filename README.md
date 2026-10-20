# Lynx-Enigma2

Lynx for Enigma2 satellite receivers: watch UK amateur TV repeaters on a shop-bought box, with every repeater listed and ready to tune.

Part of the Lynx family, with the [Lynx DATV Receiver](https://github.com/G8YTZ/lynx-datv-receiver) and [Lynx-Tx](https://github.com/G8YTZ/Lynx-DATV-Tx).

**Status: Early development.** Proven so far on a Zgemma H11S running OpenATV: DVB-S2 on 23 cm straight into the box's satellite tuner, from 1000 kS/s up.

## The idea

A satellite receiver's tuner covers 950 to 2150 MHz, so 23 cm repeaters go straight in, and the box already decodes HEVC to HDMI. What it lacks is knowing where the repeaters are. Lynx-Enigma2 adds:

- **Every UK repeater, ready to tune:** Built from the RSGB ETCC list (frequencies, locations, status) and the BATC wiki (symbol rates), sorted by distance from you.
- **Pick and watch:** Choose a repeater and the box finds its programme by itself; no channel numbers to know.
- **Lynx on screen:** Callsign, signal quality and repeater details.
- **Other bands** (3.4 and 10 GHz) through a suitable LNB or converter, each with its own local oscillator.

LNB power stays on, to feed the small inline preamplifiers that run from it.

## Setting up a box

Tested on a Zgemma H11S. Other Enigma2 boxes with a DVB-S2 tuner should work the same way.

1. **Use a current image:** OpenATV 8 or later (7.x is end of life). Older images (Python 2, 2021 and before) run Lynx, but their stream players miss the picture on many BATC streams. On a multiboot box such as the H11S, put the new image in a spare slot, so the old one stays as it was: **Menu, Setup, Software Management, Flash online**, choose the newest OpenATV 8 build for your box, then a free slot.

   Flash online needs a USB stick or disc to download to ("could not find suitable media" without one). Without one, flash from a PC over SSH instead, here for the H11S (find your box's newest `_multi.zip` at `images.mynonpublic.com/openatv/8.0/<box>/`):
   ```
   ssh root@<box> 'mkdir -p /home/root/flash && cd /home/root/flash && wget -O image.zip <multi.zip address> && unzip -o image.zip'
   ssh root@<box> 'nohup /usr/bin/ofgwrite -r -k -m2 /home/root/flash/h11 > /home/root/flash/ofgwrite.log 2>&1 &'
   ```
   `-m2` writes slot 2 and leaves the others alone. When the screen says it flashed, use the **Multiboot Image Selector** to start slot 2, and work through the setup wizard (tuner A: universal LNB, Astra 19.2E; no channel scan needed).
2. **Tuner:** **Menu, Setup, Tuner Configuration, Tuner A**: configuration mode **Simple**, **Single**, satellite **Astra 1KR/1L/1M/1N (19.2E)**, then save. Check this even after the setup wizard: on OpenATV 8 the wizard can leave tuner A "not configured", and Lynx then cannot tune anything (it will tell you so). Lynx works out the frequencies; nothing else needs changing for 23 cm.
3. **Time:** **Menu, Setup, System, Time**, time synchronisation by NTP. Lynx also puts the clock right after a power cut, but the box should keep it too.
4. **Stream players:** Install ServiceApp with gstplayer and exteplayer3, from the box's own feed:
   ```
   opkg update
   opkg install enigma2-plugin-systemplugins-serviceapp gstplayer exteplayer3
   ```
5. **Lynx:** From a PC on the same network, `tools/deploy.sh <box address>`. Then open **Plugins, UK ATV Repeaters**, press blue for Settings, enter your locator, and switch on **Open Lynx at start-up** if the box is to be a repeater receiver first.

## Trying it

From a Mac or Linux PC on the same network as the box:

```
tools/deploy.sh 192.168.0.164
```

That copies the plugin to `/usr/lib/enigma2/python/Plugins/Extensions/LynxRepeaters/` and restarts the GUI. Then open **Plugins, UK ATV Repeaters**:

- **OK or green:** Watch the highlighted repeater. Lynx scans its one transponder and plays the programme it finds.
- **Yellow:** Watch the repeater's BATC stream instead of on air (repeaters marked LIVE).
- **MENU:** Every choice in one place, including watching on air while trying every symbol rate (for a listed rate that is wrong) and checking BATC now.
- **Blue:** Settings: your locator, LNB supply (13 or 18 V), the 9 cm and 3 cm LNB oscillators, whether to show repeaters listed as off air, whether Lynx opens by itself when the box starts, and the BATC live streams.
- **Stream only:** Repeaters on the BATC streamer but not on the UK list (foreign ones such as DB0OZ Bremen, say) are at the end of the list; OK or yellow watches them.
- **BATC Live:** Lynx checks the BATC streamer every hour and keeps a **BATC Live** channel list, so live streams can be watched from the box's ordinary channel list too.
- While watching, the Lynx bar shows callsign, town, distance and live SNR. **CH+ and CH-** (or up and down) go to the next or previous repeater in Lynx's list, **OK** hides the bar, **EXIT** goes back to the list.
- **Leaving Lynx:** Only through **MENU, Leave Lynx**, so a stray press never throws you out; what is playing carries on. On the list, EXIT or red (**Stop** or **Close menu**) stops a tune in progress, or takes you back to the picture; left alone for 10 seconds while something is playing, the list goes back to the picture by itself.

For the BATC streams, ServiceApp must be on the box (step 4 above): Lynx then plays streams through gstplayer; if a stream gives sound but no picture, **yellow** on the Lynx bar swaps to exteplayer3 (and back).

If something goes wrong, Lynx keeps its own log on the box: `ssh root@<box> cat /tmp/lynx.log`.

Tests (on any PC): `python3 tests/test_plugin.py`

## Licence

GNU General Public License, version 2 or (at your option) any later version, like Enigma2 itself. See [LICENSE](LICENSE).

Justin Cockett, G8YTZ

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
- While watching, the Lynx bar shows callsign, town, distance and live SNR. **CH+ and CH-** (or up and down) go to the next or previous repeater in Lynx's list, **OK** hides the bar, **EXIT** goes back to the list, **red** leaves Lynx with the repeater still on.

For the BATC streams, install ServiceApp on the box first (`opkg install enigma2-plugin-systemplugins-serviceapp gstplayer exteplayer3`): Lynx then plays streams through gstplayer, which is reliable and quick when hopping channels.

Tests (on any PC): `python3 tests/test_plugin.py`

## Licence

GNU General Public License, version 2 or (at your option) any later version, like Enigma2 itself. See [LICENSE](LICENSE).

Justin Cockett, G8YTZ

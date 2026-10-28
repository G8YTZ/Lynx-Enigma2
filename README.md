# Lynx-Enigma2

Lynx for Enigma2 satellite receivers: watch UK amateur TV repeaters on a shop-bought box, with every repeater listed and ready to tune, and their BATC streams too.

Part of the Lynx family, with the [Lynx DATV Receiver](https://github.com/G8YTZ/lynx-datv-receiver) and [Lynx-Tx](https://github.com/G8YTZ/Lynx-DATV-Tx).

**Status: Working, in testing.** Proven on a Zgemma H11S with OpenATV 8.0.1: 23 cm DVB-S2 straight into the box's satellite tuner from 1000 kS/s up, 4K HEVC on air, BATC streams, channel hopping between the two.

**Tested on:**
- **Zgemma H11S,** OpenATV 8.0.1: Everything, on air and streams (two boxes, October 2026).
- **Zgemma H9S SE:** Works just like the H11S (October 2026).
- **Octagon SF8008 4K Combo:** Works (October 2026).

Tried it on another box? Please say how it went on the issues page.

## The idea

A satellite receiver's tuner covers 950 to 2150 MHz, so 23 cm repeaters go straight in, and the box already decodes HEVC to HDMI. What it lacks is knowing where the repeaters are. Lynx adds:

- **Every UK repeater, ready to tune:** From the RSGB ETCC list (frequencies, locations, status) and the BATC wiki (symbol rates), sorted by distance from you.
- **Pick and watch:** Choose a repeater and the box finds its programme by itself; no channel numbers, and it still works if a repeater changes its service name or IDs.
- **BATC streams:** Repeaters streaming on the BATC streamer are marked LIVE and play over the internet, so you can see a repeater beyond radio range, or check it is on before pointing an antenna.
- **Lynx on screen:** The broadcast name, callsign, town, distance, frequency, symbol rate, picture size and LNB supply, with the real modulation and FEC, signal level, SNR and margin read from the demodulator, and a **magic eye** for pointing antennas.
- **Other bands** (3.4 and 10 GHz) through a suitable LNB, each with its own local oscillator.

LNB power is on by default, to feed the small inline preamplifiers that run from it, and can be switched off in Settings.

## 1. Setting up the box

Tested on the Zgemma H11S and H9S SE and the Octagon SF8008. Other Enigma2 boxes with a DVB-S2 tuner should work the same way. Lynx needs **OpenATV 8 or later** (7.x is end of life; the older images a box may come with miss the picture on many BATC streams). Already on OpenATV 8? Go straight to step 3.

### Step 1: First power-up (the image the box came with)

Plug in the network cable first. The box runs its own set-up wizard; you only need it to reach the network, as this image is about to be replaced:
- **Language:** English (GB).
- **Network:** Enabled **Yes**.
- **Everything else:** Accept what it offers, and skip the tuner set-up and the channel scan.

Then note the box's address: **Menu, Setup, System, Network** (such as 192.168.0.80). **Do not run a software update on this image**: on an old image it can fail part-way and leave the box worse off.

### Step 2: Put OpenATV 8 on it

On a multiboot box such as the H11S, OpenATV 8 goes in a spare slot, so the image the box came with stays as it was: your way back.

**With a USB stick in the box:** **Menu, Setup, Software Management, Flash online**, the newest OpenATV 8 build for your box, then a free slot. Without a stick or disc it says "could not find suitable media"; then use a computer, as follows. The commands are the same on a Mac and on Windows.

   **a. Open a command window.**
   - **Mac:** Open **Terminal** (Applications, Utilities).
   - **Windows 10 or 11:** Open **PowerShell** (type PowerShell in the Start menu).

   **b. Find two more things:**
   - **A free slot:** On the box, **Menu, Standby / Restart, Multiboot Image Selector** lists what is in each slot. Pick an empty one (2, 3 or 4). Never the slot with the image the box came with: that is your way back.
   - **The image's address:** In a browser, open [images.mynonpublic.com/openatv](https://images.mynonpublic.com/openatv/), choose your box (zgemmah11s for the H11S), then the newest **8.x** `_multi.zip`, and copy its link. On 26 October 2026 that was `https://images.mynonpublic.com/openatv/8.0/zgemmah11s/openatv-8.0.1-zgemmah11s-20261026_multi.zip`.

     Or, on a Mac, let Terminal find the newest one for you (for another box, put its name in place of zgemmah11s):
     ```
     curl -sL https://images.mynonpublic.com/openatv/json/zgemmah11s | tr ',' '\n' | grep -o 'https[^"]*openatv-8[^"]*_multi.zip' | sed 's#\\##g' | sort | tail -1
     ```

   **c. Let the box download the image.** Type this as one line, with your box's address and the image's address in place of the examples (the box fetches the image itself; nothing is saved on your computer):
   ```
   ssh root@192.168.0.80 "mkdir -p /home/root/flash && cd /home/root/flash && wget -O image.zip https://images.mynonpublic.com/openatv/8.0/zgemmah11s/openatv-8.0.1-zgemmah11s-20261026_multi.zip && unzip -o image.zip && ls h11"
   ```
   The first time, answer `yes` to trusting the box. After a minute or two it should end with `rootfs.tar.bz2` and `uImage`. If it doesn't, stop here and check the addresses.

   **d. Flash it,** with your box's address and the free slot after `-m` (here slot 2):
   ```
   ssh root@192.168.0.80 "nohup /usr/bin/ofgwrite -r -k -m2 /home/root/flash/h11 > /home/root/flash/ofgwrite.log 2>&1 &"
   ```
   The box's screen shows the progress. When it says it has flashed, choose that slot in the **Multiboot Image Selector** (Menu, Standby / Restart); the old image may list it oddly (such as "Type root to log in with supervisor privileges"), which is fine. The box restarts with the OpenATV 8 logo.

### Step 3: OpenATV 8's set-up wizard

- **Language:** English (GB).
- **Video:** Automatic mode selection **Yes**, then **2160p 50 Hz** on a 4K TV or monitor, or the best mode yours supports. Pick 50 Hz in Europe, not 30 or 60.
- **Network:** Enabled **Yes**; **Wake on LAN** is worth switching on too.
- **Time:** Synchronise the time using **NTP**.
- **Tuner:** Configuration mode **Simple**, **Single**, then the satellite: choose the **Astra Ku band option at 19.2°E** (its exact name varies between images, such as "Astra 1KR/1L/1M/1N (19.2E)").
- **Channel scan:** Skip it; Lynx does not need one.

### Step 4: Check the tuner

**Menu, Setup, Tuner Configuration, Tuner A** should show **Simple**, **Single** and the Astra 19.2°E option; set it and save if not. The wizard can leave tuner A "not configured", and Lynx cannot tune anything until it is set (it says so). Nothing else needs changing for 23 cm; Lynx works out the frequencies.

## 2. Installing Lynx

Lynx installs from the box itself, over the network. It goes into the image you are running: each slot is a separate system, so Lynx installed in the old image is not in OpenATV 8.

**Log in to the box:**
- **Mac or Linux:** Open Terminal and type `ssh root@<box address>`.
- **Windows 10 or 11:** Open PowerShell and type the same.

OpenATV's root login has no password; answer `yes` if asked whether to trust the box. You are on the box when the prompt changes to something like `root@zgemmah11s:~#`. After a reflash, SSH may refuse with a warning that the box's "host key has changed": clear the old key on your computer with `ssh-keygen -R <box address>` and log in again.

**Then type these on the box, one at a time,** waiting for the prompt to come back after each (pasted together with the login line, they are lost while it connects):
```
opkg update && opkg upgrade
```
```
wget -qO- https://raw.githubusercontent.com/G8YTZ/Lynx-Enigma2/main/tools/install.sh | sh
```
The first brings OpenATV 8 up to date ("No packages installed or removed" means it already was). The second installs the stream players (nothing for you to set up), downloads the latest Lynx, installs it and restarts the box's GUI. It ends with "Lynx: installed; restarting the GUI".

**Open Lynx:** On the remote, **Menu**, then the plugin browser (**Plugins**), then **Lynx: UK ATV Repeaters** (it may be further down the list; scroll to find it). It is also under the blue button's **Extensions** list. Once **Open Lynx at start-up** is on and saved (below), you won't need to find it again.

### Lynx's settings

The first time, Lynx opens its settings by itself; after that they are on **blue** in the Lynx list. **Up and down** pick a line, **left and right** change it, **green** saves, **red** goes back without saving.

| Setting | What it does | Choose |
|---|---|---|
| **Your locator** | Sorts the list by distance from you. Type it with the number keys, or press **TEXT** for an on-screen keyboard; upper or lower case both work. | Yours, such as JO01 or JO01AJ. |
| **LNB supply on the cable** | The DC the box puts up the coax: 13 V, 18 V or off. | **13 V** to power an inline preamp (the cooler choice); **off** for a feed with no preamp, or an antenna that is a DC short. Off also cuts power to a 19.2°E dish on the same tuner. |
| **9 cm LNB oscillator** | For 9 cm repeaters through a C-band LNB. | 5150 unless your LNB says otherwise. |
| **3 cm LNB oscillator** | For 10 GHz repeaters. A standard 9750 MHz LNB puts them below the tuner, so they need a 9 GHz one. | 9000 with a 9 GHz LNB. |
| **Show repeaters listed as off air** | Includes repeaters the RSGB list marks as off air. | **No**, unless you are checking one. |
| **Open Lynx at start-up** | The box goes straight to Lynx whenever it starts, instead of the TV screen. | **Yes** on a box kept for ATV. |
| **BATC live streams** | Checks the BATC streamer every hour: LIVE markers, stream-only repeaters, and the BATC Live channel list. | **Yes**. |
| **Every BATC stream in the list** | Adds every stream on the BATC streamer at the end of the list, members' and event streams too, offline ones greyed. | Your choice; **No** keeps the list to repeaters. |
| **Player for streams** | Which player plays BATC streams. | **Automatic** (gstplayer, then exteplayer3 on yellow). |
| **Lynx updates at start-up** | At each start, looks for a newer Lynx. | **Ask before installing**, or **Install by itself** on a box nobody watches. |

**Entering your locator:**
1. With **Your locator** highlighted, press **TEXT** for the on-screen keyboard (easiest), or type straight in with the number keys as on an old phone: press a key repeatedly to step through its letters (**5** for J, **6** three times for O).
2. Type four or six characters, such as **JO01** or **JO01AJ**. Six gives a more exact distance. Upper or lower case both work, and Lynx ignores any stray spaces or symbols the number keys slip in.
3. On the keyboard, finish with its **OK** or **green** to put the text in.
4. Don't know yours? Look up your address on a locator map such as [QRZ's grid mapper](https://www.qrz.com/gridmapper), or ask a local amateur.

Then press **green** to save. The list is sorted from your locator, and Lynx is ready to watch.

**Before you watch on air, check the tuner once more.** Lynx's settings do not include it: it is the box's own setting. **Menu, Setup, Tuner Configuration, Tuner A**: **Simple**, **Single**, and the **Astra Ku band option at 19.2°E**, then save (see [step 4](#step-4-check-the-tuner)). If it is not set, Lynx says "No tuner set up" instead of tuning.

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

**By itself:** Each time the box starts, Lynx checks GitHub for a newer version and asks whether to install it (Settings, **Lynx updates at start-up**: ask, install by itself, or do not check). **MENU, Check for a newer Lynx now** does the same at any time. This works on installs made with the line above; a copy put on from a PC with `deploy.sh` is left alone.

**Removing Lynx,** on the box:
```
rm -rf /usr/lib/enigma2/python/Plugins/Extensions/LynxRepeaters; /sbin/init 4; sleep 2; /sbin/init 3
```

## 4. Using Lynx

**The list:**
- **OK or green:** Watch the highlighted repeater on air. Lynx scans its one transponder and plays the programme it finds.
- **Yellow:** Watch its BATC stream instead (repeaters marked LIVE).
- **Blue:** Settings (see [Lynx's settings](#lynxs-settings)).
- **0:** Update the LIVE markers now: asks BATC which streams are live, instead of waiting for the hourly check.
- **MENU:** Every choice in one place, including watching on air while trying every symbol rate (for a listed rate that is wrong), updating the stream status, and **Leave Lynx**.
- **Tuning by hand:** **MENU, Tune by hand**: type the frequency in MHz (1249, say) with the number keys and choose the symbol rate (1, 1.5, 2, 3 or 4 MS/s, or **Not sure: try them all**). **OK** or **green** watches it. To keep it, give it a name and press **yellow**: it goes at the top of the list as a preset, and **MENU** on a preset changes or deletes it. Presets are kept on the box and survive Lynx updates.
- **EXIT or red** (**Stop** or **Close menu**): Stops a tune in progress, or takes you back to the picture. Left alone for 10 seconds while something is playing, the list goes back to the picture by itself.
- **Stream only:** Repeaters on the BATC streamer but not on the UK list (DB0OZ Bremen, say) are at the end; OK or yellow watches them.
- **A member's stream:** **MENU, Add a BATC stream by its name**: type the end of its address on the BATC streamer (for batc.org.uk/live/g4fre, that is g4fre). It goes at the top of the list as a preset, marked LIVE while it is streaming; OK watches it.

**The Lynx bar,** while watching:
- **The magic eye:** Its dark wedge narrows as the signal gets stronger and the margin grows, and closes on a strong, clean signal. Wide open means you are near the edge; dark means no lock.
- **Margin:** Beside the SNR, how many dB the signal is above what its modulation and FEC need to decode. Around +3 is a working signal, +10 or more plenty in hand, below +1 at the edge of breaking up.
- **Level:** In dBm on the line below. Uncalibrated, so good for comparing antenna positions; below about -77 dBm the tuner cannot tell any lower, and the margin is the better guide.
- **CH+ and CH-** (or up and down): The next or previous repeater in the list, by the same route (on air or stream). Keep pressing to scroll; each press moves straight on.
- **OK:** Hides or shows the bar.
- **Yellow,** on a stream: Swaps between gstplayer and exteplayer3, for a stream that gives sound but no picture.
- **EXIT:** Back to the list.

**Leaving Lynx:** Only through **MENU, Leave Lynx**, so a stray press never throws you out. What is playing carries on.

**Using your TV's or amplifier's remote:** If the box is connected over HDMI to a TV or AV amplifier that supports HDMI-CEC, you can use that remote instead of the box's (tried with a Sony TV's remote, October 2026: everything worked, with **Return** for **EXIT**). Switch CEC on at both ends: on the box, **Menu, Setup, System, HDMI-CEC**; on the TV it often has a brand name (Anynet+ on Samsung, Bravia Sync on Sony, SimpLink on LG, VIERA Link on Panasonic). The arrows, **OK** and the colour buttons usually work the same. Some buttons are in different places or have other names: **EXIT** is often **Back** or **Return**, and **MENU** may be under **Tools**, **Options** or a long press. A few, such as **0** or **TEXT**, may not pass through at all: a Yamaha AV amplifier's remote (October 2026) works everything else but has no 0, its number keys being input selectors. Without **0**, update the stream status with **MENU, Update the BATC stream status now**; for typing the locator or a stream name, use the box's own remote.

**BATC Live:** Lynx also keeps a **BATC Live** channel list, refreshed every hour, so live streams can be watched from the box's ordinary channel list.

## 5. Troubleshooting

- **Lynx does not open when the box starts:** Switch on **Open Lynx at start-up** in Lynx's settings (**blue**).
- **The locator will not go in:** Some boxes put a space or a symbol before the 0 on the number keys. Lynx ignores those now; or press **TEXT** for the on-screen keyboard.
- **LNB supply off:** It applies from the next tune. It also cuts power to a 19.2E satellite dish on the same tuner, so leave it on if the box watches satellite TV too.
- **"No tuner set up":** Tuner A is not configured; see step 4 of setting up.
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

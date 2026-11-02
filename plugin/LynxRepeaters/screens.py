# Lynx-Enigma2: the UK ATV Repeaters screens.
#
# Copyright (C) 2026 Justin Cockett, G8YTZ
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version. See LICENSE.
"""Three screens:

  RepeaterList   every repeater the box can show, nearest first, after your
                 own presets; OK watches
  ManualTune     a frequency and symbol rate typed in, watched or kept as a
                 preset
  LynxBar        a strip along the bottom while watching: callsign, town,
                 distance, frequency, symbol rate and live MER
  LynxSettings   locator, LNB supply voltage, per-band LNB oscillators
"""
from __future__ import absolute_import, division, print_function

from .log import log

import re
import sys
import time

from enigma import ePoint, eServiceReference, eSize, getDesktop

from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.Label import Label
from Components.Sources.List import List
from Components.Sources.StaticText import StaticText
from Components.config import (ConfigInteger, ConfigSelection, ConfigSubsection, ConfigText,
                               ConfigYesNo, config, configfile, getConfigListEntry)
from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen

from . import repeaters, streams, sync
from .eye import FRAMES as EYE_FRAMES, closure as eye_closure, frame as eye_frame, margin_db
from .tuning import level, signal
from .tuning import RepeaterTuner, _timer, live, match_playing, same_service, signal_text, tech_text, title_text

try:
    _
except NameError:
    def _(s):
        return s

VERSION = "0.2"

# Settings

config.plugins.lynxrepeaters = ConfigSubsection()
cfg = config.plugins.lynxrepeaters
cfg.locator = ConfigText(default="", fixed_size=False)
cfg.supply = ConfigSelection(default="13", choices=[
    ("13", _("13 V (vertical)")), ("18", _("18 V (horizontal)")),
    ("off", _("Off: no power up the cable"))])
# At each start: look for a newer Lynx on GitHub (Justin, 23 Oct 2026).
cfg.update_check = ConfigSelection(default="ask", choices=[
    ("ask", _("Ask before installing")), ("auto", _("Install by itself")), ("off", _("Do not check"))])
cfg.osc_9cm = ConfigInteger(default=repeaters.BANDS["9cm"][2], limits=(1, 20000))
cfg.osc_3cm = ConfigInteger(default=repeaters.BANDS["3cm"][2], limits=(1, 20000))
cfg.show_off = ConfigYesNo(default=False)
cfg.autostart = ConfigYesNo(default=False)
cfg.streams = ConfigYesNo(default=True)
# Every BATC stream at the end of the list, members' and offline ones too
# (Justin, 23 Oct 2026), not only repeaters that stream.
cfg.all_streams = ConfigYesNo(default=False)
cfg.player = ConfigSelection(default="auto", choices=[
    ("auto", _("Automatic (gstplayer, then exteplayer3)")),
    ("exteplayer3", _("exteplayer3 (ServiceApp)")),
    ("gstplayer", _("gstplayer (ServiceApp)")),
    ("builtin", _("The box's own player"))])

# Tuning by hand: the last frequency and symbol rate typed in.
SR_CHOICES = [(str(r), "%g MS/s" % (r / 1000.0)) for r in repeaters.MANUAL_SR_KS] + [
    ("any", _("Not sure: try them all"))]
cfg.manual_freq = ConfigInteger(default=1249, limits=(950, 10500))
cfg.manual_sr = ConfigSelection(default="1500", choices=SR_CHOICES)
# Settings open by themselves the first time Lynx opens (G4FRE and others
# had not found them, 23 Oct 2026).
cfg.welcomed = ConfigYesNo(default=False)
# The PPM audio meter at the left of the Lynx bar, as Lynx Rx and Apple TV.
cfg.ppm = ConfigYesNo(default=True)
# BATC's chat for what is playing, as bubbles on the picture (Justin, 2 Nov 2026).
cfg.chat = ConfigYesNo(default=True)


def video_signs(session):
    """Everything the box offers that might show video is running, for the
    log: the service's own info and the decoder's /proc entries."""
    out = {}
    try:
        from enigma import iServiceInformation as I
        info = session.nav.getCurrentService().info()
        for name in ("sVideoWidth", "sVideoHeight", "sVideoType", "sVideoPID", "sAspect", "sFrameRate", "sProgressive"):
            if hasattr(I, name):
                out[name] = info.getInfo(getattr(I, name))
    except Exception as e:
        out["info"] = str(e)
    for f in ("xres", "yres", "framerate", "aspect"):
        try:
            with open("/proc/stb/vmpeg/0/" + f) as fh:
                out["vmpeg." + f] = fh.read().strip()
        except (IOError, OSError):
            pass
    return out


def decoder_has_picture(signs):
    """From video_signs(): whether the box's video decoder has a picture.
    The player's own size is not enough: on a start with sound but no
    picture (2 Nov 2026) gstplayer said 1920x1080 while the decoder still
    said ffffffff; on every good start the decoder had a real size within
    about 6 s."""
    try:
        x = int(str(signs.get("vmpeg.xres", "")), 16)
    except ValueError:
        return False
    return 0 < x < 0xffffffff


def lnb_osc():
    return {"23cm": 0, "9cm": cfg.osc_9cm.value, "3cm": cfg.osc_3cm.value}


def home():
    loc = repeaters.clean_locator(cfg.locator.value)
    return repeaters.locator_to_latlon(loc) if repeaters.valid_locator(loc) else None


# Skins are drawn for 1920 x 1080 and scaled to the box's output.

def _factor():
    return getDesktop(0).size().width() / 1920.0


import os

try:
    from Components.Pixmap import MultiPixmap
except ImportError:
    MultiPixmap = None

EYE = 110                              # the eye's size at 1920 x 1080
_EYE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eye")


def _eye_pixmaps():
    """The eye's pictures for this output (HD set below Full HD), in the
    order eye_frame() numbers them: open .. closed, then off. None if they
    are missing or the image has no MultiPixmap."""
    if not MultiPixmap:
        return None
    folder = _EYE_DIR if _factor() > 0.8 else os.path.join(_EYE_DIR, "hd")
    names = ["eye_%02d.png" % n for n in range(EYE_FRAMES)] + ["eye_off.png"]
    paths = [os.path.join(folder, n) for n in names]
    return paths if all(os.path.exists(p) for p in paths) else None


EYE_PIXMAPS = _eye_pixmaps()

_PPM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ppm")


def _ppm_pixmaps():
    """The PPM's pictures for this output: housing, green needles, red
    needles, screw. None if any are missing."""
    if not MultiPixmap:
        return None
    from .ppm import FRAMES as PPM_FRAMES
    folder = _PPM_DIR if _factor() > 0.8 else os.path.join(_PPM_DIR, "hd")
    pics = {"housing": os.path.join(folder, "housing.png"), "screw": os.path.join(folder, "screw.png"),
            "green": [os.path.join(folder, "green_%02d.png" % n) for n in range(PPM_FRAMES)],
            "red": [os.path.join(folder, "red_%02d.png" % n) for n in range(PPM_FRAMES)]}
    files = [pics["housing"], pics["screw"]] + pics["green"] + pics["red"]
    return pics if all(os.path.exists(f) for f in files) else None


PPM_PIXMAPS = _ppm_pixmaps()
PPM_MS = 50                            # the needles move 20 times a second


class DemuxTap(object):
    """The playing programme's PAT, PMT and sound, read straight from its
    demux (as Enigma2's own recorder does) and fed to ffmpeg's standard
    input as they arrive: no 2.5 s lumps from the port 8001 server."""

    def __init__(self, plan):
        self.adapter, self.demux, self.pids = plan
        self.fd, self.running = None, False

    def open(self):
        import fcntl
        from .ppm import DMX_ADD_PID, DMX_SET_BUFFER_SIZE, DMX_SET_PES_FILTER, DMX_START, TAP_BUFFER, pes_filter
        import struct
        path = "/dev/dvb/adapter%d/demux%d" % (self.adapter, self.demux)
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        try:
            try:
                fcntl.ioctl(fd, DMX_SET_BUFFER_SIZE, TAP_BUFFER)
            except (IOError, OSError):
                pass
            fcntl.ioctl(fd, DMX_SET_PES_FILTER, pes_filter(self.pids[0]))
            fcntl.ioctl(fd, DMX_START)
            for pid in self.pids[1:]:
                fcntl.ioctl(fd, DMX_ADD_PID, struct.pack("=H", pid))
        except (IOError, OSError):
            os.close(fd)
            raise
        self.fd, self.running = fd, True

    def pump(self, out):
        """Copies the demux to out (ffmpeg's stdin) until stopped or ffmpeg ends."""
        import select
        from .ppm import TAP_READ
        fd = self.fd
        try:
            while self.running:
                ready = select.select([fd], [], [], 0.5)[0]
                if not ready:
                    continue
                try:
                    data = os.read(fd, TAP_READ)
                except (IOError, OSError) as e:
                    if e.errno in (11, 75):          # EAGAIN, EOVERFLOW (demux buffer overran: carry on)
                        continue
                    raise
                if data:
                    out.write(data)
                    out.flush()
        except (IOError, OSError, ValueError):
            pass                                     # ffmpeg gone, or the demux closed under us
        finally:
            try:
                out.close()
            except (IOError, OSError, ValueError):
                pass

    def close(self):
        self.running = False
        fd, self.fd = self.fd, None
        if fd is not None:
            import fcntl
            from .ppm import DMX_STOP
            try:
                fcntl.ioctl(fd, DMX_STOP)
            except (IOError, OSError):
                pass
            try:
                os.close(fd)
            except OSError:
                pass


class PPMMeter(object):
    """ffmpeg decoding the sound only of what is playing, read from its
    demux (DemuxTap), or the box's own stream on port 8001 if the demux
    will not open; a thread turns its peaks into needle positions. One at
    a time; stopped with its whole process group."""

    def __init__(self):
        from .ppm import Reader
        self.reader = Reader()
        self.proc, self.url, self.thread, self.failed_at, self.tries = None, None, None, None, 0
        self.tap, self.tap_failed = None, False
        import threading
        self.lock = threading.Lock()

    RETRY_S = 30                         # after ffmpeg gives up (no sound track, say)
    MAX_TRIES = 2                        # then leave that programme alone: each start can
                                         # upset the sound for a moment (1 Nov 2026)
    ERRORS = "/tmp/lynx-ppm.log"

    def start(self, source):
        """source: ("tap", (adapter, demux, pids), fallback url) or ("url", url)."""
        url = source
        if url == self.url and self.proc and self.proc.poll() is None:
            return
        if url == self.url and self.proc and self.proc.poll() is not None:
            # It ended by itself: say why once, then wait before trying again.
            if self.tries >= self.MAX_TRIES:
                if self.failed_at:
                    log("PPM: ffmpeg stopped (%s); not trying again on this programme" % self._last_error())
                    self.failed_at = None
                    with self.lock:
                        self.reader.rest()
                return
            if not self.failed_at:
                self.failed_at = time.time()
                log("PPM: ffmpeg stopped (%s); trying again in %d s" % (self._last_error(), self.RETRY_S))
                with self.lock:
                    self.reader.rest()
            if time.time() - self.failed_at < self.RETRY_S:
                return
        tries = self.tries + 1 if url == self.url else 1
        self.stop()
        self.failed_at, self.tries = None, tries
        import subprocess
        from .ppm import command
        tap = None
        if source[0] == "tap" and not self.tap_failed:
            tap = DemuxTap(source[1])
            try:
                tap.open()
            except (IOError, OSError) as e:
                # Not on this box: say so once and use the stream server from now on.
                log("PPM: demux %d would not open for the sound (%s); using port 8001" % (source[1][1], e))
                self.tap_failed, tap = True, None
        where = "pipe:0" if tap else (source[2] if source[0] == "tap" else source[1])
        try:
            with open(self.ERRORS, "w") as errors:
                self.proc = subprocess.Popen(command(where, _discard_format()), stdout=subprocess.PIPE, stderr=errors,
                                             stdin=subprocess.PIPE if tap else None, preexec_fn=os.setsid)
        except (OSError, ValueError) as e:
            log("PPM: could not start ffmpeg: %s" % e)
            self.proc = None
            if tap:
                tap.close()
            return
        self.url = url
        import threading
        if tap:
            self.tap = tap
            feeder = threading.Thread(target=tap.pump, args=(self.proc.stdin,))
            feeder.daemon = True
            feeder.start()
            log("PPM: metering demux %d, PIDs %s" % (source[1][1], ", ".join("0x%x" % p for p in source[1][2])))
        else:
            log("PPM: metering %s" % where)
        self.thread = threading.Thread(target=self._read, args=(self.proc,))
        self.thread.daemon = True
        self.thread.start()

    def _read(self, proc):
        told = time.time()
        for raw in iter(proc.stdout.readline, b""):
            if proc is not self.proc:
                break
            with self.lock:
                self.reader.line(raw.decode("latin-1"))
            if time.time() - told > 10:
                told = time.time()
                log("PPM: %.1f s behind the sound's own clock" % self.reader.lag)

    def _last_error(self):
        try:
            with open(self.ERRORS) as f:
                lines = [l.strip() for l in f if l.strip()]
            return lines[-1][:160] if lines else "no message"
        except (IOError, OSError):
            return "no message"

    def stop(self):
        proc, self.proc, self.url, self.failed_at = self.proc, None, None, None
        tap, self.tap = self.tap, None
        if tap:
            tap.close()                  # the demux filter goes before any tune
        if proc and proc.poll() is None:
            import signal as sig
            try:
                os.killpg(proc.pid, sig.SIGTERM)
            except OSError:
                pass
            try:
                proc.wait()
            except OSError:
                pass
        with self.lock:
            self.reader.rest()

    def positions(self):
        with self.lock:
            return self.reader.positions()


_DISCARD = []


def _discard_format():
    """The output format the PPM's ffmpeg throws its sound away in: asked
    of the box's ffmpeg once, as builds differ."""
    if not _DISCARD:
        from .ppm import discard, encoders, muxers
        import subprocess

        def ask(what):
            try:
                return subprocess.Popen(["ffmpeg", "-hide_banner", what], stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT).communicate()[0].decode("latin-1")
            except (OSError, ValueError):
                return ""
        _DISCARD.append(discard(muxers(ask("-muxers")), encoders(ask("-encoders"))))
        log("PPM: ffmpeg discards the sound as %s (%s)" % _DISCARD[0])
    return _DISCARD[0]


def stop_stray_meters():
    """An earlier Lynx's PPM ffmpeg, left behind by a GUI crash."""
    from .ppm import MARKER
    os.system("pkill -f 'comment=%s' >/dev/null 2>&1" % MARKER)
LEVEL_FLOOR_DBM = -77                  # where the H11S's level reading stops falling
EYE_MS = 250                           # four looks a second: quick enough to point with
EYE_EASE = 0.35                        # how far it moves towards a new reading each look


def _scale(skin):
    f = _factor()
    if abs(f - 1) < 0.01:
        return skin
    n = lambda m: str(int(round(int(m.group(0)) * f)))
    num = lambda s: re.sub(r"\d+", n, s)
    skin = re.sub(r'(position|size)="[\d,]+"', lambda m: num(m.group(0)), skin)
    skin = re.sub(r'font="Regular;\d+"', lambda m: num(m.group(0)), skin)
    skin = re.sub(r'(pos|size)=\(\d+,\s*\d+\)', lambda m: num(m.group(0)), skin)
    skin = re.sub(r'gFont\("Regular",\s*\d+\)', lambda m: num(m.group(0)), skin)
    return re.sub(r'"itemHeight":\s*\d+', lambda m: num(m.group(0)), skin)


# EXIT closes a menu on the key press; the key's release then reaches the
# list underneath as its own EXIT and closed Lynx. Ignore EXIT this soon after
# a menu, settings or the Lynx bar closes.
CHILD_CLOSED_GRACE_S = 0.6

# With something playing, the list gets out of the way after this long
# untouched, back to the picture and the Lynx bar (Justin's idea).
LIST_IDLE_MS = 10000

# Seconds of video diagnostics logged at the start of each stream.
STREAM_DIAG_S = 12
STREAM_PICTURE_FROM_S = 3              # earlier readings may be the last programme's
STREAM_PICTURE_BY_S = 12               # good starts had a picture by about 6 s

RED = "#00d0021b"
PANEL = "#00141414"
GREY = 0x808080
WHITE = 0xffffff

# Every named widget has zPosition 1. Enigma2 creates a skin's plain
# eLabels and ePixmaps after all its named widgets, so at the same height a
# background box covers the text on it: the list's right-hand panel was
# empty and its title bars' text hidden (Justin, 2 Nov 2026; the same cause
# as the PPM needles, 1 Nov).
BUTTONS = """
  <eLabel position="40,{y}" size="8,44" backgroundColor="#00d0021b"/>
  <widget zPosition="1" source="key_red" render="Label" position="56,{y}" size="300,44" font="Regular;30" valign="center" transparent="1"/>
  <eLabel position="400,{y}" size="8,44" backgroundColor="#0000a03c"/>
  <widget zPosition="1" source="key_green" render="Label" position="416,{y}" size="300,44" font="Regular;30" valign="center" transparent="1"/>
  <eLabel position="760,{y}" size="8,44" backgroundColor="#00e6b800"/>
  <widget zPosition="1" source="key_yellow" render="Label" position="776,{y}" size="400,44" font="Regular;30" valign="center" transparent="1"/>
  <eLabel position="1220,{y}" size="8,44" backgroundColor="#000060d0"/>
  <widget zPosition="1" source="key_blue" render="Label" position="1236,{y}" size="200,44" font="Regular;30" valign="center" transparent="1"/>
  <eLabel text="0  Update streams    MENU  More" position="1400,{y}" size="330,44" font="Regular;26" halign="right" valign="center" foregroundColor="#00c0c0c0" transparent="1"/>
"""


class RepeaterList(Screen):
    skin = _scale("""
<screen name="LynxRepeaterList" position="center,center" size="1760,940" title="UK ATV Repeaters" backgroundColor="#00141414" flags="wfNoBorder">
  <eLabel position="0,0" size="1760,90" backgroundColor="#00d0021b"/>
  <eLabel text="LYNX" position="40,0" size="200,90" font="Regular;54" valign="center" foregroundColor="#00ffffff" backgroundColor="#00d0021b"/>
  <eLabel text="UK ATV Repeaters" position="240,0" size="700,90" font="Regular;40" valign="center" foregroundColor="#00ffffff" backgroundColor="#00d0021b"/>
  <widget zPosition="1" name="where" position="940,0" size="790,90" font="Regular;30" halign="right" valign="center" foregroundColor="#00ffffff" backgroundColor="#00d0021b"/>
  <widget zPosition="1" source="list" render="Listbox" position="30,110" size="1080,690" scrollbarMode="showOnDemand" backgroundColor="#00141414" backgroundColorSelected="#00d0021b" transparent="0">
    <convert type="TemplatedMultiContent">
      {"template": [
        MultiContentEntryText(pos=(12,0), size=(160,46), font=0, flags=RT_HALIGN_LEFT|RT_VALIGN_CENTER, text=1, color=0xFF000006, color_sel=0xFFFFFF),
        MultiContentEntryText(pos=(180,0), size=(320,46), font=0, flags=RT_HALIGN_LEFT|RT_VALIGN_CENTER, text=2, color=0xFF000006, color_sel=0xFFFFFF),
        MultiContentEntryText(pos=(490,0), size=(120,46), font=0, flags=RT_HALIGN_RIGHT|RT_VALIGN_CENTER, text=3, color=0xFF000006, color_sel=0xFFFFFF),
        MultiContentEntryText(pos=(615,0), size=(170,46), font=0, flags=RT_HALIGN_RIGHT|RT_VALIGN_CENTER, text=4, color=0xFF000006, color_sel=0xFFFFFF),
        MultiContentEntryText(pos=(790,0), size=(150,46), font=0, flags=RT_HALIGN_RIGHT|RT_VALIGN_CENTER, text=5, color=0xFF000006, color_sel=0xFFFFFF),
        MultiContentEntryText(pos=(950,0), size=(80,46), font=1, flags=RT_HALIGN_LEFT|RT_VALIGN_CENTER, text=7, color=0xFFD200, color_sel=0xFFFFFF)],
       "fonts": [gFont("Regular", 30), gFont("Regular", 24)],
       "itemHeight": 46}
    </convert>
  </widget>
  <eLabel position="1130,110" size="600,690" backgroundColor="#00222222"/>
  <widget zPosition="1" name="call" position="1160,125" size="560,70" font="Regular;54" foregroundColor="#00ffffff" backgroundColor="#00222222"/>
  <widget zPosition="1" name="live" position="1160,200" size="550,44" font="Regular;30" valign="center" foregroundColor="#00ffd200" backgroundColor="#00222222"/>
  <widget zPosition="1" name="details" position="1160,250" size="550,535" font="Regular;28" foregroundColor="#00e0e0e0" backgroundColor="#00222222"/>
  <widget zPosition="1" name="status" position="30,815" size="1700,50" font="Regular;30" valign="center" foregroundColor="#00ffd200" backgroundColor="#00141414"/>
""" + BUTTONS.format(y=880) + """
</screen>""")

    def __init__(self, session):
        Screen.__init__(self, session)
        self.setTitle(_("UK ATV Repeaters"))
        self.old_service = self._playing()
        self.watching = None              # the entry now on screen, if any
        self.tuner = RepeaterTuner(session, self._progress, self._tuned)
        self.stream_timer, self._st = _timer(lambda: None)   # no longer started; kept for the checks
        self.diag_timer, self._dt = _timer(self._diag)
        self.onClose.append(self.diag_timer.stop)
        self.bar = None                   # the Lynx bar while it is open
        self.chat = ChatOverlay(session)  # BATC chat bubbles for what is playing
        self.onClose.append(self.chat.close)
        self.onShown.append(lambda: self.chat.dialog.pause(True))
        self.onHide.append(lambda: self.chat.dialog.pause(False))
        self.idle_timer, self._it = _timer(self._idle)
        self.hidden = False
        # While the list is hidden over a channel Lynx does not know, any of
        # these keys brings it back (they reach this map before the list).
        unhide = dict((k, self._unhide) for k in (
            "ok", "cancel", "red", "green", "yellow", "blue", "menu", "up", "down", "left", "right"))
        self["unhide"] = ActionMap(["OkCancelActions", "ColorActions", "MenuActions", "DirectionActions"], unhide, -5)
        self["unhide"].setEnabled(False)
        self.onClose.append(self.idle_timer.stop)
        self.onClose.append(self.stream_timer.stop)
        self["list"] = List([])
        self["where"] = Label()
        self["call"] = Label()
        self["details"] = Label()
        self["status"] = Label()
        self["key_red"] = StaticText("")          # see _red()
        self["key_green"] = StaticText(_("Watch"))
        self["key_yellow"] = StaticText("")
        self["live"] = Label()
        self["key_blue"] = StaticText(_("Settings"))
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "MenuActions"], {
            "ok": self.watch,
            "green": self.watch,
            "yellow": self.watch_stream,
            "cancel": self.back,
            "red": self.back,
            "blue": self.settings,
            "menu": self.menu,
        }, -1)
        self["numbers"] = ActionMap(["NumberActions"], {"0": self.update_streams}, -1)
        self["list"].onSelectionChanged.append(self._selected)
        self["list"].onSelectionChanged.append(self._touched)
        self.data = repeaters.load()
        self.presets = repeaters.load_presets()
        self.sync = sync.get()
        self.checking = False             # an update asked for with 0 or MENU
        self.sync.listeners.append(self._streams_updated)
        self.onClose.append(lambda: self.sync.listeners.remove(self._streams_updated))
        self.onLayoutFinish.append(self.refresh)
        self.onLayoutFinish.append(self._adopt_playing)
        self.welcome_timer, self._wlt = _timer(self._welcome_now)
        self.onClose.append(self.welcome_timer.stop)
        self.onShown.append(self._welcome)
        if cfg.streams.value and self.sync.stale():
            self.sync.refresh()

    def _playing(self):
        nav = self.session.nav
        get = getattr(nav, "getCurrentlyPlayingServiceOrGroup", None) or nav.getCurrentlyPlayingServiceReference
        return get()

    # The list

    def refresh(self):
        here = home()
        self.entries = repeaters.rows(self.data, here, lnb_osc(), cfg.show_off.value)
        rows = []
        # Your own presets first: they are what you put there to find.
        for p in self.presets:
            if p.get("stream"):
                s = streams.member_stream(self.sync.streams, p["stream"], p["name"])
                e = {"call": p["name"], "town": _("BATC stream"), "stream": s, "stream_only": True,
                     "preset": True, "km": None, "approx": False, "status": "on"}
                rows.append((e, _("Preset"), e["call"], "", _("BATC stream"), "", WHITE,
                             _("LIVE") if s.get("live") else ""))
                continue
            e = repeaters.manual_entry(p["freq_mhz"], p["sr_ks"], p["name"], lnb_osc())
            if not e:
                continue                  # an LNB setting has put it out of reach
            e["stream"] = self._stream_for(e)
            sr = "%d kS/s" % p["sr_ks"] if p["sr_ks"] else _("any")
            rows.append((e, _("Preset"), e["call"], "", "%g MHz" % p["freq_mhz"], sr, WHITE,
                         _("LIVE") if e["stream"] else ""))
        for e in self.entries:
            o = e["output"]
            km = "" if e["km"] is None else ("%s%d km" % ("~" if e["approx"] else "", round(e["km"])))
            sr = "%d kS/s" % o["sr_ks"] if o.get("sr_ks") else "? kS/s"
            colour = GREY if e["status"] != "on" else WHITE
            e["stream"] = self._stream_for(e)
            rows.append((e, e["call"], e["town"], km, "%g MHz" % o["freq_mhz"], sr, colour,
                         _("LIVE") if e["stream"] else ""))
        # Repeaters seen only on the BATC streamer, at the end of the list.
        if cfg.streams.value:
            shown = [e["call"] for e in self.entries] + [p["stream"] for p in self.presets if p.get("stream")]
            for x in streams.stream_only(self.sync.streams, shown, cfg.all_streams.value):
                e = dict(x, stream_only=True, km=None, approx=False, status="on")
                live = streams.is_live(x["stream"])
                rows.append((e, e["call"], e["town"], "", _("Stream only"), "", WHITE if live else GREY,
                             _("LIVE") if live else ""))
        self["list"].setList(rows)
        loc = repeaters.clean_locator(cfg.locator.value)
        self["where"].setText(_("From %s") % loc if here else _("Set your locator in Settings (blue)"))
        self._selected()

    def update_streams(self):
        """0, or MENU: ask BATC now which streams are live, rather than wait
        for the hourly check (Justin, 23 Oct 2026)."""
        if not cfg.streams.value:
            self["status"].setText(_("BATC streams are switched off in Settings (blue)"))
            return
        self.checking = True
        self["status"].setText(_("Asking BATC which streams are live..."))
        self.sync.refresh()

    def _streams_updated(self):
        self.refresh()
        if not self.checking:
            return
        self.checking = False
        if self.sync.last_error:
            self["status"].setText(_("Could not reach BATC: %s") % self.sync.last_error)
        else:
            self["status"].setText(_("BATC checked at %s: %d streams live") % (
                time.strftime("%H:%M"), len(streams.live_only(self.sync.streams))))

    def _stream_for(self, e):
        return streams.for_call(self.sync.streams, e["call"]) if cfg.streams.value else None

    def _current(self):
        cur = self["list"].getCurrent()
        return cur[0] if cur else None

    def _selected(self):
        e = self._current()
        if not e:
            self["live"].setText("")
            self["key_yellow"].setText("")
            self["call"].setText("")
            self["details"].setText(_("No repeaters to show."))
            return
        if e.get("stream_only") and e.get("preset"):
            s = e["stream"]
            self["call"].setText(e["call"])
            self["details"].setText("\n".join([_("Your preset: a BATC stream"), "", s["url"], "",
                                               _("MENU to change or delete it")]))
            self["live"].setText(_("Streaming now: OK or yellow to watch") if s.get("live")
                                 else _("Not in BATC's live list now: OK tries it anyway"))
            self["key_yellow"].setText(_("Watch stream") if not self.tuner.busy else "")
            return
        if e.get("stream_only"):
            self["call"].setText(e["call"])
            self["details"].setText("\n".join([e["town"], "", _("On the BATC streamer only:"),
                                               _("not on the UK repeater list, so"), _("there is nothing to tune on air."),
                                               "", e["stream"]["name"]]))
            self["live"].setText(_("Streaming now on BATC: OK or yellow to watch") if streams.is_live(e["stream"])
                                 else _("Not streaming now: OK tries it anyway"))
            self["key_yellow"].setText(_("Watch stream") if not self.tuner.busy else "")
            return
        o = e["output"]
        if e.get("manual"):
            return self._selected_manual(e)
        lines = [e["town"]]
        if e["km"] is not None:
            lines.append(_("%s%d km from you%s") % ("about " if e["approx"] else "", round(e["km"]),
                                                   " (locator square)" if e["approx"] else ""))
        lines.append("")
        lines.append("%g MHz  %s" % (o["freq_mhz"], e["band"].replace("cm", " cm")))
        mode = o.get("mode") if o.get("mode") not in (None, "digital") else _("Digital")
        lines.append("%s  %s  %s" % (mode, ("%d kS/s" % o["sr_ks"]) if o.get("sr_ks") else _("symbol rate not known"),
                                     ("FEC " + o["fec"]) if o.get("fec") else ""))
        lines.append(_("(as listed; the Lynx bar shows what is received)"))
        if o.get("codec"):
            lines.append(o["codec"])
        lines.append("")
        lines.append(_("Status: %s") % {"on": _("On air"), "off": _("Off air")}.get(e["status"], e["status"]))
        if e.get("hours"):
            lines.append(_("Hours: %s") % e["hours"])
        if e.get("keeper"):
            lines.append(_("Keeper: %s") % e["keeper"])
        lines.append(_("Locator: %s") % e["locator"])
        if e["band"] != "23cm":
            lines.append("")
            lines.append(_("Needs %s") % repeaters.BANDS[e["band"]][3])
        self["call"].setText(e["call"])
        self["details"].setText("\n".join(lines))
        live = bool(e.get("stream")) and not self.tuner.busy
        self["live"].setText(_("Streaming now on BATC: yellow to watch") if e.get("stream") else "")
        self["key_yellow"].setText(_("Watch stream") if live else "")

    def _selected_manual(self, e):
        o = e["output"]
        band = e["band"].replace("cm", " cm") if e["band"] != "direct" else _("straight into the box")
        lines = [_("Your preset") if e.get("preset") else _("Tuned by hand"), "",
                 "%g MHz  %s" % (o["freq_mhz"], band),
                 ("%d kS/s" % o["sr_ks"]) if o.get("sr_ks") else _("Symbol rate: tries them all")]
        if e["lnb_osc_mhz"]:
            lines.append(_("Through an LNB at %d MHz") % e["lnb_osc_mhz"])
        if e.get("preset"):
            lines += ["", _("MENU to change or delete it")]
        self["call"].setText(e["call"])
        self["details"].setText("\n".join(lines))
        live = bool(e.get("stream")) and not self.tuner.busy
        self["live"].setText(_("Streaming now on BATC: yellow to watch") if e.get("stream") else "")
        self["key_yellow"].setText(_("Watch stream") if live else "")

    # Watching

    def watch(self, hunt=False, entry=None):
        e = entry or self._current()
        if not e or self.tuner.busy:
            return
        if e.get("stream_only"):
            return self.watch_stream()
        rec = getattr(self.session.nav, "RecordTimer", None)
        if rec and rec.isRecording():
            self.session.open(MessageBox, _("The box is recording. Stop the recording first."), MessageBox.TYPE_INFO)
            return
        self.stream_timer.stop()
        # The PPM's ffmpeg holds a stream of the tuner on the box's port
        # 8001: let it go first, or the box has no tuner free to scan with.
        if self.bar and self.bar.meter:
            self.bar.meter.stop()
        stop_stray_meters()
        self.watching = None
        self.chat.follow(None)
        self.tuning = e
        self["key_red"].setText(_("Stop"))
        self.tuner.tune(e, cfg.supply.value, hunt)

    def hunt(self):
        self.watch(hunt=True)

    def _progress(self, text):
        self._say(text)

    def _say(self, text):
        """Status line here, and on the Lynx bar while you are watching."""
        self["status"].setText(text)
        if self.bar:
            self.bar.notice(text)

    def _show(self, watching):
        """Open the Lynx bar, or move the open one on to what now plays."""
        self.watching = watching
        self._red()
        self.chat.follow(chat_room(watching, self.sync.streams))
        if self.bar:
            self.bar.set_entry(watching)
        else:
            self.bar = self.session.openWithCallback(self._bar_closed, LynxBar, watching, self)

    def _tuned(self, ref, sr_ks, error):
        self._red()
        e = self.tuning
        if not ref:
            self._say(_("%s: %s") % (e["call"], error))
            return
        self["status"].setText(_("Watching %s at %d kS/s") % (e["call"], sr_ks))
        self._show(dict(e, locked_sr_ks=sr_ks))

    def step(self, by):
        """From the Lynx bar's CH+/CH-: the next repeater in the list, by
        the same route as now where it has one (stream or on air). The bar
        stays up and changes at once; pressing again moves straight on."""
        was_stream = bool(self.watching and self.watching.get("via_stream"))
        rows = self["list"].list
        if not rows:
            return
        if self.tuner.busy:
            self.tuner.cancel()
        self.stream_timer.stop()
        i = (self["list"].getIndex() + by) % len(rows)
        self["list"].setIndex(i)
        e = rows[i][0]
        if self.bar:
            self.bar.set_entry(dict(e, locked_sr_ks=None, pending=True))
        if e.get("stream_only") or (was_stream and e.get("stream")):
            self.watch_stream()
        else:
            self.watch()

    def programme(self, by=0):
        """From the Lynx bar's left/right: the next programme on the same
        repeater (a scan finds them all). Returns (number, how many) for
        what plays afterwards, or None when there is only one."""
        progs = self.tuner.programmes
        if (len(progs) < 2 or self.tuner.busy or not self.watching
                or self.watching.get("via_stream")):
            return None
        cur = self._playing()
        cur = cur.toString() if cur else ""
        i = next((n for n, r in enumerate(progs) if same_service(r, cur)), 0)
        if by:
            i = (i + by) % len(progs)
            self.session.nav.playService(eServiceReference(progs[i]))
            log("programme %d of %d: %s" % (i + 1, len(progs), progs[i]))
        return i + 1, len(progs)

    def _child_closed(self):
        self.child_closed_at = time.time()

    def _bar_closed(self, leave=False):
        self.bar = None
        self._child_closed()
        self._touched()
        if leave:
            self.close()

    def _adopt_playing(self):
        """Lynx opened over a channel it did not start: if it is a repeater
        or a BATC stream on the list, treat it as watched."""
        if self.watching:
            return
        cur = self._playing()
        if cur is None:
            return
        rows = [r[0] for r in self["list"].list]
        try:
            name = self.session.nav.getCurrentService().info().getName()
        except Exception:
            name = ""
        found = match_playing(rows, cur.toString(), name)
        if found:
            self.watching = found
            self["status"].setText(_("Watching %s") % found["call"])
            self._touched()
        self._red()

    def _something_playing(self):
        return self._playing() is not None

    def _hide_list(self):
        self.hidden = True
        self.hide()
        self["unhide"].setEnabled(True)

    def _unhide(self):
        self.hidden = False
        self["unhide"].setEnabled(False)
        self.show()

    def _red(self):
        """Red: Stop while tuning, Close menu (back to the picture) while
        something plays, nothing otherwise. It never leaves Lynx."""
        if self.tuner.busy or self.stream_timer.isActive():
            self["key_red"].setText(_("Stop"))
        elif self.watching or self._something_playing():
            self["key_red"].setText(_("Close menu"))
        else:
            self["key_red"].setText("")

    def _touched(self):
        """Any use of the list: start its 10 s again if something is playing."""
        self.idle_timer.stop()
        if self.watching and self.bar is None:
            self.idle_timer.start(LIST_IDLE_MS, True)

    def _idle(self):
        if self.session.current_dialog is not self:
            return                       # a menu or settings is open: leave it be
        if self.watching and self.bar is None and not self.tuner.busy and not self.stream_timer.isActive():
            self._show(self.watching)

    def back(self):
        """EXIT or red on the list: stop a tune in progress, never leave
        Lynx. Leaving is MENU, Leave Lynx, so a stray press cannot do it."""
        if time.time() - getattr(self, "child_closed_at", 0) < CHILD_CLOSED_GRACE_S:
            return                       # the tail end of the EXIT that closed a menu
        if self.tuner.busy or self.stream_timer.isActive():
            self.stream_timer.stop()
            self.tuner.cancel()
            self["status"].setText(_("Stopped"))
            self._red()
            return
        if self.watching:
            return self._show(self.watching)     # back to the picture
        if self._something_playing():
            return self._hide_list()             # a channel Lynx does not know
        self["status"].setText(_("To leave Lynx: MENU, then Leave Lynx"))

    def leave(self):
        """MENU, Leave Lynx: the one way out. What is playing carries on."""
        self.stream_timer.stop()
        if self.tuner.busy:
            self.tuner.cancel()
        if not self.watching and self.old_service and self._playing() is None:
            self.session.nav.playService(self.old_service)   # put back what was on
        self.close()

    # On the Lynx bar, the same repeater either way without going back to
    # the list (Justin, 2 Nov 2026): green on air, yellow its BATC stream;
    # yellow again on the stream tries the other player.

    def bar_green(self):
        w = self.watching
        if not w or self.tuner.busy or not w.get("via_stream"):
            return                                   # already on air, or tuning
        if not w.get("output"):
            self._say(_("%s is on the BATC streamer only: nothing to tune on air") % w["call"])
            return
        e = plain_entry(w)
        if self.bar:
            self.bar.set_entry(dict(e, locked_sr_ks=None, pending=True))
        self.watch(entry=e)

    def bar_yellow(self):
        w = self.watching
        if not w or self.tuner.busy:
            return
        if w.get("via_stream"):
            return self.other_player()
        if not w.get("stream"):
            self._say(_("%s is not streaming on BATC now") % w["call"])
            return
        self.watch_stream(plain_entry(w))

    def watch_stream(self, entry=None):
        e = entry or self._current()
        if not e or not e.get("stream") or self.tuner.busy:
            return
        self.stream_entry = e
        self.players = streams.player_chain(cfg.player.value)
        self.player_i = 0
        self.auto_retried = False          # Lynx's own second try, once per stream
        self._play_stream()

    # Yellow on the Lynx bar swaps players by hand. Lynx also does it once by
    # itself when the box's video decoder still has no picture 12 s into a
    # stream (decoder_has_picture(): the test found in the 2 Nov 2026 log),
    # and logs every sign of video meanwhile.

    def _play_stream(self):
        e = self.stream_entry
        self.stype = self.players[self.player_i]
        self.session.nav.playService(eServiceReference(streams.service_ref(e["stream"], self.stype)))
        name = streams.PLAYER_NAMES.get(self.stype, self.stype)
        self["status"].setText(_("Watching %s on the BATC streamer (%s)") % (e["call"], name))
        self._show(dict(e, locked_sr_ks=None, via_stream=True, player=self.stype,
                        other_player=len(self.players) > 1))
        self.diag_left = STREAM_DIAG_S
        self.diag_timer.start(1000, True)

    def other_player(self):
        """Yellow on the Lynx bar while on a stream: the next player."""
        if not (self.watching and self.watching.get("via_stream")) or len(getattr(self, "players", ())) < 2:
            return
        self.player_i = (self.player_i + 1) % len(self.players)
        self._play_stream()

    def _diag(self):
        signs = video_signs(self.session)
        log("video check %s: %s" % (self.stype, signs))
        self.diag_left -= 1
        seconds = STREAM_DIAG_S - self.diag_left
        # The first readings can still hold the last programme's size.
        if seconds >= STREAM_PICTURE_FROM_S and decoder_has_picture(signs):
            return
        if seconds >= STREAM_PICTURE_BY_S:
            if not getattr(self, "auto_retried", True) and self.watching and self.watching.get("via_stream"):
                # Sound but no picture: the player joined between keyframes.
                # What yellow does by hand, done once by itself (Justin, 2 Nov 2026).
                self.auto_retried = True
                log("stream: no picture after %d s on %s; trying again" % (seconds, self.stype))
                if len(self.players) > 1:
                    self.player_i = (self.player_i + 1) % len(self.players)
                self._play_stream()
                self._say(_("No picture yet: trying again"))
            return
        if self.diag_left > 0:
            self.diag_timer.start(1000, True)

    # MENU: every choice in one place

    def menu(self):
        e = self._current()
        choices = []
        if e and e.get("preset"):
            choices.append((_("Watch %s") % e["call"], self.watch))
            choices.append((_("Change preset %s") % e["call"], lambda: self.manual(e)))
            choices.append((_("Delete preset %s") % e["call"], lambda: self.delete_preset(e)))
        elif e and e.get("stream_only"):
            choices.append((_("Watch %s on the BATC streamer") % e["call"], self.watch_stream))
        elif e:
            choices.append((_("Watch %s on air") % e["call"], self.watch))
            if e.get("stream"):
                choices.append((_("Watch %s on the BATC streamer") % e["call"], self.watch_stream))
            choices.append((_("Watch %s, trying every symbol rate") % e["call"], self.hunt))
        choices.append((_("Tune by hand (frequency and symbol rate)"), self.manual))
        choices.append((_("Add a BATC stream by its name (a member's stream)"), self.add_stream))
        if cfg.streams.value:
            choices.append((_("Update the BATC stream status now (0)"), self.update_streams))
        choices.append((_("BATC chat: hide or report"), lambda: self.session.open(ChatSafety, self.chat)))
        choices.append((_("Settings"), self.settings))
        choices.append((_("Check for a newer Lynx now"), lambda: updater(self.session).check(manual=True)))
        choices.append((_("Leave Lynx"), self.leave))
        self.idle_timer.stop()
        self.session.openWithCallback(self._menu_chosen, ChoiceBox, title=_("Lynx"), list=choices)

    def _menu_chosen(self, choice):
        self._child_closed()
        self._touched()
        if choice:
            choice[1]()

    # Tuning by hand, and presets

    def manual(self, preset_entry=None):
        if self.tuner.busy:
            return
        if preset_entry and preset_entry.get("stream_only"):
            return self.add_stream(preset_entry)
        preset = None
        if preset_entry:
            o = preset_entry["output"]
            preset = {"name": preset_entry["call"], "freq_mhz": o["freq_mhz"], "sr_ks": o.get("sr_ks")}
        self.idle_timer.stop()
        self.session.openWithCallback(self._manual_closed, ManualTune, preset)

    def _manual_closed(self, result=None):
        self._child_closed()
        self.presets = repeaters.load_presets()
        self.refresh()
        self._touched()
        if not result:
            return
        what, x = result
        if what == "watch":
            self.watch(entry=x)
        elif what == "saved":
            self._select_preset(x)

    def add_stream(self, preset_entry=None):
        preset = None
        if preset_entry:
            preset = {"name": preset_entry["call"], "stream": preset_entry["stream"]["key"]}
        self.idle_timer.stop()
        self.session.openWithCallback(self._manual_closed, AddStream, preset)

    def _select_preset(self, name):
        for i, row in enumerate(self["list"].list):
            if row[0].get("preset") and row[0]["call"].lower() == name.lower():
                self["list"].setIndex(i)
                return

    def delete_preset(self, e):
        def done(yes):
            self._child_closed()
            if yes:
                self.presets = repeaters.drop_preset(repeaters.load_presets(), e["call"])
                try:
                    repeaters.save_presets(self.presets)
                except (IOError, OSError) as err:
                    self["status"].setText(_("Could not save the presets: %s") % err)
                self.refresh()
        self.session.openWithCallback(done, MessageBox, _("Delete the preset %s?") % e["call"],
                                      MessageBox.TYPE_YESNO, default=False)

    # Settings

    def settings(self):
        if not self.tuner.busy:
            self.idle_timer.stop()
            self.session.openWithCallback(self._settings_closed, LynxSettings)

    def _welcome(self):
        """The first time Lynx opens, its settings, so the locator and Open
        Lynx at start-up are not missed. Not for a box already set up."""
        if cfg.welcomed.value:
            return
        cfg.welcomed.value = True
        cfg.welcomed.save()
        configfile.save()
        if not cfg.locator.value.strip():
            self.welcome_timer.start(300, True)      # once the list is on screen

    def _welcome_now(self):
        if self.session.current_dialog is self and not self.tuner.busy:
            self.idle_timer.stop()
            self.session.openWithCallback(self._settings_closed, LynxSettings, True)

    def _settings_closed(self, *args):
        self._child_closed()
        self.refresh()
        self._touched()


def _bar_skin(with_ppm):
    """The Lynx bar, with the PPM at its left end when it is shown (the
    text moves along to make room) and the magic eye at the right."""
    x = 150 if with_ppm else 40
    ppm = ""
    if with_ppm:
        # All four layers are named widgets: Enigma2 creates named widgets in
        # the order the screen adds them, and plain ePixmaps after all of
        # them, on top (Screen.createGUIScreen). As ePixmaps the housing and
        # screw hid the needles (1 Nov 2026).
        ppm = ('<widget zPosition="1" name="ppm_housing" position="24,10" size="110,110" alphatest="blend" pixmap="%s"/>'
               '<widget zPosition="1" name="ppm_green" position="24,10" size="110,110" alphatest="blend" pixmaps="%s"/>'
               '<widget zPosition="1" name="ppm_red" position="24,10" size="110,110" alphatest="blend" pixmaps="%s"/>'
               '<widget zPosition="1" name="ppm_screw" position="24,10" size="110,110" alphatest="blend" pixmap="%s"/>' % (
                   PPM_PIXMAPS["housing"], ",".join(PPM_PIXMAPS["green"]), ",".join(PPM_PIXMAPS["red"]),
                   PPM_PIXMAPS["screw"]))
    return _scale("""
<screen name="LynxBar" position="60,930" size="1800,130" backgroundColor="#00141414" flags="wfNoBorder">
  <eLabel position="0,0" size="12,130" backgroundColor="#00d0021b"/>
""" + ppm + """
  <widget zPosition="1" name="call" position="%d,8" size="420,70" font="Regular;54" noWrap="1" foregroundColor="#00ffffff" backgroundColor="#00141414"/>
  <widget zPosition="1" name="where" position="%d,8" size="%d,70" font="Regular;36" valign="center" noWrap="1" foregroundColor="#00ffffff" backgroundColor="#00141414"/>
  <widget zPosition="1" name="signal" position="1140,8" size="510,70" font="Regular;36" halign="right" valign="center" foregroundColor="#00ffd200" backgroundColor="#00141414"/>
  <widget zPosition="1" name="tech" position="%d,78" size="%d,44" font="Regular;28" valign="center" foregroundColor="#00c0c0c0" backgroundColor="#00141414"/>
  <widget zPosition="1" name="hint" position="1240,78" size="410,44" font="Regular;20" halign="right" valign="center" foregroundColor="#00909090" backgroundColor="#00141414"/>
""" % (x, x + 430, 1140 - (x + 430), x, 1240 - x) + (
        '<widget zPosition="1" name="eye" position="1670,10" size="110,110" alphatest="blend" pixmaps="%s"/>' % ",".join(EYE_PIXMAPS)
        if EYE_PIXMAPS else "") + """
</screen>""")


BAR_SKIN = _bar_skin(False)
BAR_SKIN_PPM = _bar_skin(True) if PPM_PIXMAPS else BAR_SKIN


def plain_entry(watching):
    """The list's row for what is being watched, without how it is watched."""
    return dict((k, v) for k, v in watching.items()
                if k not in ("via_stream", "player", "other_player", "locked_sr_ks", "pending"))


def bar_hint(entry):
    """The Lynx bar's key hint: what green and yellow do from here."""
    if entry.get("via_stream"):
        swap = _("YELLOW player") if entry.get("other_player") else ""
        if entry.get("output"):
            return "  ".join(x for x in (_("GREEN on air"), swap, _("EXIT list")) if x)   # the hint is 410 px wide
        return "  ".join(x for x in (_("CH+/- next"), swap, _("EXIT list")) if x)
    if entry.get("stream"):
        return _("YELLOW stream  CH+/- next  EXIT list")
    return _("CH+/- next   OK hide   EXIT list")


def chat_room(entry, listed=()):
    """The BATC stream whose chat goes with what is watched, on air or as a
    stream: the row's own stream, or else the one named after its callsign
    in BATC's list even when it is not streaming now. None if neither."""
    entry = entry or {}
    s = entry.get("stream")
    if not isinstance(s, dict) and not entry.get("manual"):
        s = streams.chat_for(listed or [], entry.get("call"))
    return s.get("key") if isinstance(s, dict) else None


_BUBBLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bubble")
CHAT_SLOTS = 3                         # bubbles on screen at once, newest at the bottom
CHAT_W = 640                           # as tools/make_bubble.py draws them, at Full HD
BUBBLE = {"pad": 16, "who": 38, "line": 36, "tail": 12, "tip": 14, "lines": 8, "inset": 26,
          "left": 34, "right": 48, "blue": "#000a84ff"}


def _bubble_pixmaps():
    """The bubbles' two ends, (left, right) for 1 to 8 lines; None if missing.
    A plain blue box between them is as wide as the message."""
    if not MultiPixmap:
        return None
    folder = _BUBBLE_DIR if _factor() > 0.8 else os.path.join(_BUBBLE_DIR, "hd")
    n = range(1, BUBBLE["lines"] + 1)
    left = [os.path.join(folder, "left_%d.png" % k) for k in n]
    right = [os.path.join(folder, "right_%d.png" % k) for k in n]
    return (left, right) if all(os.path.exists(p) for p in left + right) else None


BUBBLE_PIXMAPS = _bubble_pixmaps()


def _bubble_lines(height, line):
    """Lines of text in a message 'height' pixels tall: rounded up (a part
    line is still a line to show), 1 to the tallest bubble."""
    import math
    return max(1, min(BUBBLE["lines"], int(math.ceil(height / float(line) - 0.3))))


def _chat_skin():
    b, text_w = BUBBLE, CHAT_W - BUBBLE["tip"] - 2 * BUBBLE["inset"]
    tallest = b["pad"] * 2 + b["who"] + b["line"] * b["lines"] + b["tail"]
    slots = ""
    for i in range(CHAT_SLOTS):
        slots += '<widget name="mid%d" position="0,0" size="%d,100" zPosition="1" backgroundColor="%s"/>' % (
            i, CHAT_W, b["blue"])
        if BUBBLE_PIXMAPS:
            slots += ('<widget name="left%d" position="0,0" size="%d,%d" zPosition="1" alphatest="blend" pixmaps="%s"/>'
                      '<widget name="right%d" position="0,0" size="%d,%d" zPosition="1" alphatest="blend" pixmaps="%s"/>'
                      % (i, b["left"], tallest, ",".join(BUBBLE_PIXMAPS[0]),
                         i, b["right"], tallest, ",".join(BUBBLE_PIXMAPS[1])))
        slots += ('<widget name="who%d" position="%d,%d" size="%d,%d" zPosition="2" font="Regular;26" noWrap="1" '
                  'foregroundColor="#00d6e8ff" transparent="1"/>'
                  '<widget name="said%d" position="%d,%d" size="%d,400" zPosition="2" font="Regular;30" '
                  'foregroundColor="#00ffffff" transparent="1"/>') % (
                      i, b["inset"], b["pad"], text_w, b["who"], i, b["inset"], b["pad"] + b["who"], text_w)
    return _scale('<screen name="LynxChat" position="1240,40" size="%d,820" zPosition="5" flags="wfNoBorder" '
                  'backgroundColor="#ff000000">%s</screen>' % (CHAT_W, slots))


class ChatBubbles(Screen):
    """New BATC chat messages over the picture in blue bubbles, like texts
    on a phone: right-aligned, as wide as the message, each up 10 s (a
    second more for each line past two), then gone."""

    skin = _chat_skin()
    GAP = 12                                         # between bubbles, Full HD pixels

    def __init__(self, session):
        Screen.__init__(self, session)
        import threading
        for i in range(CHAT_SLOTS):
            self["mid%d" % i] = Label()
            if BUBBLE_PIXMAPS:
                self["left%d" % i] = MultiPixmap()
                self["right%d" % i] = MultiPixmap()
            self["who%d" % i] = Label()
            self["said%d" % i] = Label()
        self.lock = threading.Lock()
        # Not "shown": Screen uses that name for whether it is on screen
        # (the first try crashed on it, 2 Nov 2026).
        self.incoming, self.bubbles = [], []        # bubbles: [name, text, hhmm, until]
        self.paused = False                          # the Lynx list is up: no bubbles over it
        self.timer, self._t = _timer(self._tick)
        self.onClose.append(self.timer.stop)
        self.timer.start(500, False)

    def heard(self, name, text, hhmm):
        """From the chat listener's thread: handed over on the next tick."""
        with self.lock:
            self.incoming.append((name, text, hhmm))

    def clear(self):
        with self.lock:
            self.incoming = []
        self.bubbles = []
        self._layout()

    def _tick(self):
        with self.lock:
            new, self.incoming = self.incoming, []
        now = time.time()
        changed = bool(new)
        for name, text, hhmm in new:
            self.bubbles.append([name, text, hhmm, None])
        if len(self.bubbles) > CHAT_SLOTS:
            self.bubbles = self.bubbles[-CHAT_SLOTS:]
        keep = [b for b in self.bubbles if b[3] is None or b[3] > now]
        if len(keep) != len(self.bubbles):
            self.bubbles, changed = keep, True
        if changed:
            self._layout()

    def _parts(self, i):
        names = ["mid", "who", "said"] + (["left", "right"] if BUBBLE_PIXMAPS else [])
        return [self["%s%d" % (n, i)] for n in names]

    def _layout(self):
        from .chat import show_for
        b = BUBBLE
        f = _factor()
        px = lambda v: int(round(v * f))
        text_w = CHAT_W - b["tip"] - 2 * b["inset"]
        y, now = 0, time.time()
        self._fit(px, text_w)
        for i in range(CHAT_SLOTS):
            parts = self._parts(i)
            mid, who, said = parts[:3]
            if i >= len(self.bubbles) or said.instance is None:
                for w in parts:
                    w.hide()
                continue
            msg = self.bubbles[i]
            who.instance.resize(eSize(px(text_w), px(b["who"])))
            who.setText("%s   %s" % (msg[0], msg[2]))
            said.instance.resize(eSize(px(text_w), px(b["line"] * 30)))
            said.setText(msg[1])
            size = said.instance.calculateSize()
            # Longer than the tallest bubble: cut at a word, with "..." (Justin,
            # 2 Nov 2026: long messages were cut off). Once, then kept.
            while size.height() > px(b["line"] * b["lines"]) + px(b["line"]) // 2 and " " in msg[1]:
                body = msg[1][:-3] if msg[1].endswith("...") else msg[1]
                msg[1] = body.rsplit(" ", 1)[0].rstrip(".,;:") + "..."
                said.setText(msg[1])
                size = said.instance.calculateSize()
            lines = _bubble_lines(size.height(), px(b["line"]))
            if msg[3] is None:                    # its clock starts when it first shows
                msg[3] = now + show_for(lines)
            # As wide as the longer of the name line and the message; a message
            # of more than one line keeps the full width, as a narrower box
            # wraps it onto more lines than were counted (Justin, 2 Nov 2026:
            # "not scaling past 3 lines").
            text = min(px(text_w), max(size.width(), who.instance.calculateSize().width()) + px(4))
            if lines > 1:
                text = px(text_w)
            body_w = max(text + 2 * px(b["inset"]), px(b["left"] + b["right"] - b["tip"] + 8))
            body_h = px(b["pad"] * 2 + b["who"] + b["line"] * lines)
            x = px(CHAT_W - b["tip"]) - body_w          # right-aligned, the tail to its right
            if BUBBLE_PIXMAPS:
                left, right = parts[3], parts[4]
                left.setPixmapNum(lines - 1)
                right.setPixmapNum(lines - 1)
                left.instance.move(ePoint(x, px(y)))
                right.instance.move(ePoint(x + body_w - px(b["right"] - b["tip"]), px(y)))
                mid.instance.move(ePoint(x + px(b["left"]), px(y)))
                mid.instance.resize(eSize(body_w - px(b["left"]) - px(b["right"] - b["tip"]), body_h))
            else:                                     # no pictures: a plain blue box
                mid.instance.move(ePoint(x, px(y)))
                mid.instance.resize(eSize(body_w, body_h))
            who.instance.move(ePoint(x + px(b["inset"]), px(y + b["pad"])))
            who.instance.resize(eSize(text, px(b["who"])))
            said.instance.move(ePoint(x + px(b["inset"]), px(y + b["pad"] + b["who"])))
            said.instance.resize(eSize(text, px(b["line"] * lines)))
            for w in parts:
                w.show()
            y += b["pad"] * 2 + b["who"] + b["line"] * lines + b["tail"] + self.GAP
        if self.bubbles and not self.paused:
            self.show()
        else:
            self.hide()

    TALL = 820                                       # the overlay's height, Full HD pixels

    def _fit(self, px, text_w):
        """Oldest bubbles go early when three long ones would not fit in the
        overlay (as on Lynx-Tx): the newest message always shows whole."""
        b, said = BUBBLE, self["said0"]
        if said.instance is None:
            return
        while len(self.bubbles) > 1:
            total = 0
            for msg in self.bubbles:
                said.instance.resize(eSize(px(text_w), px(b["line"] * 30)))
                said.setText(msg[1])
                h = said.instance.calculateSize().height()
                lines = _bubble_lines(h, px(b["line"]))
                total += b["pad"] * 2 + b["who"] + b["line"] * lines + b["tail"] + self.GAP
            if total - self.GAP <= self.TALL:
                return
            self.bubbles.pop(0)

    def pause(self, paused):
        self.paused = paused
        self._layout()


class ChatOverlay(object):
    """The bubbles and the listener for the stream being watched."""

    START_MS = 6000                    # let the picture start first (Justin: streams were slower to start)

    def __init__(self, session):
        import collections
        import threading
        from .chat import RECENT, load_hidden
        self.session, self.room, self.listener = session, None, None
        self.dialog = session.instantiateDialog(ChatBubbles)
        self.later, self._l = _timer(self._start)
        self.hidden = load_hidden()
        self.recent = collections.deque(maxlen=RECENT)   # (name, text, hhmm), for hide or report
        self.lock = threading.Lock()

    def heard(self, name, text, hhmm):
        """From the listener's thread: kept for the hide or report screen,
        and shown unless the viewer has hidden that sender."""
        from .chat import is_hidden
        with self.lock:
            self.recent.append((name, text, hhmm))
        if not is_hidden(name, self.hidden):
            self.dialog.heard(name, text, hhmm)

    def messages(self):
        with self.lock:
            return list(self.recent)

    def set_hidden(self, names):
        from .chat import save_hidden
        self.hidden = list(names)
        try:
            save_hidden(self.hidden)
        except (IOError, OSError) as e:
            log("chat: could not save hidden senders: %s" % e)

    def follow(self, room):
        if not cfg.chat.value:
            room = None
        if room == self.room:
            return
        if self.listener:
            self.listener.stop()
            self.listener = None
        self.later.stop()
        self.room = room
        self.dialog.clear()
        if room:
            self.later.start(self.START_MS, True)

    def _start(self):
        if not self.room or self.listener:
            return
        from .chat import Listener
        try:
            self.listener = Listener(self.room, self.heard, log)
            self.listener.start()
        except ValueError:
            self.listener = None

    def close(self):
        self.later.stop()
        self.follow(None)
        self.dialog.hide()
        self.session.deleteDialog(self.dialog)


class LynxBar(Screen):
    skin = BAR_SKIN

    def __init__(self, session, entry, owner=None):
        # The PPM's widgets only when it is shown: its own skin name, so the
        # two layouts are never mixed up.
        # Python 3 only: the layers rely on the screen keeping the order they
        # were added in, which Python 2's dictionaries do not.
        self.with_ppm = bool(cfg.ppm.value and PPM_PIXMAPS and sys.version_info >= (3, 7))
        if self.with_ppm:
            self.skin, self.skinName = BAR_SKIN_PPM, "LynxBarPPM"
        Screen.__init__(self, session)
        self.entry, self.owner = entry, owner
        self.notice_text = None
        big, beside = title_text(entry, {})
        self["call"] = Label(big)
        self["where"] = Label(beside)
        self["tech"] = Label(self._tech({}))
        self["signal"] = Label()
        self["hint"] = Label()
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
            "ok": self.toggle,
            "green": lambda: self.owner and self.owner.bar_green(),
            "yellow": lambda: self.owner and self.owner.bar_yellow(),
            "cancel": lambda: self.close(False),
        }, -1)
        # CH+/CH- and the up/down arrows step through Lynx's own list. The
        # channel keys' action names differ between images, so all are bound.
        nxt, prv = lambda: self._zap(1), lambda: self._zap(-1)
        self["zap"] = ActionMap(["DirectionActions", "InfobarChannelSelection", "ChannelSelectBaseActions"], {
            "up": prv, "down": nxt,
            "zapUp": prv, "zapDown": nxt,
            "switchChannelUp": prv, "switchChannelDown": nxt,
            "nextBouquet": nxt, "prevBouquet": prv,
            # Left/right: the other programmes on the same repeater.
            "left": lambda: self._programme(-1), "right": lambda: self._programme(1),
        }, -1)
        self.visible = True
        self.timer, self._tc = _timer(self.update)
        self.onShown.append(self._start)
        self.onClose.append(self.timer.stop)
        # The magic eye: SNR above what the locked MODCOD needs.
        self.modcod = {}
        self.eye_amount, self.eye_shown = 0.0, None
        if EYE_PIXMAPS:
            self["eye"] = MultiPixmap()
            self.eye_timer, self._et = _timer(self._eye)
            self.onClose.append(self.eye_timer.stop)
        # The PPM: needles at rest until the sound is metered.
        self.meter, self.ppm_shown, self.ppm_on = None, (None, None), True
        if self.with_ppm:
            from Components.Pixmap import Pixmap
            self["ppm_housing"] = Pixmap()          # bottom to top, in this order
            self["ppm_green"] = MultiPixmap()
            self["ppm_red"] = MultiPixmap()
            self["ppm_screw"] = Pixmap()
            self.meter = PPMMeter()
            self.ppm_timer, self._pt = _timer(self._ppm)
            self.onClose.append(self.ppm_timer.stop)
            self.onClose.append(self.meter.stop)

    def _zap(self, by):
        if self.owner:
            if not self.visible:
                self.toggle()
            self.owner.step(by)

    def _programme(self, by):
        if not self.owner:
            return
        if not self.visible:
            self.toggle()
        if self.owner.programme(by):
            self.update()

    def set_entry(self, entry):
        """Now showing something else (or about to)."""
        self.entry, self.notice_text = entry, None
        if entry.get("pending"):
            self.notice_text = _("Tuning...")
        self.update()

    def notice(self, text):
        """Progress or a problem, shown in place of the technical line until
        the next repeater plays."""
        self.notice_text = text
        self.update()

    def _start(self):
        self.update()
        self.timer.start(1000, False)
        if self.meter:
            self.ppm_timer.start(PPM_MS, False)
        if EYE_PIXMAPS:
            self.eye_timer.start(EYE_MS, False)

    def _on_air(self):
        return not (self.entry.get("via_stream") or self.entry.get("pending") or self.notice_text)

    def _margin(self, db):
        return margin_db(db, self.modcod.get("modulation"), self.modcod.get("fec"),
                         self.modcod.get("system", "DVB-S2"))

    def _eye(self):
        if not self.visible:
            return
        on_air = self._on_air()
        db, q, locked = signal(self.session) if on_air else (None, None, False)
        dbm = level(self.session) if on_air and locked else None
        target = eye_closure(locked, db, self._margin(db), dbm)
        self.eye_amount += EYE_EASE * (target - self.eye_amount)
        n = eye_frame(self.eye_amount, bool(locked))
        if n == self.eye_shown:
            return                        # same picture: nothing to do
        self.eye_shown = n
        log("eye %s: snr %s margin %s dbm %s mod %s fec %s target %.2f" % (
            n, db, self._margin(db), dbm, self.modcod.get("modulation"), self.modcod.get("fec"), target))
        self["eye"].setPixmapNum(EYE_FRAMES if n == "off" else n)

    def _ppm_source(self):
        """What the PPM should meter: the on-air programme playing, from its
        demux (with the box's own stream on port 8001 to fall back on), or
        nothing (streams: not yet, it would mean a second connection to BATC)."""
        if self.entry.get("via_stream") or self.entry.get("pending") or self.notice_text:
            return None
        try:
            ref = self.session.nav.getCurrentlyPlayingServiceReference()
            ref = ref and ref.toString()
        except Exception:
            return None
        if not ref or not ref.startswith("1:"):
            return None
        url = "http://127.0.0.1:8001/" + ref
        try:
            from .ppm import tap_plan
            service = self.session.nav.getCurrentService()
            stream = service and service.stream()
            plan = tap_plan(stream and stream.getStreamingData())
        except Exception:
            plan = None
        if plan:
            return ("tap", plan, url)
        # Just after a tune the service may not yet say its PIDs: wait for
        # them rather than start on port 8001 and switch a second later
        # (seen 2 Nov 2026). Port 8001 only where the demux will not open.
        return ("url", url) if self.meter and self.meter.tap_failed else None

    def _show_ppm(self, show):
        """Shows or hides the PPM, sliding the text along to match the
        skin's layout with or without it."""
        if show == self.ppm_on or self["call"].instance is None:
            return
        self.ppm_on = show
        for name in ("ppm_housing", "ppm_green", "ppm_red", "ppm_screw"):
            if show:
                self[name].show()
            else:
                self[name].hide()
        x, f = (150 if show else 40), _factor()
        for name, left, width in (("call", x, 420), ("where", x + 430, 1140 - (x + 430)), ("tech", x, 1240 - x)):
            inst = self[name].instance
            if inst is not None:
                inst.move(ePoint(int(round(left * f)), inst.position().y()))
                inst.resize(eSize(int(round(width * f)), inst.size().height()))

    def _ppm(self):
        if not self.visible:
            return
        from .ppm import frame as ppm_frame
        left, right = self.meter.positions()
        shown = (ppm_frame(left), ppm_frame(right))
        if shown != self.ppm_shown:
            self.ppm_shown = shown
            self["ppm_red"].setPixmapNum(shown[0])
            self["ppm_green"].setPixmapNum(shown[1])

    def update(self):
        # Live values every second: what was actually locked and decoded,
        # never the list's idea of FEC or codec.
        if self.meter:
            # Streams cannot be metered (no copy of their sound to take), so
            # the meter goes and the text closes up (Justin, 2 Nov 2026).
            self._show_ppm(not self.entry.get("via_stream"))
            url = self._ppm_source()
            if url:
                self.meter.start(url)
            else:
                self.meter.stop()
        prog = self.owner.programme() if self.owner and not self.entry.get("pending") else None
        if prog:
            self["hint"].setText(_("< > programme %d/%d   CH+/- next   EXIT list") % prog)
        else:
            self["hint"].setText(bar_hint(self.entry))
        waiting = self.entry.get("pending") or self.notice_text
        p = {} if waiting else live(self.session)
        self.modcod = p
        big, beside = title_text(self.entry, p)
        self["call"].setText(big)
        self["where"].setText(beside)
        if waiting:
            self["signal"].setText("")
            self["tech"].setText(self.notice_text or "")
            return
        if self.entry.get("via_stream"):
            self["signal"].setText(_("BATC stream"))
        else:
            db = signal(self.session)[0]
            self["signal"].setText(signal_text(self.session, self._margin(db)))
        self["tech"].setText(self._tech(p))

    def _tech(self, p):
        if self.entry.get("via_stream"):
            return "   ".join([_("Internet stream from the BATC streamer")] +
                               (["%dx%d" % p["size"]] if p.get("size") else []))
        # The supply Lynx puts up the cable (set by polarisation): real, unlike
        # the driver's echoed system, roll-off and FEC on this box.
        supply = _("LNB off") if cfg.supply.value == "off" else "LNB %s V" % cfg.supply.value
        text = "%s   %s" % (tech_text(self.entry["output"]["freq_mhz"], p, self.entry["locked_sr_ks"]), supply)
        dbm = level(self.session)
        if dbm is None:
            return text
        if dbm <= LEVEL_FLOOR_DBM:
            # The tuner is at full gain: it cannot tell any lower (H11S,
            # 21 Oct 2026: 20 % at both -39 and -40 dB). The eye still can.
            return text + "   " + _("below %d dBm") % LEVEL_FLOOR_DBM
        return text + "   %.0f dBm" % dbm

    def toggle(self):
        self.visible = not self.visible
        self.show() if self.visible else self.hide()


class LynxSettings(ConfigListScreen, Screen):
    skin = _scale("""
<screen name="LynxSettings" position="center,center" size="1300,780" title="Lynx settings" backgroundColor="#00141414" flags="wfNoBorder">
  <eLabel position="0,0" size="1300,90" backgroundColor="#00d0021b"/>
  <eLabel text="Lynx settings" position="40,0" size="1200,90" font="Regular;40" valign="center" foregroundColor="#00ffffff" backgroundColor="#00d0021b"/>
  <widget zPosition="1" name="config" position="30,110" size="1240,450" font="Regular;30" itemHeight="50" scrollbarMode="showOnDemand" backgroundColor="#00141414"/>
  <widget zPosition="1" name="help" position="40,575" size="1220,110" font="Regular;26" foregroundColor="#00c0c0c0" backgroundColor="#00141414"/>
  <eLabel position="40,710" size="8,44" backgroundColor="#00d0021b"/>
  <widget zPosition="1" source="key_red" render="Label" position="56,710" size="300,44" font="Regular;30" valign="center" transparent="1"/>
  <eLabel position="400,710" size="8,44" backgroundColor="#0000a03c"/>
  <widget zPosition="1" source="key_green" render="Label" position="416,710" size="300,44" font="Regular;30" valign="center" transparent="1"/>
</screen>""")

    def __init__(self, session, welcome=False):
        Screen.__init__(self, session)
        self.setTitle(_("Lynx settings"))
        items = [
            getConfigListEntry(_("Your locator (JO01AJ or JO01)"), cfg.locator),
            getConfigListEntry(_("LNB supply on the cable"), cfg.supply),
            getConfigListEntry(_("9 cm LNB oscillator (MHz)"), cfg.osc_9cm),
            getConfigListEntry(_("3 cm LNB oscillator (MHz)"), cfg.osc_3cm),
            getConfigListEntry(_("Show repeaters listed as off air"), cfg.show_off),
            getConfigListEntry(_("Open Lynx at start-up"), cfg.autostart),
            getConfigListEntry(_("BATC live streams (checked hourly)"), cfg.streams),
            getConfigListEntry(_("Every BATC stream in the list, not only repeaters"), cfg.all_streams),
            getConfigListEntry(_("Player for streams"), cfg.player),
            getConfigListEntry(_("Lynx updates at start-up"), cfg.update_check),
            getConfigListEntry(_("PPM audio meter on the Lynx bar (RF only)"), cfg.ppm),
            getConfigListEntry(_("BATC chat on the picture"), cfg.chat),
        ]
        ConfigListScreen.__init__(self, items, session=session)
        if welcome:
            text = _("Welcome to Lynx. Enter your locator, so the list is sorted by distance, and switch on "
                     "Open Lynx at start-up to come straight here whenever the box starts. Green saves.")
        else:
            text = _("Type the locator with the number keys, or press TEXT for an on-screen keyboard; "
                     "upper or lower case both work. LNB supply off also cuts power to a 19.2E dish on this tuner. "
                     "Lynx-Enigma2 %s") % VERSION
        self["help"] = Label(text)
        self["key_red"] = StaticText(_("Cancel"))
        self["key_green"] = StaticText(_("Save"))
        self["lynx_actions"] = ActionMap(["SetupActions", "ColorActions"], {
            "save": self.save,
            "green": self.save,
            "cancel": self.cancel,
            "red": self.cancel,
        }, -2)

    def save(self):
        loc = repeaters.clean_locator(cfg.locator.value)
        if loc and not repeaters.valid_locator(loc):
            self.session.open(MessageBox, _("%s is not a locator. Use four or six characters, such as JO01 or JO01AJ.") % loc,
                              MessageBox.TYPE_ERROR)
            return
        cfg.locator.value = loc
        player_changed = cfg.player.isChanged()
        if cfg.supply.isChanged():
            from . import lnbpower
            if not lnbpower.apply(cfg.supply.value == "off") and cfg.supply.value == "off":
                self.session.open(MessageBox, _("This box's software cannot switch the LNB supply off."),
                                  MessageBox.TYPE_ERROR)
                return
        for item in self["config"].list:
            item[1].save()
        configfile.save()
        if player_changed:
            sync.get().rewrite_bouquet()
        self.close(True)

    def cancel(self):
        for item in self["config"].list:
            item[1].cancel()
        self.close(False)


class ManualTune(ConfigListScreen, Screen):
    """A frequency and symbol rate typed in. Green watches it; yellow keeps
    it as a preset at the top of the list."""
    skin = _scale("""
<screen name="LynxManualTune" position="center,center" size="1300,560" title="Tune by hand" backgroundColor="#00141414" flags="wfNoBorder">
  <eLabel position="0,0" size="1300,90" backgroundColor="#00d0021b"/>
  <widget zPosition="1" name="title" position="40,0" size="1200,90" font="Regular;40" valign="center" foregroundColor="#00ffffff" backgroundColor="#00d0021b"/>
  <widget zPosition="1" name="config" position="30,110" size="1240,160" font="Regular;30" itemHeight="50" scrollbarMode="showOnDemand" backgroundColor="#00141414"/>
  <widget zPosition="1" name="help" position="40,290" size="1220,180" font="Regular;26" foregroundColor="#00c0c0c0" backgroundColor="#00141414"/>
  <eLabel position="40,490" size="8,44" backgroundColor="#00d0021b"/>
  <widget zPosition="1" source="key_red" render="Label" position="56,490" size="300,44" font="Regular;30" valign="center" transparent="1"/>
  <eLabel position="400,490" size="8,44" backgroundColor="#0000a03c"/>
  <widget zPosition="1" source="key_green" render="Label" position="416,490" size="300,44" font="Regular;30" valign="center" transparent="1"/>
  <eLabel position="760,490" size="8,44" backgroundColor="#00e6b800"/>
  <widget zPosition="1" source="key_yellow" render="Label" position="776,490" size="400,44" font="Regular;30" valign="center" transparent="1"/>
</screen>""")

    def __init__(self, session, preset=None):
        Screen.__init__(self, session)
        self.preset = preset
        if preset:
            freq, sr, name = preset["freq_mhz"], preset.get("sr_ks"), preset["name"]
            sr = str(sr) if sr in repeaters.MANUAL_SR_KS else "any"
        else:
            freq, sr, name = cfg.manual_freq.value, cfg.manual_sr.value, ""
        self.freq = ConfigInteger(default=int(round(freq)), limits=(950, 10500))
        self.sr = ConfigSelection(default=sr, choices=SR_CHOICES)
        self.name = ConfigText(default=name, fixed_size=False)
        title = _("Change preset %s") % name if preset else _("Tune by hand")
        self.setTitle(title)
        self["title"] = Label(title)
        ConfigListScreen.__init__(self, [
            getConfigListEntry(_("Frequency (MHz)"), self.freq),
            getConfigListEntry(_("Symbol rate"), self.sr),
            getConfigListEntry(_("Name, to keep it as a preset"), self.name),
        ], session=session)
        self["help"] = Label(_("Type the frequency with the number keys; left and right choose the symbol rate. "
                               "23 cm goes straight in; 9 cm and 3 cm go through the LNB oscillators in Settings. "
                               "A preset goes at the top of the Lynx list; MENU there changes or deletes it."))
        self["key_red"] = StaticText(_("Cancel"))
        self["key_green"] = StaticText(_("Watch"))
        self["key_yellow"] = StaticText(_("Save preset"))
        self["lynx_actions"] = ActionMap(["SetupActions", "ColorActions"], {
            "ok": self._ok,
            "save": self.watch,
            "green": self.watch,
            "yellow": self.keep,
            "cancel": lambda: self.close(None),
            "red": lambda: self.close(None),
        }, -2)

    def _ok(self):
        """OK watches, as it does on the list (Justin pressed OK and waited,
        21 Oct 2026), except on the name, where it brings up the keyboard."""
        cur = self["config"].getCurrent()
        if cur and cur[1] is self.name:
            ok = getattr(ConfigListScreen, "keyOK", None)
            return ok(self) if ok else None
        self.watch()

    def _sr(self):
        return None if self.sr.value == "any" else int(self.sr.value)

    def _entry(self, name):
        e = repeaters.manual_entry(self.freq.value, self._sr(), name, lnb_osc())
        if not e:
            self.session.open(MessageBox, _("The box cannot tune %d MHz. 23 cm (1240 to 1325 MHz) goes straight in; "
                                            "9 cm and 3 cm need their LNB oscillator set in Settings.") % self.freq.value,
                              MessageBox.TYPE_ERROR)
        return e

    def watch(self):
        e = self._entry(self.name.value)
        if not e:
            return
        cfg.manual_freq.value, cfg.manual_sr.value = self.freq.value, self.sr.value
        cfg.manual_freq.save()
        cfg.manual_sr.save()
        configfile.save()
        self.close(("watch", e))

    def keep(self):
        name = self.name.value.strip() or "%d MHz" % self.freq.value
        if not self._entry(name):
            return
        preset = {"name": name, "freq_mhz": float(self.freq.value), "sr_ks": self._sr()}
        replacing = self.preset["name"] if self.preset else None
        try:
            repeaters.save_presets(repeaters.put_preset(repeaters.load_presets(), preset, replacing))
        except (IOError, OSError) as err:
            self.session.open(MessageBox, _("Could not save the preset: %s") % err, MessageBox.TYPE_ERROR)
            return
        log("preset saved: %s" % preset)
        self.close(("saved", name))


_QR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qr")


def _qr_pixmap():
    path = os.path.join(_QR_DIR if _factor() > 0.8 else os.path.join(_QR_DIR, "hd"), "report.png")
    return path if os.path.exists(path) else None


class ChatSafety(Screen):
    """MENU, BATC chat: hide or report. The last messages heard, OK on one
    hides (or shows again) everything from its sender on this box; and a
    QR code for BATC's own incident report form, which deals with what is
    said (BATC's Online Safety Act policies; posting is for members only).
    Lynx only ever reads the chat."""

    QR = _qr_pixmap()
    skin = _scale("""
<screen name="LynxChatSafety" position="center,center" size="1600,860" title="BATC chat: hide or report" backgroundColor="#00141414" flags="wfNoBorder">
  <eLabel position="0,0" size="1600,90" backgroundColor="#00d0021b"/>
  <widget zPosition="1" name="title" position="40,0" size="1500,90" font="Regular;40" valign="center" foregroundColor="#00ffffff" backgroundColor="#00d0021b"/>
  <widget zPosition="1" source="list" render="Listbox" position="30,110" size="1080,620" scrollbarMode="showOnDemand" backgroundColor="#00141414" backgroundColorSelected="#00d0021b">
    <convert type="StringList"/>
  </widget>
  <widget zPosition="1" name="report" position="1140,110" size="430,190" font="Regular;26" foregroundColor="#00e0e0e0" backgroundColor="#00141414"/>
""" + ('<widget zPosition="1" name="qr" position="1205,310" size="300,300" alphatest="off" pixmap="%s"/>' % QR if QR else "") + """
  <widget zPosition="1" name="url" position="1140,620" size="430,90" font="Regular;24" halign="center" foregroundColor="#00ffd200" backgroundColor="#00141414"/>
  <widget zPosition="1" name="status" position="30,745" size="1540,44" font="Regular;28" valign="center" foregroundColor="#00ffd200" backgroundColor="#00141414"/>
  <eLabel position="40,800" size="8,44" backgroundColor="#00d0021b"/>
  <widget zPosition="1" source="key_red" render="Label" position="56,800" size="300,44" font="Regular;30" valign="center" transparent="1"/>
  <eLabel position="400,800" size="8,44" backgroundColor="#0000a03c"/>
  <widget zPosition="1" source="key_green" render="Label" position="416,800" size="600,44" font="Regular;30" valign="center" transparent="1"/>
</screen>""")

    def __init__(self, session, overlay):
        Screen.__init__(self, session)
        from .chat import REPORT_TEXT
        self.overlay = overlay
        self.setTitle(_("BATC chat: hide or report"))
        self["title"] = Label(_("BATC chat: hide or report"))
        self["list"] = List([])
        self["report"] = Label(_("To report a message, scan this with a phone, or go to the address "
                                 "below, and choose Streamer chat. BATC deals with what is said; "
                                 "Lynx only reads the chat."))
        if self.QR:
            from Components.Pixmap import Pixmap
            self["qr"] = Pixmap()
        self["url"] = Label(REPORT_TEXT)
        self["status"] = Label()
        self["key_red"] = StaticText(_("Close"))
        self["key_green"] = StaticText(_("OK: hide or show this sender"))
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
            "ok": self.toggle, "green": self.toggle,
            "cancel": self.close, "red": self.close,
        }, -1)
        self.onLayoutFinish.append(self.fill)

    def fill(self):
        from .chat import is_hidden
        # A hidden sender's messages stay hidden here too (Justin, 2 Nov
        # 2026): one line per hidden sender instead, to show them again.
        rows, held = [], {}
        for name, text, hhmm in reversed(self.overlay.messages()):     # newest first
            if is_hidden(name, self.overlay.hidden):
                held[name.lower()] = held.get(name.lower(), 0) + 1
                continue
            short = text if len(text) <= 60 else text[:57] + "..."
            rows.append(("%s  %s: %s" % (hhmm, name, short), name))
        for name in self.overlay.hidden:
            n = held.get(name.lower(), 0)
            heard = (_(" (%d message)") if n == 1 else _(" (%d messages)")) % n if n else ""
            rows.append((_("%s: hidden%s; OK to show again") % (name, heard), name))
        if not rows:
            rows = [(_("No chat messages heard yet while watching."), None)]
        self.rows = rows
        self["list"].setList([r[0] for r in rows])
        if not self["status"].getText():
            self["status"].setText(_("%d sender(s) hidden on this box") % len(self.overlay.hidden))

    def toggle(self):
        i = self["list"].getIndex()
        if i is None or i >= len(self.rows) or not self.rows[i][1]:
            return
        from .chat import is_hidden
        name = self.rows[i][1]
        hidden = [h for h in self.overlay.hidden if h.lower() != name.lower()]
        if is_hidden(name, self.overlay.hidden):
            self["status"].setText(_("%s shown again") % name)
        else:
            hidden.append(name)
            self["status"].setText(_("Messages from %s are now hidden on this box") % name)
        self.overlay.set_hidden(hidden)
        log("chat: hidden senders now %s" % hidden)
        self.fill()
        self["list"].setIndex(min(i, len(self.rows) - 1))


class AddStream(ConfigListScreen, Screen):
    """A BATC stream by its name, kept as a preset: for a member's stream
    that is not on the repeater list (G4FRE, 23 Oct 2026). The name is the
    end of its address, batc.org.uk/live/<name>."""
    skin = _scale("""
<screen name="LynxAddStream" position="center,center" size="1300,520" title="Add a BATC stream" backgroundColor="#00141414" flags="wfNoBorder">
  <eLabel position="0,0" size="1300,90" backgroundColor="#00d0021b"/>
  <widget zPosition="1" name="title" position="40,0" size="1200,90" font="Regular;40" valign="center" foregroundColor="#00ffffff" backgroundColor="#00d0021b"/>
  <widget zPosition="1" name="config" position="30,110" size="1240,110" font="Regular;30" itemHeight="50" scrollbarMode="showOnDemand" backgroundColor="#00141414"/>
  <widget zPosition="1" name="help" position="40,240" size="1220,190" font="Regular;26" foregroundColor="#00c0c0c0" backgroundColor="#00141414"/>
  <eLabel position="40,450" size="8,44" backgroundColor="#00d0021b"/>
  <widget zPosition="1" source="key_red" render="Label" position="56,450" size="300,44" font="Regular;30" valign="center" transparent="1"/>
  <eLabel position="400,450" size="8,44" backgroundColor="#0000a03c"/>
  <widget zPosition="1" source="key_green" render="Label" position="416,450" size="300,44" font="Regular;30" valign="center" transparent="1"/>
</screen>""")

    def __init__(self, session, preset=None):
        Screen.__init__(self, session)
        self.preset = preset
        self.key = ConfigText(default=preset["stream"] if preset else "", fixed_size=False)
        self.label = ConfigText(default=preset["name"] if preset else "", fixed_size=False)
        title = _("Change preset %s") % preset["name"] if preset else _("Add a BATC stream")
        self.setTitle(title)
        self["title"] = Label(title)
        ConfigListScreen.__init__(self, [
            getConfigListEntry(_("Stream name (batc.org.uk/live/...)"), self.key),
            getConfigListEntry(_("Name in the list (optional)"), self.label),
        ], session=session)
        self["help"] = Label(_("The stream name is the end of its address on the BATC streamer: for "
                               "batc.org.uk/live/g4fre it is g4fre. Press TEXT for an on-screen keyboard. "
                               "It goes at the top of the Lynx list, marked LIVE while it is streaming."))
        self["key_red"] = StaticText(_("Cancel"))
        self["key_green"] = StaticText(_("Save"))
        self["lynx_actions"] = ActionMap(["SetupActions", "ColorActions"], {
            "save": self.keep,
            "green": self.keep,
            "cancel": lambda: self.close(None),
            "red": lambda: self.close(None),
        }, -2)

    def keep(self):
        key = self.key.value.strip()
        # People paste or type the whole address: keep only its last part.
        key = key.rstrip("/").split("/")[-1]
        if not repeaters.STREAM_KEY.match(key):
            self.session.open(MessageBox, _("Type the stream's name: the end of its address on the BATC "
                                            "streamer, such as g4fre."), MessageBox.TYPE_ERROR)
            return
        name = self.label.value.strip() or key.upper()
        preset = {"name": name, "stream": key}
        replacing = self.preset["name"] if self.preset else None
        try:
            repeaters.save_presets(repeaters.put_preset(repeaters.load_presets(), preset, replacing))
        except (IOError, OSError) as err:
            self.session.open(MessageBox, _("Could not save the preset: %s") % err, MessageBox.TYPE_ERROR)
            return
        log("stream preset saved: %s" % preset)
        self.close(("saved", name))


class LynxUpdater(object):
    """At start-up, and from MENU: a newer Lynx on GitHub? Then ask (or,
    if set, just install), install it with the README's install line, and
    restart the GUI. Network and install in a worker thread."""

    def __init__(self, session):
        self.session = session
        self.busy = False
        self._result = None
        self.poll, self._pc = _timer(self._poll)
        self.later, self._lc = _timer(self.check)

    def start(self, delay_ms):
        if cfg.update_check.value != "off":
            self.later.start(delay_ms, True)

    def _run(self, job, then):
        import threading
        self.busy, self._result, self._then = True, None, then

        def work():
            try:
                self._result = ("ok", job())
            except Exception as e:
                self._result = ("error", e)
        t = threading.Thread(target=work)
        t.daemon = True
        t.start()
        self.poll.start(500, True)

    def _poll(self):
        if self._result is None:
            self.poll.start(500, True)
            return
        self.busy = False
        kind, value = self._result
        self._then(kind, value)

    def check(self, manual=False):
        if self.busy:
            return
        from . import update
        self.manual = manual

        def job():
            sync.fix_clock()              # no battery clock: HTTPS needs the right date
            return update.latest()
        self._run(job, self._checked)

    def _checked(self, kind, value):
        from . import update
        if kind == "error" or not value:
            log("update check: %s" % (value,))
            if self.manual:
                self._say(_("Could not reach GitHub to check for a newer Lynx."))
            return
        have = update.installed()
        self.latest = value
        if not update.newer(have, value) and not (self.manual and have != value[0]):
            log("update check: up to date (%s)" % (have or "copied from a PC")[:7])
            if self.manual:
                self._say(_("This Lynx is up to date."))
            return
        log("update check: %s available (%s)" % (value[0][:7], value[1]))
        if cfg.update_check.value == "auto" and not self.manual:
            return self._install(True)
        text = _("A newer Lynx is ready (%s):\n%s\n\nInstall it now? The picture stops for about a minute "
                 "while the box restarts its menus.") % (value[1], value[2])
        self.session.openWithCallback(self._install, MessageBox, text, MessageBox.TYPE_YESNO,
                                      timeout=60, default=False)

    def _install(self, yes):
        if not yes:
            return
        rec = getattr(self.session.nav, "RecordTimer", None)
        if rec and rec.isRecording():
            log("update: not now, the box is recording")
            return
        import subprocess
        from . import update
        log("update: installing %s" % self.latest[0][:7])
        self._say(_("Updating Lynx..."), 30)
        self._run(lambda: subprocess.call(["sh", "-c", update.install_command()]), self._installed)

    def _installed(self, kind, value):
        if kind == "error" or value != 0:
            log("update: install failed (%s); see /tmp/lynx-update.log" % (value,))
            self._say(_("The Lynx update did not install; Lynx is as it was. Details in /tmp/lynx-update.log."))
            return
        log("update: installed; restarting the GUI")
        from Screens.Standby import TryQuitMainloop
        self.session.open(TryQuitMainloop, 3)

    def _say(self, text, timeout=8):
        self.session.open(MessageBox, text, MessageBox.TYPE_INFO, timeout=timeout)


_updater = []


def updater(session):
    if not _updater:
        _updater.append(LynxUpdater(session))
    return _updater[0]

# Lynx-Enigma2: the UK ATV Repeaters screens.
#
# Copyright (C) 2026 Justin Cockett, G8YTZ
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version. See LICENSE.
"""Three screens:

  RepeaterList   every repeater the box can show, nearest first; OK watches
  LynxBar        a strip along the bottom while watching: callsign, town,
                 distance, frequency, symbol rate and live SNR
  LynxSettings   locator, LNB supply voltage, per-band LNB oscillators
"""
from __future__ import absolute_import, division, print_function

from .log import log

import re
import time

from enigma import eServiceReference, getDesktop

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
from .tuning import RepeaterTuner, _timer, live, match_playing, signal_text, tech_text, title_text

try:
    _
except NameError:
    def _(s):
        return s

VERSION = "0.1"

# Settings

config.plugins.lynxrepeaters = ConfigSubsection()
cfg = config.plugins.lynxrepeaters
cfg.locator = ConfigText(default="", fixed_size=False)
cfg.supply = ConfigSelection(default="13", choices=[
    ("13", _("13 V (vertical)")), ("18", _("18 V (horizontal)"))])
cfg.osc_9cm = ConfigInteger(default=repeaters.BANDS["9cm"][2], limits=(1, 20000))
cfg.osc_3cm = ConfigInteger(default=repeaters.BANDS["3cm"][2], limits=(1, 20000))
cfg.show_off = ConfigYesNo(default=False)
cfg.autostart = ConfigYesNo(default=False)
cfg.streams = ConfigYesNo(default=True)
cfg.player = ConfigSelection(default="auto", choices=[
    ("auto", _("Automatic (gstplayer, then exteplayer3)")),
    ("exteplayer3", _("exteplayer3 (ServiceApp)")),
    ("gstplayer", _("gstplayer (ServiceApp)")),
    ("builtin", _("The box's own player"))])


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


def lnb_osc():
    return {"23cm": 0, "9cm": cfg.osc_9cm.value, "3cm": cfg.osc_3cm.value}


def home():
    loc = cfg.locator.value.strip().upper()
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
STREAM_DIAG_S = 10

RED = "#00d0021b"
PANEL = "#00141414"
GREY = 0x808080
WHITE = 0xffffff

BUTTONS = """
  <eLabel position="40,{y}" size="8,44" backgroundColor="#00d0021b"/>
  <widget source="key_red" render="Label" position="56,{y}" size="300,44" font="Regular;30" valign="center" transparent="1"/>
  <eLabel position="400,{y}" size="8,44" backgroundColor="#0000a03c"/>
  <widget source="key_green" render="Label" position="416,{y}" size="300,44" font="Regular;30" valign="center" transparent="1"/>
  <eLabel position="760,{y}" size="8,44" backgroundColor="#00e6b800"/>
  <widget source="key_yellow" render="Label" position="776,{y}" size="400,44" font="Regular;30" valign="center" transparent="1"/>
  <eLabel position="1220,{y}" size="8,44" backgroundColor="#000060d0"/>
  <widget source="key_blue" render="Label" position="1236,{y}" size="300,44" font="Regular;30" valign="center" transparent="1"/>
  <eLabel text="MENU  More" position="1550,{y}" size="180,44" font="Regular;30" halign="right" valign="center" foregroundColor="#00c0c0c0" transparent="1"/>
"""


class RepeaterList(Screen):
    skin = _scale("""
<screen name="LynxRepeaterList" position="center,center" size="1760,940" title="UK ATV Repeaters" backgroundColor="#00141414" flags="wfNoBorder">
  <eLabel position="0,0" size="1760,90" backgroundColor="#00d0021b"/>
  <eLabel text="LYNX" position="40,0" size="200,90" font="Regular;54" valign="center" foregroundColor="#00ffffff" backgroundColor="#00d0021b"/>
  <eLabel text="UK ATV Repeaters" position="240,0" size="700,90" font="Regular;40" valign="center" foregroundColor="#00ffffff" backgroundColor="#00d0021b"/>
  <widget name="where" position="940,0" size="790,90" font="Regular;30" halign="right" valign="center" foregroundColor="#00ffffff" backgroundColor="#00d0021b"/>
  <widget source="list" render="Listbox" position="30,110" size="1080,690" scrollbarMode="showOnDemand" backgroundColor="#00141414" backgroundColorSelected="#00d0021b" transparent="0">
    <convert type="TemplatedMultiContent">
      {"template": [
        MultiContentEntryText(pos=(12,0), size=(160,46), font=0, flags=RT_HALIGN_LEFT|RT_VALIGN_CENTER, text=1, color=0xFF000006, color_sel=0xFFFFFF),
        MultiContentEntryText(pos=(180,0), size=(320,46), font=0, flags=RT_HALIGN_LEFT|RT_VALIGN_CENTER, text=2, color=0xFF000006, color_sel=0xFFFFFF),
        MultiContentEntryText(pos=(500,0), size=(130,46), font=0, flags=RT_HALIGN_RIGHT|RT_VALIGN_CENTER, text=3, color=0xFF000006, color_sel=0xFFFFFF),
        MultiContentEntryText(pos=(640,0), size=(160,46), font=0, flags=RT_HALIGN_RIGHT|RT_VALIGN_CENTER, text=4, color=0xFF000006, color_sel=0xFFFFFF),
        MultiContentEntryText(pos=(810,0), size=(150,46), font=0, flags=RT_HALIGN_RIGHT|RT_VALIGN_CENTER, text=5, color=0xFF000006, color_sel=0xFFFFFF),
        MultiContentEntryText(pos=(970,0), size=(90,46), font=1, flags=RT_HALIGN_RIGHT|RT_VALIGN_CENTER, text=7, color=0xFFD200, color_sel=0xFFFFFF)],
       "fonts": [gFont("Regular", 30), gFont("Regular", 24)],
       "itemHeight": 46}
    </convert>
  </widget>
  <eLabel position="1130,110" size="600,690" backgroundColor="#00222222"/>
  <widget name="call" position="1160,125" size="560,70" font="Regular;54" foregroundColor="#00ffffff" backgroundColor="#00222222"/>
  <widget name="live" position="1160,200" size="550,44" font="Regular;30" valign="center" foregroundColor="#00ffd200" backgroundColor="#00222222"/>
  <widget name="details" position="1160,250" size="550,535" font="Regular;28" foregroundColor="#00e0e0e0" backgroundColor="#00222222"/>
  <widget name="status" position="30,815" size="1700,50" font="Regular;30" valign="center" foregroundColor="#00ffd200" backgroundColor="#00141414"/>
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
        self["list"].onSelectionChanged.append(self._selected)
        self["list"].onSelectionChanged.append(self._touched)
        self.data = repeaters.load()
        self.sync = sync.get()
        self.sync.listeners.append(self.refresh)
        self.onClose.append(lambda: self.sync.listeners.remove(self.refresh))
        self.onLayoutFinish.append(self.refresh)
        self.onLayoutFinish.append(self._adopt_playing)
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
            for x in streams.stream_only(self.sync.streams, [e["call"] for e in self.entries]):
                e = dict(x, stream_only=True, km=None, approx=False, status="on")
                rows.append((e, e["call"], e["town"], "", _("Stream only"), "", WHITE, _("LIVE")))
        self["list"].setList(rows)
        loc = cfg.locator.value.strip().upper()
        self["where"].setText(_("From %s") % loc if here else _("Set your locator in Settings (blue)"))
        self._selected()

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
        if e.get("stream_only"):
            self["call"].setText(e["call"])
            self["details"].setText("\n".join([e["town"], "", _("On the BATC streamer only:"),
                                               _("not on the UK repeater list, so"), _("there is nothing to tune on air."),
                                               "", e["stream"]["name"]]))
            self["live"].setText(_("Streaming now on BATC: OK or yellow to watch"))
            self["key_yellow"].setText(_("Watch stream") if not self.tuner.busy else "")
            return
        o = e["output"]
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

    # Watching

    def watch(self, hunt=False):
        e = self._current()
        if not e or self.tuner.busy:
            return
        if e.get("stream_only"):
            return self.watch_stream()
        rec = getattr(self.session.nav, "RecordTimer", None)
        if rec and rec.isRecording():
            self.session.open(MessageBox, _("The box is recording. Stop the recording first."), MessageBox.TYPE_INFO)
            return
        self.stream_timer.stop()
        self.watching = None
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

    def watch_stream(self):
        e = self._current()
        if not e or not e.get("stream") or self.tuner.busy:
            return
        self.stream_entry = e
        self.players = streams.player_chain(cfg.player.value)
        self.player_i = 0
        self._play_stream()

    # gstplayer shows the picture but reports no picture size (20 Oct 2026),
    # so Lynx cannot tell by itself when a player has failed. The stream
    # stays on the first player; yellow on the Lynx bar swaps players. For
    # the first 10 s Lynx logs every sign of video, to find a test it could
    # use to swap by itself.

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
        log("video check %s: %s" % (self.stype, video_signs(self.session)))
        self.diag_left -= 1
        if self.diag_left > 0:
            self.diag_timer.start(1000, True)

    # MENU: every choice in one place

    def menu(self):
        e = self._current()
        choices = []
        if e and e.get("stream_only"):
            choices.append((_("Watch %s on the BATC streamer") % e["call"], self.watch_stream))
        elif e:
            choices.append((_("Watch %s on air") % e["call"], self.watch))
            if e.get("stream"):
                choices.append((_("Watch %s on the BATC streamer") % e["call"], self.watch_stream))
            choices.append((_("Watch %s, trying every symbol rate") % e["call"], self.hunt))
        if cfg.streams.value:
            choices.append((_("Check BATC for live streams now"), self.sync.refresh))
        choices.append((_("Settings"), self.settings))
        choices.append((_("Leave Lynx"), self.leave))
        self.idle_timer.stop()
        self.session.openWithCallback(self._menu_chosen, ChoiceBox, title=_("Lynx"), list=choices)

    def _menu_chosen(self, choice):
        self._child_closed()
        self._touched()
        if choice:
            choice[1]()

    # Settings

    def settings(self):
        if not self.tuner.busy:
            self.idle_timer.stop()
            self.session.openWithCallback(self._settings_closed, LynxSettings)

    def _settings_closed(self, *args):
        self._child_closed()
        self.refresh()
        self._touched()


class LynxBar(Screen):
    skin = _scale("""
<screen name="LynxBar" position="60,930" size="1800,130" backgroundColor="#00141414" flags="wfNoBorder">
  <eLabel position="0,0" size="12,130" backgroundColor="#00d0021b"/>
  <widget name="call" position="40,8" size="560,70" font="Regular;54" foregroundColor="#00ffffff" backgroundColor="#00141414"/>
  <widget name="where" position="620,8" size="520,70" font="Regular;36" valign="center" foregroundColor="#00ffffff" backgroundColor="#00141414"/>
  <widget name="signal" position="1140,8" size="510,70" font="Regular;36" halign="right" valign="center" foregroundColor="#00ffd200" backgroundColor="#00141414"/>
  <widget name="tech" position="40,78" size="1200,44" font="Regular;28" valign="center" foregroundColor="#00c0c0c0" backgroundColor="#00141414"/>
  <widget name="hint" position="1240,78" size="410,44" font="Regular;20" halign="right" valign="center" foregroundColor="#00909090" backgroundColor="#00141414"/>
""" + ('<widget name="eye" position="1670,10" size="110,110" alphatest="blend" pixmaps="%s"/>' % ",".join(EYE_PIXMAPS)
       if EYE_PIXMAPS else "") + """
</screen>""")

    def __init__(self, session, entry, owner=None):
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
            "yellow": lambda: self.owner and self.owner.other_player(),
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

    def _zap(self, by):
        if self.owner:
            if not self.visible:
                self.toggle()
            self.owner.step(by)

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
        if EYE_PIXMAPS:
            self.eye_timer.start(EYE_MS, False)

    def _on_air(self):
        return not (self.entry.get("via_stream") or self.entry.get("pending") or self.notice_text)

    def _margin(self, db):
        return margin_db(db, self.modcod.get("modulation"), self.modcod.get("fec"))

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
        self["eye"].setPixmapNum(EYE_FRAMES if n == "off" else n)

    def update(self):
        # Live values every second: what was actually locked and decoded,
        # never the list's idea of FEC or codec.
        self["hint"].setText(_("CH+/- next  OK hide  EXIT list  YELLOW player")
                             if self.entry.get("other_player") else _("CH+/- next   OK hide   EXIT list"))
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
        text = "%s   LNB %s V" % (tech_text(self.entry["output"]["freq_mhz"], p, self.entry["locked_sr_ks"]),
                                 cfg.supply.value)
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
<screen name="LynxSettings" position="center,center" size="1300,640" title="Lynx settings" backgroundColor="#00141414" flags="wfNoBorder">
  <eLabel position="0,0" size="1300,90" backgroundColor="#00d0021b"/>
  <eLabel text="Lynx settings" position="40,0" size="1200,90" font="Regular;40" valign="center" foregroundColor="#00ffffff" backgroundColor="#00d0021b"/>
  <widget name="config" position="30,110" size="1240,360" font="Regular;30" itemHeight="50" scrollbarMode="showOnDemand" backgroundColor="#00141414"/>
  <widget name="help" position="40,480" size="1220,80" font="Regular;26" foregroundColor="#00c0c0c0" backgroundColor="#00141414"/>
  <eLabel position="40,580" size="8,44" backgroundColor="#00d0021b"/>
  <widget source="key_red" render="Label" position="56,580" size="300,44" font="Regular;30" valign="center" transparent="1"/>
  <eLabel position="400,580" size="8,44" backgroundColor="#0000a03c"/>
  <widget source="key_green" render="Label" position="416,580" size="300,44" font="Regular;30" valign="center" transparent="1"/>
</screen>""")

    def __init__(self, session):
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
            getConfigListEntry(_("Player for streams"), cfg.player),
        ]
        ConfigListScreen.__init__(self, items, session=session)
        self["help"] = Label(_("The LNB supply stays on to power inline preamplifiers. "
                               "Use the number keys to type the locator. Lynx-Enigma2 %s") % VERSION)
        self["key_red"] = StaticText(_("Cancel"))
        self["key_green"] = StaticText(_("Save"))
        self["lynx_actions"] = ActionMap(["SetupActions", "ColorActions"], {
            "save": self.save,
            "green": self.save,
            "cancel": self.cancel,
            "red": self.cancel,
        }, -2)

    def save(self):
        loc = cfg.locator.value.strip().upper()
        if loc and not repeaters.valid_locator(loc):
            self.session.open(MessageBox, _("%s is not a locator. Use four or six characters, such as JO01 or JO01AJ.") % loc,
                              MessageBox.TYPE_ERROR)
            return
        cfg.locator.value = loc
        player_changed = cfg.player.isChanged()
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

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

import re

from enigma import getDesktop

from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.Label import Label
from Components.Sources.List import List
from Components.Sources.StaticText import StaticText
from Components.config import (ConfigInteger, ConfigSelection, ConfigSubsection, ConfigText,
                               ConfigYesNo, config, configfile, getConfigListEntry)
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen

from . import repeaters
from .tuning import RepeaterTuner, _timer, signal_text

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


def lnb_osc():
    return {"23cm": 0, "9cm": cfg.osc_9cm.value, "3cm": cfg.osc_3cm.value}


def home():
    loc = cfg.locator.value.strip().upper()
    return repeaters.locator_to_latlon(loc) if repeaters.valid_locator(loc) else None


# Skins are drawn for 1920 x 1080 and scaled to the box's output.

def _scale(skin):
    f = getDesktop(0).size().width() / 1920.0
    if abs(f - 1) < 0.01:
        return skin
    n = lambda m: str(int(round(int(m.group(0)) * f)))
    num = lambda s: re.sub(r"\d+", n, s)
    skin = re.sub(r'(position|size)="[\d,]+"', lambda m: num(m.group(0)), skin)
    skin = re.sub(r'font="Regular;\d+"', lambda m: num(m.group(0)), skin)
    skin = re.sub(r'(pos|size)=\(\d+,\s*\d+\)', lambda m: num(m.group(0)), skin)
    skin = re.sub(r'gFont\("Regular",\s*\d+\)', lambda m: num(m.group(0)), skin)
    return re.sub(r'"itemHeight":\s*\d+', lambda m: num(m.group(0)), skin)


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
  <widget source="key_blue" render="Label" position="1236,{y}" size="400,44" font="Regular;30" valign="center" transparent="1"/>
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
        MultiContentEntryText(pos=(180,0), size=(360,46), font=0, flags=RT_HALIGN_LEFT|RT_VALIGN_CENTER, text=2, color=0xFF000006, color_sel=0xFFFFFF),
        MultiContentEntryText(pos=(540,0), size=(150,46), font=0, flags=RT_HALIGN_RIGHT|RT_VALIGN_CENTER, text=3, color=0xFF000006, color_sel=0xFFFFFF),
        MultiContentEntryText(pos=(710,0), size=(170,46), font=0, flags=RT_HALIGN_RIGHT|RT_VALIGN_CENTER, text=4, color=0xFF000006, color_sel=0xFFFFFF),
        MultiContentEntryText(pos=(890,0), size=(170,46), font=0, flags=RT_HALIGN_RIGHT|RT_VALIGN_CENTER, text=5, color=0xFF000006, color_sel=0xFFFFFF)],
       "fonts": [gFont("Regular", 30)],
       "itemHeight": 46}
    </convert>
  </widget>
  <eLabel position="1130,110" size="600,690" backgroundColor="#00222222"/>
  <widget name="call" position="1160,125" size="560,70" font="Regular;54" foregroundColor="#00ffffff" backgroundColor="#00222222"/>
  <widget name="details" position="1160,205" size="550,580" font="Regular;28" foregroundColor="#00e0e0e0" backgroundColor="#00222222"/>
  <widget name="status" position="30,815" size="1700,50" font="Regular;30" valign="center" foregroundColor="#00ffd200" backgroundColor="#00141414"/>
""" + BUTTONS.format(y=880) + """
</screen>""")

    def __init__(self, session):
        Screen.__init__(self, session)
        self.setTitle(_("UK ATV Repeaters"))
        self.old_service = self._playing()
        self.watching = None              # the entry now on screen, if any
        self.tuner = RepeaterTuner(session, self._progress, self._tuned)
        self["list"] = List([])
        self["where"] = Label()
        self["call"] = Label()
        self["details"] = Label()
        self["status"] = Label()
        self["key_red"] = StaticText(_("Close"))
        self["key_green"] = StaticText(_("Watch"))
        self["key_yellow"] = StaticText(_("Hunt symbol rate"))
        self["key_blue"] = StaticText(_("Settings"))
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "MenuActions"], {
            "ok": self.watch,
            "green": self.watch,
            "yellow": self.hunt,
            "cancel": self.exit,
            "red": self.exit,
            "blue": self.settings,
            "menu": self.settings,
        }, -1)
        self["list"].onSelectionChanged.append(self._selected)
        self.data = repeaters.load()
        self.onLayoutFinish.append(self.refresh)

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
            rows.append((e, e["call"], e["town"], km, "%g MHz" % o["freq_mhz"], sr, colour))
        self["list"].setList(rows)
        loc = cfg.locator.value.strip().upper()
        self["where"].setText(_("From %s") % loc if here else _("Set your locator in Settings (blue)"))
        self._selected()

    def _current(self):
        cur = self["list"].getCurrent()
        return cur[0] if cur else None

    def _selected(self):
        e = self._current()
        if not e:
            self["call"].setText("")
            self["details"].setText(_("No repeaters to show."))
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

    # Watching

    def watch(self, hunt=False):
        e = self._current()
        if not e or self.tuner.busy:
            return
        rec = getattr(self.session.nav, "RecordTimer", None)
        if rec and rec.isRecording():
            self.session.open(MessageBox, _("The box is recording. Stop the recording first."), MessageBox.TYPE_INFO)
            return
        self.watching = None
        self.tuning = e
        self["key_red"].setText(_("Stop"))
        self.tuner.tune(e, cfg.supply.value, hunt)

    def hunt(self):
        self.watch(hunt=True)

    def _progress(self, text):
        self["status"].setText(text)

    def _tuned(self, ref, sr_ks, error):
        self["key_red"].setText(_("Close"))
        e = self.tuning
        if not ref:
            self["status"].setText(_("%s: %s") % (e["call"], error))
            return
        self.watching = dict(e, locked_sr_ks=sr_ks)
        self["status"].setText(_("Watching %s at %d kS/s") % (e["call"], sr_ks))
        self.session.openWithCallback(self._bar_closed, LynxBar, self.watching)

    def _bar_closed(self, leave=False):
        if leave:
            self.close()

    def exit(self):
        if self.tuner.busy:
            self.tuner.cancel()
            self["status"].setText(_("Stopped"))
            self["key_red"].setText(_("Close"))
            return
        if not self.watching and self.old_service and self._playing() is None:
            self.session.nav.playService(self.old_service)   # put back what was on
        self.close()

    # Settings

    def settings(self):
        if not self.tuner.busy:
            self.session.openWithCallback(lambda *a: self.refresh(), LynxSettings)


class LynxBar(Screen):
    skin = _scale("""
<screen name="LynxBar" position="0,920" size="1920,160" backgroundColor="#ff000000" flags="wfNoBorder">
  <eLabel position="60,10" size="1800,130" backgroundColor="#30141414"/>
  <eLabel position="60,10" size="12,130" backgroundColor="#00d0021b"/>
  <widget name="call" position="100,18" size="300,70" font="Regular;54" foregroundColor="#00ffffff" backgroundColor="#30141414" transparent="1"/>
  <widget name="where" position="400,18" size="900,70" font="Regular;36" valign="center" foregroundColor="#00ffffff" backgroundColor="#30141414" transparent="1"/>
  <widget name="signal" position="1300,18" size="530,70" font="Regular;40" halign="right" valign="center" foregroundColor="#00ffd200" backgroundColor="#30141414" transparent="1"/>
  <widget name="tech" position="100,88" size="1300,44" font="Regular;28" valign="center" foregroundColor="#00c0c0c0" backgroundColor="#30141414" transparent="1"/>
  <eLabel text="OK hide   EXIT list   RED leave Lynx" position="1300,88" size="530,44" font="Regular;24" halign="right" valign="center" foregroundColor="#00909090" backgroundColor="#30141414" transparent="1"/>
</screen>""")

    def __init__(self, session, entry):
        Screen.__init__(self, session)
        self.entry = entry
        o = entry["output"]
        self["call"] = Label(entry["call"])
        km = "" if entry["km"] is None else "   %s%d km" % ("~" if entry["approx"] else "", round(entry["km"]))
        self["where"] = Label(entry["town"] + km)
        self["tech"] = Label("%g MHz   %d kS/s%s%s" % (
            o["freq_mhz"], entry["locked_sr_ks"],
            ("   FEC " + o["fec"]) if o.get("fec") else "",
            ("   " + o["codec"]) if o.get("codec") else ""))
        self["signal"] = Label()
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
            "ok": self.toggle,
            "cancel": lambda: self.close(False),
            "red": lambda: self.close(True),
        }, -1)
        self.visible = True
        self.timer, self._tc = _timer(self.update)
        self.onShown.append(self._start)
        self.onClose.append(self.timer.stop)

    def _start(self):
        self.update()
        self.timer.start(1000, False)

    def update(self):
        self["signal"].setText(signal_text(self.session))

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
        for item in self["config"].list:
            item[1].save()
        configfile.save()
        self.close(True)

    def cancel(self):
        for item in self["config"].list:
            item[1].cancel()
        self.close(False)

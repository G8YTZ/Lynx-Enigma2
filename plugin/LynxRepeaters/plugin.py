# Lynx-Enigma2: watch UK amateur TV repeaters on an Enigma2 box.
#
# Copyright (C) 2026 Justin Cockett, G8YTZ
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version. See LICENSE.
from __future__ import absolute_import

from Plugins.Plugin import PluginDescriptor

try:
    _
except NameError:
    def _(s):
        return s


def main(session, **kwargs):
    from .screens import RepeaterList     # loaded on first use, not at boot
    session.open(RepeaterList)


# Opening at start-up: wait until the normal TV screen (InfoBar) is up and
# nothing else, such as the first-boot wizard, is on top of it.
_boot = {}
BOOT_TRIES = 30            # one a second


def _open_at_boot():
    from Screens.InfoBar import InfoBar
    from .screens import RepeaterList
    session = _boot["session"]
    bar = InfoBar.instance
    if bar is not None and session.current_dialog is bar:
        session.open(RepeaterList)
        return
    _boot["tries"] -= 1
    if _boot["tries"] > 0:
        _boot["timer"].start(1000, True)


def sessionstart(reason, session=None, **kwargs):
    if reason != 0 or session is None:
        return
    from . import screens
    if screens.cfg.supply.value == "off":
        from . import lnbpower
        lnbpower.apply(True)        # the box's own tuner set-up is already loaded
    screens.updater(session).start(120 * 1000)   # a newer Lynx? Once the clock and network are up
    if screens.cfg.streams.value:
        from . import sync
        s = sync.get()
        s.rewrite_bouquet()         # with the player in use now (ServiceApp may be new)
        s.start(15 * 1000)          # first BATC check (and clock) soon after boot
    if not screens.cfg.autostart.value:
        return
    from .tuning import _timer
    timer, conn = _timer(_open_at_boot)
    _boot.update(session=session, timer=timer, conn=conn, tries=BOOT_TRIES)
    timer.start(3000, True)


def Plugins(**kwargs):
    return [
        PluginDescriptor(where=PluginDescriptor.WHERE_SESSIONSTART, fnc=sessionstart),
        PluginDescriptor(
            name=_("UK ATV Repeaters"),
            description=_("Lynx: watch UK amateur TV repeaters"),
            where=[PluginDescriptor.WHERE_PLUGINMENU, PluginDescriptor.WHERE_EXTENSIONSMENU],
            fnc=main),
    ]

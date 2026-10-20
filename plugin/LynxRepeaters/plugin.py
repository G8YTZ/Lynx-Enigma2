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

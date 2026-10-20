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


def Plugins(**kwargs):
    return [PluginDescriptor(
        name=_("UK ATV Repeaters"),
        description=_("Lynx: watch UK amateur TV repeaters"),
        where=[PluginDescriptor.WHERE_PLUGINMENU, PluginDescriptor.WHERE_EXTENSIONSMENU],
        fnc=main)]

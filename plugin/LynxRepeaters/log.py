# Lynx-Enigma2: Lynx's own log.
#
# Copyright (C) 2026 Justin Cockett, G8YTZ
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version. See LICENSE.
"""Lynx writes its own log to /tmp/lynx.log (memory, so it goes at a
restart), as well as Enigma2's: where Enigma2 sends Python's messages
differs between images, and reading one file over SSH is easier for anyone
helping with a box.

  ssh root@<box> cat /tmp/lynx.log
"""
from __future__ import absolute_import, division, print_function

import io
import time

PATH = "/tmp/lynx.log"
MAX_BYTES = 256 * 1024          # then start again, keeping the second half


def log(msg):
    line = "%s %s" % (time.strftime("%H:%M:%S"), msg)
    print("[LynxRepeaters] " + msg)
    try:
        try:
            with io.open(PATH, "rb") as f:
                old = f.read()
        except (IOError, OSError):
            old = b""
        if len(old) > MAX_BYTES:
            old = old[len(old) // 2:]
            old = old[old.find(b"\n") + 1:]
            with io.open(PATH, "wb") as f:
                f.write(old)
        with io.open(PATH, "ab") as f:
            f.write((line + "\n").encode("utf-8") if not isinstance(line, bytes) else line + b"\n")
    except (IOError, OSError):
        pass                    # a log must never stop Lynx

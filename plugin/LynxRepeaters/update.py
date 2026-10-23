# Lynx-Enigma2: is there a newer Lynx?
#
# Copyright (C) 2026 Justin Cockett, G8YTZ
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version. See LICENSE.
"""At each start (Justin, 23 Oct 2026) Lynx asks GitHub which commit the
main branch is at and compares it with the one tools/install.sh put on the
box (version.txt beside the plugin). Installing is the same install.sh the
README gives, run on the box. Only GitHub's own answer is used, over
checked HTTPS; if the box cannot check certificates, Lynx does not look.
No Enigma2 imports here.
"""
from __future__ import absolute_import, division, print_function

import io
import json
import os
import re

try:
    from urllib.request import Request, urlopen      # Python 3
except ImportError:                                   # Python 2
    from urllib2 import Request, urlopen

from .repeaters import _native

REPO = "G8YTZ/Lynx-Enigma2"
API = "https://api.github.com/repos/%s/commits/main" % REPO
INSTALL = "https://raw.githubusercontent.com/%s/main/tools/install.sh" % REPO
HERE = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(HERE, "version.txt")
LOG = "/tmp/lynx-update.log"
_SHA = re.compile(r"^[0-9a-f]{40}$")


def installed(path=VERSION_FILE):
    """The commit installed, or None (copied from a PC with deploy.sh, or
    an install from before 23 Oct 2026)."""
    try:
        with io.open(path, encoding="utf-8") as f:
            sha = f.read().split()[0].strip().lower()
    except (IOError, OSError, IndexError):
        return None
    return sha if _SHA.match(sha) else None


def parse(data):
    """(sha, date, first line of the message) from GitHub's answer."""
    sha = str(data.get("sha", "")).lower()
    if not _SHA.match(sha):
        return None
    commit = data.get("commit") or {}
    date = ((commit.get("committer") or {}).get("date") or "")[:10]
    message = (commit.get("message") or "").strip().split("\n")[0][:80]
    return sha, date, message


def latest(timeout=15):
    req = Request(API, headers={"User-Agent": "Lynx-Enigma2", "Accept": "application/vnd.github+json"})
    body = urlopen(req, timeout=timeout).read()
    return parse(_native(json.loads(body.decode("utf-8"))))


def newer(have, got):
    """Whether GitHub's latest is worth offering: a known install that
    differs. An unknown install (deploy.sh from a PC) is left alone."""
    return bool(have and got and got[0] != have)


def install_command():
    """install.sh without its own GUI restart: Lynx restarts the GUI the
    proper way once the files are in place (a shell started from Enigma2
    could be stopped with it, half way through)."""
    return "wget -qO- %s | LYNX_NO_RESTART=1 sh > %s 2>&1" % (INSTALL, LOG)

#!/bin/sh
# Lynx-Enigma2: install or update Lynx, run on the box itself.
#
#   opkg update && opkg upgrade
#   wget -qO- https://raw.githubusercontent.com/G8YTZ/Lynx-Enigma2/main/tools/install.sh | sh
#
# (the first line brings the box's own software up to date first)
#
# Installs the stream players (ServiceApp, gstplayer, exteplayer3) from the
# box's feed, downloads the latest Lynx from GitHub, puts the plugin and the
# repeater list in place, and restarts the GUI. Settings are kept: they live in the
# box's own settings file. Run it again at any time to update.
#
# Copyright (C) 2026 Justin Cockett, G8YTZ. GPL-2.0-or-later; see LICENSE.
set -e

URL=${LYNX_TARBALL:-https://github.com/G8YTZ/Lynx-Enigma2/archive/refs/heads/main.tar.gz}
DEST=${LYNX_DEST:-/usr/lib/enigma2/python/Plugins/Extensions/LynxRepeaters}
WORK=/tmp/lynx-install.$$

# The stream players Lynx uses for BATC streams, from the box's own feed.
# Already there: opkg leaves them alone. Not available: Lynx still works,
# with the box's own player for streams.
if [ -z "$LYNX_NO_PLAYERS" ] && command -v opkg >/dev/null 2>&1; then
    echo "Lynx: making sure the stream players are installed"
    opkg update >/dev/null 2>&1 || true
    opkg install enigma2-plugin-systemplugins-serviceapp gstplayer exteplayer3 >/dev/null 2>&1 \
        || echo "Lynx: could not install the stream players; streams will use the box's own player"
fi

echo "Lynx: downloading"
rm -rf "$WORK"
mkdir -p "$WORK"
trap 'rm -rf "$WORK"' EXIT
case "$URL" in
    http*) wget -q -O "$WORK/lynx.tar.gz" "$URL" ;;
    *) cp "$URL" "$WORK/lynx.tar.gz" ;;            # a local file, for testing
esac
tar -xzf "$WORK/lynx.tar.gz" -C "$WORK"
SRC=$(ls -d "$WORK"/*/plugin/LynxRepeaters 2>/dev/null | head -1)
if [ -z "$SRC" ] || [ ! -f "$SRC/plugin.py" ]; then
    echo "Lynx: the download did not contain the plugin; nothing changed." >&2
    exit 1
fi
TOP=${SRC%/plugin/LynxRepeaters}

echo "Lynx: installing to $DEST"
mkdir -p "$DEST"
rm -rf "$DEST/__pycache__"
rm -f "$DEST"/*.pyc "$DEST"/*.pyo
cp "$SRC"/*.py "$DEST/"
cp "$TOP/data/repeaters.json" "$DEST/"

if [ -n "$LYNX_NO_RESTART" ]; then
    echo "Lynx: installed (GUI not restarted)"
    exit 0
fi
echo "Lynx: installed; restarting the GUI"
/sbin/init 4
sleep 2
killall -9 enigma2 2>/dev/null || true
sleep 1
/sbin/init 3

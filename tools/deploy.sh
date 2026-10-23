#!/bin/sh
# Copy the plugin and the repeater list to an Enigma2 box and restart its GUI.
# It removes version.txt, so the box does not offer to "update" over your copy.
#   tools/deploy.sh [box address] [--no-restart]
# Needs root SSH to the box (OpenATV: no password by default).
set -e
BOX=192.168.0.163
RESTART=1
for a in "$@"; do
    case "$a" in
        --no-restart) RESTART= ;;
        *) BOX="$a" ;;
    esac
done
HERE=$(cd "$(dirname "$0")/.." && pwd)
DEST=/usr/lib/enigma2/python/Plugins/Extensions/LynxRepeaters
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
cp "$HERE"/plugin/LynxRepeaters/*.py "$HERE/data/repeaters.json" "$STAGE/"
cp -R "$HERE/plugin/LynxRepeaters/eye" "$STAGE/"
# COPYFILE_DISABLE stops macOS tar adding ._ files; tar over ssh avoids
# needing SFTP on the box; -m stops tar fussing when the box's clock is wrong.
COPYFILE_DISABLE=1 tar -C "$STAGE" -cf - . | \
    ssh root@"$BOX" "mkdir -p $DEST && rm -rf $DEST/__pycache__ $DEST/version.txt && tar -m -C $DEST -xf -"
echo "Copied to $BOX:$DEST"
if [ -n "$RESTART" ]; then
    # /sbin is not on the box's PATH over SSH, hence the full paths.
    # Stop the GUI, clear any copies left by tools/foreground.sh, start it
    # again. Two copies at once fight over screen and tuner and hang the box.
    ssh root@"$BOX" "/sbin/init 4; sleep 2; killall -9 enigma2 2>/dev/null; sleep 1; /sbin/init 3"
    echo "GUI restarting; the plugin is under Plugins as UK ATV Repeaters."
fi

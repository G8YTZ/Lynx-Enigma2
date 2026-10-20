#!/bin/sh
# Copy the plugin and the repeater list to an Enigma2 box and restart its GUI.
#   tools/deploy.sh [box address] [--no-restart]
# Needs root SSH to the box (OpenATV: no password by default).
set -e
BOX=192.168.0.164
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
# COPYFILE_DISABLE stops macOS tar adding ._ files; tar over ssh avoids
# needing SFTP on the box.
COPYFILE_DISABLE=1 tar -C "$STAGE" -cf - . | \
    ssh root@"$BOX" "mkdir -p $DEST && rm -rf $DEST/__pycache__ && tar -C $DEST -xf -"
echo "Copied to $BOX:$DEST"
if [ -n "$RESTART" ]; then
    ssh root@"$BOX" "init 4; sleep 3; init 3"
    echo "GUI restarting; the plugin is under Plugins as UK ATV Repeaters."
fi

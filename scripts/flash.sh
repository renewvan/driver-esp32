#!/usr/bin/env bash
# Build and flash the relay node, stamping the firmware version from this checkout.
#
# The version is `git describe --tags --always --dirty`, and it is ALWAYS passed to the
# build. An untagged tree flashes with a hash version and an uncommitted tree gets a
# `-dirty` suffix; this script never refuses. The static Node fields come from
# manifest.json (scripts/manifest_substitutions.py), so they cannot drift from CI.
#
# usage: scripts/flash.sh [esphome run args...]   e.g. scripts/flash.sh --device /dev/ttyUSB0
#        scripts/flash.sh --print-version         print the stamp and exit
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

version="$(git describe --tags --always --dirty)"

if [[ "${1:-}" == "--print-version" ]]; then
  echo "$version"
  exit 0
fi

args=(-s version "$version")
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  args+=(-s "${line%%=*}" "${line#*=}")
done < <(python3 scripts/manifest_substitutions.py manifest.json)

echo "Flashing relay-node.yaml as version: $version" >&2
exec esphome "${args[@]}" run relay-node.yaml "$@"

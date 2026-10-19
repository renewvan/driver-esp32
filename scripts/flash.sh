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

# Read into a variable first: a process substitution would hide a manifest error from
# `set -e`, and the flash would go ahead with the placeholders unexpanded.
manifest_args=()
while IFS= read -r -d '' arg; do
  manifest_args+=("$arg")
done < <(python3 scripts/manifest_substitutions.py manifest.json --esphome-args || echo FAILED >&2)

if [[ ${#manifest_args[@]} -eq 0 ]]; then
  echo "scripts/flash.sh: manifest.json produced no substitutions; refusing to flash" >&2
  exit 1
fi

echo "Flashing relay-node.yaml as version: $version" >&2
exec esphome -s version "$version" "${manifest_args[@]}" run relay-node.yaml "$@"

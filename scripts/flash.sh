#!/usr/bin/env bash
# Build and flash one ESP32 firmware variant, stamping the version from this checkout.
#
# The version is `git describe --tags --always --dirty`, and it is ALWAYS passed to the
# build. An untagged tree flashes with a hash version and an uncommitted tree gets a
# `-dirty` suffix; this script never refuses. The static Driver fields come from the
# variant's manifest (scripts/manifest_substitutions.py), so they cannot drift from CI.
#
# usage: scripts/flash.sh <variant> [esphome run args...]
#          e.g. scripts/flash.sh esp32-16x-relay --device /dev/ttyUSB0
#        scripts/flash.sh --print-version         print the stamp and exit
#        scripts/flash.sh --list                  print the variants and exit
# A variant is a name under manifests/ (and firmware/): see README.md.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

version="$(git describe --tags --always --dirty)"

case "${1:-}" in
  --print-version)
    echo "$version"
    exit 0
    ;;
  --list)
    python3 scripts/variants.py list
    exit 0
    ;;
  "" | -*)
    echo "usage: scripts/flash.sh <variant> [esphome run args...]" >&2
    echo "variants: $(python3 scripts/variants.py list)" >&2
    exit 2
    ;;
esac

variant="$1"
shift

if [[ ! -f "firmware/${variant}.yaml" || ! -f "manifests/${variant}.json" ]]; then
  echo "scripts/flash.sh: unknown variant '${variant}'; variants: $(python3 scripts/variants.py list)" >&2
  exit 2
fi

# Read into a variable first: a process substitution would hide a manifest error from
# `set -e`, and the flash would go ahead with the placeholders unexpanded.
manifest_args=()
while IFS= read -r -d '' arg; do
  manifest_args+=("$arg")
done < <(python3 scripts/manifest_substitutions.py "$variant" --esphome-args || echo FAILED >&2)

if [[ ${#manifest_args[@]} -eq 0 ]]; then
  echo "scripts/flash.sh: manifests/${variant}.json produced no substitutions; refusing to flash" >&2
  exit 1
fi

echo "Flashing firmware/${variant}.yaml as version: $version" >&2
exec esphome -s version "$version" "${manifest_args[@]}" run "firmware/${variant}.yaml" "$@"

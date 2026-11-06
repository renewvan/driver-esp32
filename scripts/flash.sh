#!/usr/bin/env bash
# Build and flash one ESP32 firmware variant, stamping the version from this checkout.
#
# The version is `git describe --tags --always --dirty`, and it is ALWAYS passed to the
# build. An untagged tree flashes with a hash version and an uncommitted tree gets a
# `-dirty` suffix; this script never refuses. The static Driver fields come from the
# variant's manifest (scripts/manifest_substitutions.py), so they cannot drift from CI.
#
# `--board <name>` is required: it names the physical board and is compiled into the firmware.
# The board appears on the bus as its own Driver `esp32-<name>` (relay ids `<name>-<nn>`), so
# reflashing with the same name keeps the Driver and a new name is a new Driver. The name is
# validated before anything is built: a slug (lowercase letters and numerals, hyphen-separated),
# at most 16 characters, and not ending in a hyphen plus numerals (scripts/variants.py).
#
# Secrets are per board: the shared secrets.yaml (WiFi, broker address) with secrets/<name>.yaml laid
# over it (the board's broker account, OTA password, API key, optional `ota_address`), merged by
# scripts/board_secrets.py into the gitignored staging tree .build/<name>/ (a copy of the variant's yaml
# next to its own secrets.yaml, since ESPHome reads secrets next to the entrypoint). A board with no
# secrets/<name>.yaml is refused. With no `--device`, an `ota_address` in the board's secrets is the
# OTA target; without one esphome finds the board by its own hostname renewvan-esp32-<name>.
#
# usage: scripts/flash.sh <variant> --board <name> [esphome run args...]
#          e.g. scripts/flash.sh esp32-16x-relay --board front --device /dev/ttyUSB0
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
    echo "usage: scripts/flash.sh <variant> --board <name> [esphome run args...]" >&2
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

# Pull `--board <name>` out of the arguments; everything else goes to `esphome run`.
board=""
run_args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --board)
      if [[ $# -lt 2 ]]; then
        echo "scripts/flash.sh: --board needs a name" >&2
        exit 2
      fi
      board="$2"
      shift 2
      ;;
    --board=*)
      board="${1#--board=}"
      shift
      ;;
    *)
      run_args+=("$1")
      shift
      ;;
  esac
done

if [[ -z "$board" ]]; then
  echo "scripts/flash.sh: --board <name> is required (it names this board and is compiled in), e.g. --board front" >&2
  exit 2
fi
# Reject a bad name before building anything.
python3 scripts/variants.py board "$board" || exit 2

# Stage this board's build: ESPHome reads secrets next to the entrypoint, so the variant's yaml is
# copied beside the board's merged secrets, with packages/ linked in for its relative !includes.
stage=".build/${board}"
rm -rf "$stage"
mkdir -p "$stage/firmware"
python3 scripts/board_secrets.py "$board" --write "$stage/firmware/secrets.yaml" || exit 2
cp "firmware/${variant}.yaml" "$stage/firmware/${variant}.yaml"
ln -s ../../packages "$stage/packages"
has_device=0
for arg in ${run_args[@]+"${run_args[@]}"}; do
  [[ "$arg" == --device || "$arg" == --device=* ]] && has_device=1
done
if [[ $has_device -eq 0 ]]; then
  ota_address="$(python3 scripts/board_secrets.py "$board" --get ota_address)"
  if [[ -n "$ota_address" ]]; then
    run_args+=(--device "$ota_address")
  fi
fi

# Read into a variable first: a process substitution would hide a manifest error from
# `set -e`, and the flash would go ahead with the placeholders unexpanded.
manifest_args=()
while IFS= read -r -d '' arg; do
  manifest_args+=("$arg")
done < <(python3 scripts/manifest_substitutions.py "$variant" --board "$board" --esphome-args || echo FAILED >&2)

if [[ ${#manifest_args[@]} -eq 0 ]]; then
  echo "scripts/flash.sh: manifests/${variant}.json produced no substitutions; refusing to flash" >&2
  exit 1
fi

echo "Flashing firmware/${variant}.yaml as board '${board}' (Driver esp32-${board}), version: $version" >&2
# `-s` is a global esphome option, so it goes before `run` (the run subcommand has no -s).
exec esphome -s version "$version" "${manifest_args[@]}" run "${stage}/firmware/${variant}.yaml" ${run_args[@]+"${run_args[@]}"}

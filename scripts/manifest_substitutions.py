#!/usr/bin/env python3
"""Flatten a variant's manifest into `key=value` lines for ESPHome substitutions.

Used by scripts/flash.sh (esphome -s) and CI (build-action `substitutions:`), so the
static Driver fields have exactly one source: manifests/<variant>.json. Optional fields that
are empty are omitted, never emitted blank.

Values are escaped for a C++ string literal (`\\` and `"`): ESPHome pastes substitutions
textually, and the firmware places them between double quotes inside a lambda.

usage: manifest_substitutions.py VARIANT|MANIFEST_PATH [--esphome-args]
       manifest_substitutions.py esp32-16x-relay
       manifest_substitutions.py manifests/esp32-16x-relay.json
"""

import argparse
import json
import sys

import variants

REQUIRED = ("driver", "product", "source", "publishes")
OPTIONAL = ("manufacturer", "homepage")
# Stamped from the checkout / read from the board, never hand-written.
FORBIDDEN = ("version", "board_serial")


def flatten(manifest):
    errors = [f"manifest must not contain '{key}'" for key in FORBIDDEN if key in manifest]
    errors += [f"manifest is missing '{key}'" for key in REQUIRED if not manifest.get(key)]
    if errors:
        raise ValueError("; ".join(errors))

    out = {key: manifest[key] for key in REQUIRED}
    out["publishes"] = json.dumps(manifest["publishes"], separators=(",", ":"))
    out.update({key: manifest[key] for key in OPTIONAL if manifest.get(key)})
    return {key: cpp_escape(value) for key, value in out.items()}


def cpp_escape(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", help="a variant name, or the path of its manifest")
    parser.add_argument(
        "--esphome-args",
        action="store_true",
        help="emit NUL-separated `-s KEY VALUE` triples for `esphome` instead of key=value lines",
    )
    args = parser.parse_args()

    path, variant = variants.resolve_manifest(args.manifest)
    try:
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
    except OSError as err:
        print(f"{args.manifest}: {err}", file=sys.stderr)
        return 1

    try:
        values = flatten(manifest)
        # Asked for by name, the manifest must carry this repo's one Driver key: a manifest
        # copied from another repo would publish under that Driver's topics.
        if variant is not None and manifest["driver"] != variants.DRIVER_KEY:
            raise ValueError(f"driver is '{manifest['driver']}', expected '{variants.DRIVER_KEY}'")
    except ValueError as err:
        print(f"{path}: {err}", file=sys.stderr)
        return 1

    if args.esphome_args:
        for key, value in values.items():
            sys.stdout.write(f"-s\0{key}\0{value}\0")
    else:
        for key, value in values.items():
            print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

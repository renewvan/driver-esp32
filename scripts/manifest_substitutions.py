#!/usr/bin/env python3
"""Flatten a variant's manifest into `key=value` lines for ESPHome substitutions.

Used by scripts/flash.sh (esphome -s) and CI (build-action `substitutions:`), so the
static Driver fields have exactly one source: manifests/<variant>.json. Optional fields that
are empty are omitted, never emitted blank.

Values are escaped for a C++ string literal (`\\` and `"`): ESPHome pastes substitutions
textually, and the firmware places them between double quotes inside a lambda.

--board NAME is required: it adds `board` and `driver` (= esp32-NAME, variants.driver_key), the
board's identity, composed here and nowhere else. The manifest itself may not carry a `driver`.
Without --board the script fails (exit 2, nothing on stdout) rather than build placeholders.

--hub-power CH (optional) adds `hub_power`: the channel key (`relay_<nn>`) of the board's Hub power
(packages/hub-power.yaml), from `hub_power` in secrets/<board>.yaml. It must be one of the variant's
channels, so it needs a variant name, not a manifest path. Absent or empty: no Hub power.

--ble-channels CH,CH (optional) adds `ble_channels`: the channel keys the phone may switch over
Bluetooth while the hub is unreachable (Direct control, packages/ble-wake.yaml), from `ble_channels`
in secrets/<board>.yaml. Each must be one of the variant's channels, listed once, and never the Hub
power (whose one Bluetooth action is Hub wake). Absent or empty: none.

usage: manifest_substitutions.py VARIANT|MANIFEST_PATH --board NAME [--hub-power CH]
                                 [--ble-channels CH,CH] [--esphome-args]
       manifest_substitutions.py esp32-16x-relay --board front
       manifest_substitutions.py manifests/esp32-16x-relay.json
"""

import argparse
import json
import sys

import check_relay_channels
import variants

REQUIRED = ("product", "source", "publishes")
OPTIONAL = ("manufacturer", "homepage")
# Stamped from the checkout / read from the board / composed from --board, never hand-written.
FORBIDDEN = ("version", "board_serial", "driver")


def flatten(manifest):
    errors = [f"manifest must not contain '{key}'" for key in FORBIDDEN if key in manifest]
    errors += [f"manifest is missing '{key}'" for key in REQUIRED if not manifest.get(key)]
    if errors:
        raise ValueError("; ".join(errors))

    out = {key: manifest[key] for key in REQUIRED}
    out["publishes"] = json.dumps(manifest["publishes"], separators=(",", ":"))
    out.update({key: manifest[key] for key in OPTIONAL if manifest.get(key)})
    return {key: cpp_escape(value) for key, value in out.items()}


def variant_channels(variant):
    """The variant's channel keys, read from its firmware yaml."""
    text = variants.firmware_path(variant).read_text(encoding="utf-8")
    return [ch for ch, _ in check_relay_channels.PACKAGE.findall(text)]


def hub_power_problem(channel, variant):
    """Why `channel` cannot be this variant's Hub power, or None when it can."""
    if variant is None:
        return "--hub-power needs a variant name, not a manifest path"
    try:
        channels = variant_channels(variant)
    except OSError as err:
        return f"--hub-power: {err}"
    if channel not in channels:
        return f"--hub-power '{channel}' is not a channel of {variant} ({', '.join(channels)})"
    return None


def ble_channels_problem(listed, variant, hub_power):
    """Why these channel keys cannot be the board's Direct control channels, or None."""
    if variant is None:
        return "--ble-channels needs a variant name, not a manifest path"
    try:
        channels = variant_channels(variant)
    except OSError as err:
        return f"--ble-channels: {err}"
    for channel in listed:
        if channel not in channels:
            return f"--ble-channels '{channel}' is not a channel of {variant} ({', '.join(channels)})"
        if channel == hub_power:
            return f"--ble-channels '{channel}' is the Hub power: its one Bluetooth action is Hub wake"
        if listed.count(channel) > 1:
            return f"--ble-channels lists '{channel}' twice"
    return None


def cpp_escape(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", help="a variant name, or the path of its manifest")
    parser.add_argument(
        "--board", required=True, help="the board's name (required): adds `board` and `driver` (esp32-<name>)"
    )
    parser.add_argument(
        "--hub-power",
        default="",
        metavar="CH",
        help="the channel key (relay_<nn>) that powers the hub; empty or absent: none",
    )
    parser.add_argument(
        "--ble-channels",
        default="",
        metavar="CH,CH",
        help="the channel keys (relay_<nn>) open to Direct control over Bluetooth; empty: none",
    )
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
    except ValueError as err:
        print(f"{path}: {err}", file=sys.stderr)
        return 1

    problems = variants.validate_board(args.board)
    if problems:
        print("; ".join(problems), file=sys.stderr)
        return 1
    values["board"] = args.board
    values["driver"] = variants.driver_key(args.board)
    if args.hub_power:
        problem = hub_power_problem(args.hub_power, variant)
        if problem:
            print(problem, file=sys.stderr)
            return 1
        values["hub_power"] = args.hub_power
    listed = [ch.strip() for ch in args.ble_channels.split(",") if ch.strip()]
    if listed:
        problem = ble_channels_problem(listed, variant, args.hub_power)
        if problem:
            print(problem, file=sys.stderr)
            return 1
        values["ble_channels"] = ",".join(listed)

    if args.esphome_args:
        for key, value in values.items():
            sys.stdout.write(f"-s\0{key}\0{value}\0")
    else:
        for key, value in values.items():
            print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

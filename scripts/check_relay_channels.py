#!/usr/bin/env python3
"""CI guard for the relay variant: the channels under `packages:` must equal the channels in
its `publish_retained_state` script.

The retained states are published from ONE script, step (1) of the single connect
chain in packages/base.yaml (the order of separate on_connect entries is undefined), which
lists every channel by hand. A channel present under `packages:` but missing from that script
would never publish its state, and `esphome config` would not notice.

Relay-specific on purpose: other variants have no channel list. Run it only for a variant that
includes packages/relay-channel.yaml.

usage: check_relay_channels.py VARIANT|FIRMWARE_PATH   e.g. check_relay_channels.py esp32-16x-relay
"""

import re
import sys

import variants

# `relay_03: !include { file: ../packages/relay-channel.yaml, vars: { ch: relay_03, nn: "03", bit: 2 } }`
# `ch` is the channel key inside the firmware, `nn` the number in its bus id `<board>-<nn>`.
PACKAGE = re.compile(r'vars:\s*\{\s*ch:\s*([A-Za-z0-9_]+)\s*,\s*nn:\s*"([0-9]+)"')
# `{"${board}-03", id(relay_relay_03), &id(name_relay_03)},`
CHAIN = re.compile(r'\{\s*"\$\{board\}-([0-9]+)"\s*,\s*id\(relay_([A-Za-z0-9_]+)\)')


def check(text):
    packages = {ch: nn for ch, nn in PACKAGE.findall(text)}
    chain = {ch: nn for nn, ch in CHAIN.findall(text)}
    problems = [f"channel {c} is in `packages:` but not in `publish_retained_state`" for c in sorted(set(packages) - set(chain))]
    problems += [f"channel {c} is in `publish_retained_state` but not in `packages:`" for c in sorted(set(chain) - set(packages))]
    for c in sorted(set(packages) & set(chain)):
        if packages[c] != chain[c]:
            problems.append(
                f"channel {c} is numbered {packages[c]} in `packages:` but {chain[c]} in `publish_retained_state`"
            )
    for c, nn in sorted(packages.items()):
        if c != f"relay_{nn}":
            problems.append(f"channel {c} has nn \"{nn}\": the key must be relay_<nn>")
    if not packages:
        problems.append("no channels found under `packages:`")
    return problems


def main():
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        with open(variants.resolve_firmware(sys.argv[1]), encoding="utf-8") as handle:
            problems = check(handle.read())
    except OSError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

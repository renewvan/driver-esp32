#!/usr/bin/env python3
"""CI guard: the channels under `packages:` must equal the channels in the connect chain.

The sixteen retained states are published from ONE connect chain (the order of separate
on_connect entries is undefined), which lists every channel by hand. A channel present under
`packages:` but missing from that chain would never publish its state, and `esphome config`
would not notice.

usage: check_channels.py esp32-16x-relay-driver.yaml
"""

import re
import sys

# `relay_03: !include { file: pkg/relay-channel.yaml, vars: { ch: relay_03, bit: 2 } }`
PACKAGE = re.compile(r"vars:\s*\{\s*ch:\s*([A-Za-z0-9_]+)\s*,")
# `{"relay_03", id(relay_relay_03), &id(name_relay_03)},`
CHAIN = re.compile(r'\{\s*"([A-Za-z0-9_]+)"\s*,\s*id\(relay_')


def check(text):
    packages = set(PACKAGE.findall(text))
    chain = set(CHAIN.findall(text))
    problems = [f"channel {c} is in `packages:` but not in the connect chain" for c in sorted(packages - chain)]
    problems += [f"channel {c} is in the connect chain but not in `packages:`" for c in sorted(chain - packages)]
    if not packages:
        problems.append("no channels found under `packages:`")
    return problems


def main():
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    with open(sys.argv[1], encoding="utf-8") as handle:
        problems = check(handle.read())
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Clear the retained topics of a board that was removed or renamed, so no ghost Driver stays.

A board is its own Driver `esp32-<name>` (see GLOSSARY.md), and renaming is a new Driver: the old
name's retained topics stay on the broker and the old Driver keeps showing. This finds what is
retained for the name and clears it by publishing an empty retained message to each topic:

  renewvan/esp32-<name>/info and renewvan/esp32-<name>/health     the Driver
  renewvan/relay/<name>-<nn>/<anything>                            its relay entities (state, name, driver)

It reads what is actually retained instead of assuming sixteen channels, so a board of any variant
is cleared. It refuses while the board's health is `online` (a live board would republish at once)
unless --force, and it verifies afterwards that nothing is left. Needs mosquitto_sub/mosquitto_pub.

usage: clear_board.py NAME [--dry-run] [--force] [--wait SECONDS] [-- MOSQUITTO ARGS...]
  e.g. clear_board.py front --dry-run -- -h broker.local -u admin -P secret

Everything after `--` is passed to mosquitto_sub and mosquitto_pub (host, port, credentials, TLS).
The credential must be allowed to publish to the board's topics. Importable: topics_to_clear().
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import variants  # noqa: E402

BUS = "renewvan"


def health_topic(board):
    return f"{BUS}/{variants.driver_key(board)}/health"


def subscriptions(board):
    """The filters that cover everything a board can have retained."""
    return [f"{BUS}/{variants.driver_key(board)}/#", f"{BUS}/relay/+/#"]


def topics_to_clear(board, topics):
    """The subset of `topics` that belongs to `board`, sorted.

    A relay id is `<board>-<nn>`; a board name never ends in `-<digits>`, so `front` does not own
    `front-left-01` (that is board `front-left`).
    """
    driver = f"{BUS}/{variants.driver_key(board)}/"
    relay = re.compile(rf"^{BUS}/relay/{re.escape(board)}-[0-9]+/.+")
    return sorted({t for t in topics if t.startswith(driver) or relay.match(t)})


def parse_retained(output):
    """`mosquitto_sub -v` lines -> {topic: payload}."""
    found = {}
    for line in output.splitlines():
        topic, _, payload = line.partition(" ")
        if topic:
            found[topic] = payload
    return found


def read_retained(board, mosquitto_args, wait):
    """Everything retained under the board's filters, as {topic: payload}."""
    cmd = ["mosquitto_sub", "-v", "--retained-only", "-W", str(wait), *mosquitto_args]
    for flt in subscriptions(board):
        cmd += ["-t", flt]
    # -W ends with exit code 27 when the timeout passes: that is how a quiet broker ends, not a failure.
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode not in (0, 27):
        raise RuntimeError(f"mosquitto_sub failed ({result.returncode}): {result.stderr.strip()}")
    return parse_retained(result.stdout)


def clear(topic, mosquitto_args):
    cmd = ["mosquitto_pub", *mosquitto_args, "-r", "-n", "-t", topic]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"clearing {topic} failed: {result.stderr.strip()}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("name", help="the board name that was removed or renamed")
    parser.add_argument("--dry-run", action="store_true", help="list what would be cleared, change nothing")
    parser.add_argument("--force", action="store_true", help="clear even if the board's health is online")
    parser.add_argument("--wait", type=int, default=3, help="seconds to wait for retained topics (default 3)")
    argv = sys.argv[1:] if argv is None else list(argv)
    # Everything after `--` belongs to mosquitto, not to this parser.
    split = argv.index("--") if "--" in argv else len(argv)
    args = parser.parse_args(argv[:split])
    args.mosquitto_args = argv[split + 1 :]

    problems = variants.validate_board(args.name)
    if problems:
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        return 2

    try:
        retained = read_retained(args.name, args.mosquitto_args, args.wait)
        owned = topics_to_clear(args.name, retained)
        if not owned:
            print(f"nothing retained for board '{args.name}': no ghost Driver to clear")
            return 0

        for topic in owned:
            print(("would clear " if args.dry_run else "clear ") + topic)
        if args.dry_run:
            return 0
        if retained.get(health_topic(args.name), "").strip('" ') == "online" and not args.force:
            print(
                f"error: esp32-{args.name} is online: the board is still running and would republish. "
                "Power it off (or reflash it under another name) first, or pass --force.",
                file=sys.stderr,
            )
            return 1

        for topic in owned:
            clear(topic, args.mosquitto_args)
        left = topics_to_clear(args.name, read_retained(args.name, args.mosquitto_args, args.wait))
    except (RuntimeError, FileNotFoundError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    if left:
        print("error: still retained: " + ", ".join(left), file=sys.stderr)
        return 1
    print(f"cleared {len(owned)} retained topics: esp32-{args.name} no longer exists on the bus")
    return 0


if __name__ == "__main__":
    sys.exit(main())

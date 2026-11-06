#!/usr/bin/env python3
"""The firmware variants of this repo, and the board names built from them.

A variant is one ESP32 firmware image (one kind of board). Its name is the stem shared by
  manifests/<variant>.json   the static fields of the kind; it MUST NOT carry a `driver` key
  firmware/<variant>.yaml    the ESPHome entrypoint
A board is one physical unit running a variant. Its owner names it once at flash time
(`flash.sh <variant> --board <name>`) and its Driver key is `esp32-<name>` (driver_key()): that is
the only place the key is composed. The manifests/ directory is the list of variants: CI, the
release build and every script derive them from it, so adding a variant needs no edit elsewhere.

usage: variants.py list          print the variants as a compact JSON array (for a CI matrix)
       variants.py check         fail unless every variant satisfies the layout invariants above
       variants.py board NAME    fail unless NAME is a valid board name (see validate_board)

Importable: ROOT, DRIVER_PREFIX, discover(), manifest_path(), firmware_path(), resolve_manifest(),
check(), validate_board(), driver_key().
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# A board's Driver key is `<DRIVER_PREFIX>-<board>`: the repo name minus `driver-`, then the board.
DRIVER_PREFIX = "esp32"
# The Driver slug grammar (hub ADR 0019/0020): lowercase, digits, single hyphens between parts.
SLUG = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
# Relay ids are `<board>-<nn>`; a board ending in `-<digits>` would be ambiguous with one.
TRAILING_DIGITS = re.compile(r"-[0-9]+$")
# The ESPHome node name `renewvan-esp32-<board>` may be 31 characters (the hostname limit);
# `renewvan-esp32-` is 15 of them. Also keeps the fallback AP SSID within 32 bytes.
MAX_BOARD_LENGTH = 16


def validate_board(name):
    """Why `name` is not a usable board name; an empty list means it is."""
    problems = []
    if not SLUG.match(name):
        problems.append(
            f"board name '{name}' is not a slug (lowercase letters and digits, starting with a "
            "letter, words joined by single hyphens)"
        )
    elif TRAILING_DIGITS.search(name):
        problems.append(
            f"board name '{name}' must not end in -<digits>: relay ids are <board>-<nn> and "
            "would be ambiguous with the board name"
        )
    if len(name) > MAX_BOARD_LENGTH:
        problems.append(
            f"board name '{name}' is longer than {MAX_BOARD_LENGTH} characters (the ESPHome "
            "node name renewvan-esp32-<board> is limited to 31)"
        )
    return problems


def driver_key(board):
    """The Driver a board appears as on the bus."""
    return f"{DRIVER_PREFIX}-{board}"


def discover(root=ROOT):
    """Variant names, sorted: the stems of manifests/*.json."""
    return sorted(path.stem for path in (Path(root) / "manifests").glob("*.json"))


def manifest_path(variant, root=ROOT):
    return Path(root) / "manifests" / f"{variant}.json"


def firmware_path(variant, root=ROOT):
    return Path(root) / "firmware" / f"{variant}.yaml"


def resolve_manifest(arg, root=ROOT):
    """A variant name (`esp32-16x-relay`) or a path to a manifest; returns (path, variant|None).

    `variant` is set only when a name was given, so a caller can hold the manifest to the name.
    """
    if "/" in arg or arg.endswith(".json"):
        return Path(arg), None
    return manifest_path(arg, root), arg


def resolve_firmware(arg, root=ROOT):
    """A variant name or a path to a firmware yaml."""
    if "/" in arg or arg.endswith((".yaml", ".yml")):
        return Path(arg)
    return firmware_path(arg, root)


def check(root=ROOT):
    """Layout problems across every variant (an empty list means the layout is sound)."""
    root = Path(root)
    variants = discover(root)
    problems = [] if variants else ["no variants: manifests/ holds no *.json"]

    for variant in variants:
        try:
            manifest = json.loads(manifest_path(variant, root).read_text(encoding="utf-8"))
        except ValueError as err:
            problems.append(f"manifests/{variant}.json is not valid JSON: {err}")
            continue
        if "driver" in manifest:
            problems.append(
                f"manifests/{variant}.json has a 'driver' key: a manifest describes the kind only; "
                "the Driver key is composed at flash time from --board"
            )
        if not firmware_path(variant, root).is_file():
            problems.append(f"manifests/{variant}.json has no firmware/{variant}.yaml")

    for path in sorted((root / "firmware").glob("*.yaml")):
        # firmware/secrets.yaml is the symlink ESPHome's secret lookup needs, not an entrypoint.
        if path.name != "secrets.yaml" and path.stem not in variants:
            problems.append(f"firmware/{path.name} has no manifests/{path.stem}.json")

    return problems


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "board":
        problems = validate_board(sys.argv[2])
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        return 2 if problems else 0

    if len(sys.argv) != 2 or sys.argv[1] not in ("list", "check"):
        print(__doc__, file=sys.stderr)
        return 2

    if sys.argv[1] == "list":
        print(json.dumps(discover(), separators=(",", ":")))
        return 0

    problems = check()
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

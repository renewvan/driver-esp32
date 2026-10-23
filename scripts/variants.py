#!/usr/bin/env python3
"""The firmware variants of this repo, discovered from the directory layout.

A variant is one ESP32 firmware image, i.e. one Driver. Its name is the stem shared by
  manifests/<variant>.json   the static Driver fields; its `driver` key MUST equal <variant>
  firmware/<variant>.yaml    the ESPHome entrypoint
The manifests/ directory is the list: CI, the release build and every script derive the variants
from it, so adding a variant needs no edit anywhere else.

usage: variants.py list    print the variants as a compact JSON array (for a CI matrix)
       variants.py check   fail unless every variant satisfies the layout invariants above

Importable: ROOT, discover(), manifest_path(), firmware_path(), resolve_manifest(), check().
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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
        if manifest.get("driver") != variant:
            problems.append(
                f"manifests/{variant}.json has driver '{manifest.get('driver')}', expected '{variant}'"
            )
        if not firmware_path(variant, root).is_file():
            problems.append(f"manifests/{variant}.json has no firmware/{variant}.yaml")

    for path in sorted((root / "firmware").glob("*.yaml")):
        # firmware/secrets.yaml is the symlink ESPHome's secret lookup needs, not an entrypoint.
        if path.name != "secrets.yaml" and path.stem not in variants:
            problems.append(f"firmware/{path.name} has no manifests/{path.stem}.json")

    return problems


def main():
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

#!/usr/bin/env python3
"""CI guard for the stamped version in a resolved ESPHome configuration.

`esphome config` treats an undeclared substitution as a warning: the literal `${name}`
survives into the configuration and the command still exits 0, so a dropped `-s version=...`
would silently ship a placeholder. This fails the build instead.

Fails when:
  * the resolved configuration still contains an unexpanded `$name` / `${name}`;
  * the resolved `esphome.project.version` differs from --expected-version;
  * the version the build action reported differs from --expected-version;
  * the resolved configuration is not the --variant's: its project name is not
    `renewvan.driver-esp32-<variant>`, or its node name is not `renewvan-<variant>`;
  * the resolved health topic is not the repo's one Driver key (`renewvan/esp32/health`,
    variants.DRIVER_KEY): a build stamped with another repo's manifest.

usage: check_resolved_config.py RESOLVED_YAML --variant V --expected-version V --reported-version V
"""

import argparse
import re
import sys

import variants

# Same shape ESPHome itself treats as a substitution (`$name` or `${...}`).
PLACEHOLDER = re.compile(r"\$\{[^}\n]*\}|\$[A-Za-z_][A-Za-z0-9_]*")
PROJECT_NAME = re.compile(
    r"^esphome:\n(?:[ ]{2}.*\n)*?[ ]{2}project:\n(?:[ ]{4}.*\n)*?[ ]{4}name:[ ]*(.*?)[ ]*$",
    re.MULTILINE,
)
NODE_NAME = re.compile(r"^esphome:\n(?:[ ]{2}.*\n)*?[ ]{2}name:[ ]*(.*?)[ ]*$", re.MULTILINE)
PROJECT_VERSION = re.compile(
    r"^esphome:\n(?:[ ]{2}.*\n)*?[ ]{2}project:\n(?:[ ]{4}.*\n)*?[ ]{4}version:[ ]*(.*?)[ ]*$",
    re.MULTILINE,
)


def check(resolved, variant, expected, reported):
    problems = []

    for match in sorted(set(PLACEHOLDER.findall(resolved))):
        problems.append(f"unexpanded placeholder in resolved configuration: {match}")

    found = PROJECT_VERSION.search(resolved)
    if found is None:
        problems.append("resolved configuration has no esphome.project.version")
    elif found.group(1) != expected:
        problems.append(
            f"resolved esphome.project.version is '{found.group(1)}', expected '{expected}'"
        )

    name = PROJECT_NAME.search(resolved)
    if name is None or name.group(1) != f"renewvan.driver-esp32-{variant}":
        problems.append(
            f"resolved esphome.project.name is '{name.group(1) if name else None}', "
            f"expected 'renewvan.driver-esp32-{variant}'"
        )

    node = NODE_NAME.search(resolved)
    if node is None or node.group(1) != f"renewvan-{variant}":
        problems.append(
            f"resolved esphome.name is '{node.group(1) if node else None}', expected 'renewvan-{variant}'"
        )

    health = f"renewvan/{variants.DRIVER_KEY}/health"
    if not re.search(rf"^[ ]+topic:[ ]*{re.escape(health)}[ ]*$", resolved, re.MULTILINE):
        problems.append(f"resolved configuration never uses the health topic {health}")

    if reported != expected:
        problems.append(
            f"build action reported project version '{reported}', expected '{expected}'"
        )

    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("resolved")
    parser.add_argument("--variant", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--reported-version", required=True)
    args = parser.parse_args()

    with open(args.resolved, encoding="utf-8") as handle:
        resolved = handle.read()

    problems = check(resolved, args.variant, args.expected_version, args.reported_version)
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

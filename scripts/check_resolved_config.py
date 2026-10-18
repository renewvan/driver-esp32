#!/usr/bin/env python3
"""CI guard for the stamped version in a resolved ESPHome configuration.

`esphome config` treats an undeclared substitution as a warning: the literal `${name}`
survives into the configuration and the command still exits 0, so a dropped `-s version=...`
would silently ship a placeholder. This fails the build instead.

Fails when:
  * the resolved configuration still contains an unexpanded `$name` / `${name}`;
  * the resolved `esphome.project.version` differs from --expected-version;
  * the version the build action reported differs from --expected-version.

usage: check_resolved_config.py RESOLVED_YAML --expected-version V --reported-version V
"""

import argparse
import re
import sys

# Same shape ESPHome itself treats as a substitution (`$name` or `${...}`).
PLACEHOLDER = re.compile(r"\$\{[^}\n]*\}|\$[A-Za-z_][A-Za-z0-9_]*")
PROJECT_VERSION = re.compile(
    r"^esphome:\n(?:[ ]{2}.*\n)*?[ ]{2}project:\n(?:[ ]{4}.*\n)*?[ ]{4}version:[ ]*(.*?)[ ]*$",
    re.MULTILINE,
)


def check(resolved, expected, reported):
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

    if reported != expected:
        problems.append(
            f"build action reported project version '{reported}', expected '{expected}'"
        )

    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("resolved")
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--reported-version", required=True)
    args = parser.parse_args()

    with open(args.resolved, encoding="utf-8") as handle:
        resolved = handle.read()

    problems = check(resolved, args.expected_version, args.reported_version)
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

"""Seam: resolved `esphome config` output -> pass/fail verdict for CI.

Fixtures are real `esphome config` output shapes: an undeclared substitution survives
verbatim as `${name}` and `esphome config` still exits 0, so only this guard catches it.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_resolved_config.py"

RESOLVED = """\
substitutions:
  node_name: renewvan-esp32-relay
  version: {version}
esphome:
  name: renewvan-esp32-relay
  project:
    name: renewvan.node-esp32-relay
    version: {version}
  min_version: 2026.9.1
mqtt:
  broker: 192.168.1.10
"""


def check(resolved, expected_version="ci-1234abc", reported_version=None):
    """Run the guard. `reported_version` is the build action's `project-version` output."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "resolved.yaml"
        path.write_text(resolved)
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(path),
                "--expected-version",
                expected_version,
                "--reported-version",
                expected_version if reported_version is None else reported_version,
            ],
            capture_output=True,
            text=True,
        )


class ResolvedConfigGuard(unittest.TestCase):
    def test_fully_expanded_config_with_matching_version_passes(self):
        result = check(RESOLVED.format(version="ci-1234abc"))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_dropped_version_substitution_fails_on_the_surviving_placeholder(self):
        # The exact failure the guard exists for: substitution not passed, config exits 0,
        # and the literal placeholder would ship as the version.
        result = check(RESOLVED.format(version="${version}"), reported_version="${version}")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("${version}", result.stderr)

    def test_any_unexpanded_placeholder_fails_not_only_version(self):
        resolved = RESOLVED.format(version="ci-1234abc").replace(
            "broker: 192.168.1.10", "broker: ${mqtt_host}"
        )
        result = check(resolved)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("${mqtt_host}", result.stderr)

    def test_bare_dollar_name_placeholder_fails_too(self):
        resolved = RESOLVED.format(version="ci-1234abc").replace(
            "broker: 192.168.1.10", "broker: $mqtt_host"
        )
        result = check(resolved)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("$mqtt_host", result.stderr)

    def test_action_reported_version_differing_from_ci_value_fails(self):
        result = check(RESOLVED.format(version="ci-1234abc"), reported_version="dev")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dev", result.stderr)
        self.assertIn("ci-1234abc", result.stderr)

    def test_missing_reported_version_fails(self):
        # build-action only emits project-version when esphome.project is configured.
        result = check(RESOLVED.format(version="ci-1234abc"), reported_version="")
        self.assertNotEqual(result.returncode, 0)

    def test_resolved_project_version_differing_from_ci_value_fails(self):
        # Reported by the action as correct, but the resolved config disagrees.
        result = check(RESOLVED.format(version="dev"), expected_version="ci-1234abc")
        self.assertNotEqual(result.returncode, 0)

    def test_dev_default_is_accepted_only_when_it_is_the_expected_value(self):
        result = check(RESOLVED.format(version="dev"), expected_version="dev")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

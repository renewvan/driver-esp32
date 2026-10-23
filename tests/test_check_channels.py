"""Seam: esp32-16x-relay-driver.yaml text -> pass/fail verdict on channel agreement.

A channel listed under `packages:` but missing from the connect chain would never publish
its retained state, and `esphome config` would not notice. Observed through the script's
command line, the way CI uses it.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_channels.py"


def channel_yaml(package_ids, chain_ids):
    packages = "".join(
        f"  {c}: !include {{ file: pkg/relay-channel.yaml, vars: {{ ch: {c}, bit: {i} }} }}\n"
        for i, c in enumerate(package_ids)
    )
    chain = "".join(
        f'          {{"{c}", id(relay_{c}), &id(name_{c})}},\n' for c in chain_ids
    )
    return f"mqtt:\n  on_connect:\n    - lambda: |-\n        const Channel channels[] = {{\n{chain}        }};\npackages:\n{packages}"


def check(text):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "device.yaml"
        path.write_text(text)
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True
        )


class CheckChannels(unittest.TestCase):
    def test_matching_channels_pass(self):
        ids = [f"relay_{n:02d}" for n in range(1, 17)]
        result = check(channel_yaml(ids, ids))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_channel_missing_from_the_connect_chain_fails_and_is_named(self):
        ids = [f"relay_{n:02d}" for n in range(1, 17)]
        result = check(channel_yaml(ids, ids[:-1]))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("relay_16", result.stderr)

    def test_a_channel_in_the_chain_but_not_in_packages_fails_and_is_named(self):
        ids = [f"relay_{n:02d}" for n in range(1, 17)]
        result = check(channel_yaml(ids[:-1], ids))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("relay_16", result.stderr)

    def test_order_does_not_matter(self):
        ids = [f"relay_{n:02d}" for n in range(1, 17)]
        result = check(channel_yaml(ids, list(reversed(ids))))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_repos_own_board_file_passes(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(ROOT / "esp32-16x-relay-driver.yaml")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

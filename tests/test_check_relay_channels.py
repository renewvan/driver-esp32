"""Seam: a relay variant's yaml -> pass/fail verdict on channel agreement.

A channel listed under `packages:` but missing from `publish_retained_state` would never publish
its retained state, and `esphome config` would not notice. Observed through the script's
command line, the way CI uses it.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_relay_channels.py"


def channel_yaml(package_ids, chain_ids):
    packages = "".join(
        f"  {c}: !include {{ file: ../packages/relay-channel.yaml, vars: {{ ch: {c}, nn: \"{c[-2:]}\", bit: {i} }} }}\n"
        for i, c in enumerate(package_ids)
    )
    chain = "".join(
        f'          {{"${{board}}-{c[-2:]}", id(relay_{c}), &id(name_{c})}},\n' for c in chain_ids
    )
    return (
        "script:\n  - id: publish_retained_state\n    then:\n      - lambda: |-\n"
        f"          const Channel channels[] = {{\n{chain}          }};\npackages:\n{packages}"
    )


def check(text):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "variant.yaml"
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

    def test_a_channel_number_that_differs_between_package_and_chain_fails_and_is_named(self):
        ids = [f"relay_{n:02d}" for n in range(1, 17)]
        text = channel_yaml(ids, ids).replace('"${board}-05"', '"${board}-50"')
        result = check(text)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("relay_05", result.stderr)

    def test_a_channel_number_that_does_not_match_its_channel_key_fails(self):
        ids = [f"relay_{n:02d}" for n in range(1, 17)]
        text = channel_yaml(ids, ids).replace('ch: relay_05, nn: "05"', 'ch: relay_05, nn: "06"')
        result = check(text)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("relay_05", result.stderr)

    def test_the_relay_variant_passes_by_name_and_by_path(self):
        for argument in ("esp32-16x-relay", str(ROOT / "firmware" / "esp32-16x-relay.yaml"), "esp32-8x-relay"):
            with self.subTest(argument=argument):
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), argument], capture_output=True, text=True
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_an_unknown_variant_fails(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "no-such-variant"], capture_output=True, text=True
        )
        self.assertNotEqual(result.returncode, 0)

    def test_the_retained_state_step_publishes_the_owning_driver_for_every_channel(self):
        for variant in ("esp32-16x-relay", "esp32-8x-relay"):
            with self.subTest(variant=variant):
                text = (ROOT / "firmware" / f"{variant}.yaml").read_text()
                self.assertIn('publish(base + "/driver", std::string("\\"${driver}\\""), 0, true)', text)

if __name__ == "__main__":
    unittest.main()

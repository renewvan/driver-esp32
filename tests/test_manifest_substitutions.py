"""Seam: a variant's manifest -> ESPHome `key=value` substitution lines.

Observed through the script's command line, the way the flash script and CI use it.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "manifest_substitutions.py"

FULL = {
    "product": "ESP32 16-channel relay board",
    "source": "ESP32 with two chained SN74HC595 shift registers",
    "publishes": ["relay"],
    "manufacturer": "renewvan",
    "homepage": "https://github.com/renewvan/driver-esp32",
}


def run(manifest, *extra):
    if "--board" not in extra:
        extra = ("--board", "front", *extra)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "manifest.json"
        path.write_text(json.dumps(manifest))
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(path), *extra],
            capture_output=True,
            text=True,
        )


def lines(result):
    return dict(line.split("=", 1) for line in result.stdout.splitlines())


class ManifestSubstitutions(unittest.TestCase):
    def test_full_manifest_yields_every_static_field(self):
        result = run(FULL)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            lines(result),
            {
                "board": "front",
                "driver": "esp32-front",
                "product": "ESP32 16-channel relay board",
                "source": "ESP32 with two chained SN74HC595 shift registers",
                "publishes": '[\\"relay\\"]',
                "manufacturer": "renewvan",
                "homepage": "https://github.com/renewvan/driver-esp32",
            },
        )

    def test_empty_optional_fields_are_omitted_not_blank(self):
        minimal = {k: v for k, v in FULL.items() if k not in ("manufacturer", "homepage")}
        self.assertEqual(
            set(lines(run(minimal))), {"board", "driver", "product", "source", "publishes"}
        )

        blank = {**FULL, "manufacturer": "", "homepage": ""}
        self.assertEqual(
            set(lines(run(blank))), {"board", "driver", "product", "source", "publishes"}
        )

    def test_publishes_decodes_back_to_the_json_array_for_multiple_types(self):
        # The value is C++-escaped for the firmware's string literal; undo exactly that
        # escaping (what the compiler does) and it must be the JSON array.
        raw = lines(run({**FULL, "publishes": ["relay", "temperature"]}))["publishes"]
        self.assertEqual(json.loads(json.loads('"' + raw + '"')), ["relay", "temperature"])

    def test_values_are_escaped_for_embedding_in_a_cpp_string_literal(self):
        # Substitutions are pasted textually between double quotes in the firmware lambda,
        # so an unescaped quote or backslash breaks the build (or injects code).
        values = lines(run({**FULL, "product": 'Relay "pro" \\ v2', "source": 'a"b'}))
        self.assertEqual(values["product"], 'Relay \\"pro\\" \\\\ v2')
        self.assertEqual(values["source"], 'a\\"b')

    def test_value_containing_equals_survives_a_split_on_first_equals(self):
        result = run({**FULL, "homepage": "https://example.com/?a=b"})
        self.assertEqual(lines(result)["homepage"], "https://example.com/?a=b")

    def test_esphome_args_mode_emits_nul_separated_dash_s_triples(self):
        # What `esphome -s KEY VALUE ...` needs, so flash.sh and CI share one translation.
        result = run(FULL, "--esphome-args")
        self.assertEqual(result.returncode, 0, result.stderr)
        tokens = result.stdout.split("\0")[:-1]
        self.assertEqual(tokens[0::3], ["-s"] * (len(tokens) // 3))
        self.assertEqual(
            dict(zip(tokens[1::3], tokens[2::3])),
            {
                "board": "front",
                "driver": "esp32-front",
                "product": "ESP32 16-channel relay board",
                "source": "ESP32 with two chained SN74HC595 shift registers",
                "publishes": '[\\"relay\\"]',
                "manufacturer": "renewvan",
                "homepage": "https://github.com/renewvan/driver-esp32",
            },
        )

    def test_esphome_args_mode_keeps_a_value_with_spaces_and_equals_as_one_token(self):
        result = run({**FULL, "source": "a b=c"}, "--esphome-args")
        tokens = result.stdout.split("\0")[:-1]
        self.assertEqual(dict(zip(tokens[1::3], tokens[2::3]))["source"], "a b=c")

    def test_esphome_args_mode_still_rejects_an_invalid_manifest(self):
        result = run({**FULL, "version": "9.9.9"}, "--esphome-args")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_manifest_that_carries_a_version_is_rejected(self):
        # The version comes only from the checkout; a hand-written one must not slip through.
        result = run({**FULL, "version": "9.9.9"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("version", result.stderr)

    def test_manifest_that_carries_board_serial_is_rejected(self):
        result = run({**FULL, "board_serial": "AA:BB:CC:DD:EE:FF"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("board_serial", result.stderr)

    def test_missing_required_field_is_rejected(self):
        for field in ("product", "source", "publishes"):
            with self.subTest(field=field):
                broken = {k: v for k, v in FULL.items() if k != field}
                result = run(broken)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(field, result.stderr)

    def test_empty_publishes_is_rejected(self):
        result = run({**FULL, "publishes": []})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("publishes", result.stderr)

    def test_the_relay_variant_flattens_the_same_by_name_and_by_path(self):
        manifest = SCRIPT.parent.parent / "manifests" / "esp32-16x-relay.json"
        by_path, by_name = (
            subprocess.run([sys.executable, str(SCRIPT), arg, "--board", "front"], capture_output=True, text=True)
            for arg in (str(manifest), "esp32-16x-relay")
        )
        self.assertEqual(by_path.returncode, 0, by_path.stderr)
        self.assertEqual(by_name.stdout, by_path.stdout)
        values = lines(by_name)
        self.assertEqual(values["driver"], "esp32-front")
        self.assertEqual(values["publishes"], '[\\"relay\\"]')
        self.assertEqual(values["homepage"], "https://github.com/renewvan/driver-esp32")

    def test_an_unknown_variant_name_is_rejected(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "no-such-variant", "--board", "front"], capture_output=True, text=True
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_a_manifest_with_a_driver_key_is_rejected(self):
        # The Driver key is composed from --board; a manifest cannot pick one.
        for driver in ("esp32", "esp32-front"):
            with self.subTest(driver=driver):
                result = run({**FULL, "driver": driver})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("driver", result.stderr)
                self.assertEqual(result.stdout, "")

    def test_board_adds_the_board_and_its_driver_key(self):
        result = run(FULL, "--board", "front")
        self.assertEqual(result.returncode, 0, result.stderr)
        values = lines(result)
        self.assertEqual(values["board"], "front")
        self.assertEqual(values["driver"], "esp32-front")

    def test_board_in_esphome_args_mode(self):
        tokens = run(FULL, "--board", "rear", "--esphome-args").stdout.split("\0")[:-1]
        values = dict(zip(tokens[1::3], tokens[2::3]))
        self.assertEqual((values["board"], values["driver"]), ("rear", "esp32-rear"))

    def test_two_boards_of_one_manifest_differ_only_in_board_and_driver(self):
        a, b = lines(run(FULL, "--board", "front")), lines(run(FULL, "--board", "rear"))
        self.assertEqual({k for k in a if a[k] != b[k]}, {"board", "driver"})

    def test_an_invalid_board_is_rejected_with_nothing_on_stdout(self):
        for name in ("Front", "front-1", "front_x", "", "a" * 17):
            with self.subTest(name=name):
                result = run(FULL, "--board", name, "--esphome-args")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_without_board_it_fails_loudly_with_nothing_on_stdout(self):
        # A build that forgot --board must not get placeholders: fail with a clear message.
        for extra in ((), ("--esphome-args",)):
            with self.subTest(extra=extra):
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "manifest.json"
                    path.write_text(json.dumps(FULL))
                    result = subprocess.run(
                        [sys.executable, str(SCRIPT), str(path), *extra], capture_output=True, text=True
                    )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn("--board", result.stderr)


if __name__ == "__main__":
    unittest.main()


class HubPowerTest(unittest.TestCase):
    def sub(self, *extra):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "esp32-16x-relay", "--board", "front", *extra],
            capture_output=True,
            text=True,
        )

    def test_hub_power_adds_the_channel_key(self):
        result = self.sub("--hub-power", "relay_01")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(lines(result)["hub_power"], "relay_01")

    def test_without_hub_power_there_is_no_hub_power_line(self):
        self.assertNotIn("hub_power", lines(self.sub()))
        self.assertNotIn("hub_power", lines(self.sub("--hub-power", "")))

    def test_a_channel_the_variant_does_not_have_is_rejected_with_nothing_on_stdout(self):
        result = self.sub("--hub-power", "relay_17")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("relay_17", result.stderr)

    def test_the_8x_variant_has_eight_channels(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "esp32-8x-relay", "--board", "front", "--hub-power", "relay_09"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_hub_power_needs_a_variant_name_not_a_path(self):
        result = run(FULL, "--hub-power", "relay_01")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("variant name", result.stderr)


class BleChannelsTest(unittest.TestCase):
    """--ble-channels: the board's Direct control allowlist (packages/ble-wake.yaml)."""

    def sub(self, *extra, variant="esp32-16x-relay"):
        return subprocess.run(
            [sys.executable, str(SCRIPT), variant, "--board", "front", *extra],
            capture_output=True,
            text=True,
        )

    def test_listed_channels_pass_through_comma_separated(self):
        result = self.sub("--ble-channels", "relay_03, relay_04")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(lines(result)["ble_channels"], "relay_03,relay_04")

    def test_none_by_default(self):
        self.assertNotIn("ble_channels", lines(self.sub()))
        self.assertNotIn("ble_channels", lines(self.sub("--ble-channels", "")))

    def test_hub_power_is_never_a_direct_control_channel(self):
        result = self.sub("--hub-power", "relay_01", "--ble-channels", "relay_03,relay_01")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("Hub power", result.stderr)

    def test_a_channel_the_variant_does_not_have_is_rejected(self):
        result = self.sub("--ble-channels", "relay_09", variant="esp32-8x-relay")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("relay_09", result.stderr)

    def test_a_repeated_channel_is_rejected(self):
        result = self.sub("--ble-channels", "relay_03,relay_03")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("twice", result.stderr)

"""Seam: manifest.json -> ESPHome `key=value` substitution lines.

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
    "node": "esp32-relay",
    "product": "ESP32 16-channel relay board",
    "source": "ESP32 with two chained SN74HC595 shift registers",
    "publishes": ["relay"],
    "manufacturer": "renewvan",
    "homepage": "https://github.com/renewvan/node-esp32-relay",
}


def run(manifest, *extra):
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
                "node": "esp32-relay",
                "product": "ESP32 16-channel relay board",
                "source": "ESP32 with two chained SN74HC595 shift registers",
                "publishes": '[\\"relay\\"]',
                "manufacturer": "renewvan",
                "homepage": "https://github.com/renewvan/node-esp32-relay",
            },
        )

    def test_empty_optional_fields_are_omitted_not_blank(self):
        minimal = {k: v for k, v in FULL.items() if k not in ("manufacturer", "homepage")}
        self.assertEqual(
            set(lines(run(minimal))), {"node", "product", "source", "publishes"}
        )

        blank = {**FULL, "manufacturer": "", "homepage": ""}
        self.assertEqual(
            set(lines(run(blank))), {"node", "product", "source", "publishes"}
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
                "node": "esp32-relay",
                "product": "ESP32 16-channel relay board",
                "source": "ESP32 with two chained SN74HC595 shift registers",
                "publishes": '[\\"relay\\"]',
                "manufacturer": "renewvan",
                "homepage": "https://github.com/renewvan/node-esp32-relay",
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

    def test_manifest_that_carries_host_serial_is_rejected(self):
        result = run({**FULL, "host_serial": "AA:BB:CC:DD:EE:FF"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("host_serial", result.stderr)

    def test_missing_required_field_is_rejected(self):
        for field in ("node", "product", "source", "publishes"):
            with self.subTest(field=field):
                broken = {k: v for k, v in FULL.items() if k != field}
                result = run(broken)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(field, result.stderr)

    def test_empty_publishes_is_rejected(self):
        result = run({**FULL, "publishes": []})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("publishes", result.stderr)

    def test_the_repos_own_manifest_flattens_to_the_renamed_node(self):
        manifest = SCRIPT.parent.parent / "manifest.json"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(manifest)], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        values = lines(result)
        self.assertEqual(values["node"], "esp32-relay")
        self.assertEqual(values["publishes"], '[\\"relay\\"]')
        self.assertEqual(values["homepage"], "https://github.com/renewvan/node-esp32-relay")


if __name__ == "__main__":
    unittest.main()

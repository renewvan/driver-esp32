"""Seam: the directory layout -> the list of variants CI and the scripts iterate over.

Real invariants of the repo itself (every manifest has its firmware, its `driver` equals its
file stem, the manifests are valid for the build) plus the discovery logic against synthetic
trees, observed through the script's command line the way CI uses it.
"""

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "variants.py"
sys.path.insert(0, str(ROOT / "scripts"))
import manifest_substitutions  # noqa: E402
import variants  # noqa: E402

MANIFEST = {
    "product": "Demo board",
    "source": "Demo",
    "publishes": ["temperature"],
}


def make_tree(root, manifests=(), firmware=()):
    """`manifests` maps stem -> manifest dict; `firmware` is stems to give a firmware yaml."""
    (root / "manifests").mkdir()
    (root / "firmware").mkdir()
    for stem, manifest in dict(manifests).items():
        (root / "manifests" / f"{stem}.json").write_text(json.dumps(manifest))
    for stem in firmware:
        (root / "firmware" / f"{stem}.yaml").write_text("esphome:\n")


def run(command, cwd):
    """Run scripts/variants.py as a copy inside `cwd`, so ROOT is the synthetic tree."""
    (cwd / "scripts").mkdir(exist_ok=True)
    (cwd / "scripts" / "variants.py").write_text(SCRIPT.read_text())
    return subprocess.run(
        [sys.executable, str(cwd / "scripts" / "variants.py"), command],
        capture_output=True,
        text=True,
    )


class RepoVariants(unittest.TestCase):
    def test_there_is_at_least_one_variant(self):
        self.assertTrue(variants.discover())

    def test_the_repo_layout_is_sound(self):
        self.assertEqual(variants.check(), [])

    def test_the_driver_key_is_esp32_dash_board(self):
        self.assertEqual(variants.driver_key("front"), "esp32-front")

    def test_every_manifest_has_its_firmware_and_no_driver_key(self):
        for variant in variants.discover():
            with self.subTest(variant=variant):
                manifest = json.loads(variants.manifest_path(variant).read_text())
                self.assertNotIn("driver", manifest)
                self.assertTrue(variants.firmware_path(variant).is_file())

    def test_every_manifest_flattens_for_the_build(self):
        for variant in variants.discover():
            with self.subTest(variant=variant):
                manifest = json.loads(variants.manifest_path(variant).read_text())
                values = manifest_substitutions.flatten(manifest)
                self.assertNotIn("driver", values)

    def test_every_firmware_declares_the_identity_the_base_package_needs(self):
        # packages/base.yaml uses these and cannot default them: a variant that omits one
        # would ship a literal `${...}` (the placeholder guard catches it in CI too).
        for variant in variants.discover():
            text = variants.firmware_path(variant).read_text()
            for key in ("variant", "device_name", "friendly_name", "fallback_ap_ssid"):
                with self.subTest(variant=variant, key=key):
                    self.assertRegex(text, rf"(?m)^  {key}:")
            with self.subTest(variant=variant, key="variant equals the file stem"):
                self.assertRegex(text, rf"(?m)^  variant: {re.escape(variant)}$")
            with self.subTest(variant=variant, key="base package"):
                self.assertIn("!include ../packages/base.yaml", text)
            with self.subTest(variant=variant, key="retained state hook"):
                self.assertIn("id: publish_retained_state", text)

    def test_cli_list_is_the_json_array_of_the_discovered_variants(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "list"], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), variants.discover())
        # One line, compact: it is written straight into $GITHUB_OUTPUT for fromJSON().
        self.assertEqual(result.stdout.count("\n"), 1)


class BoardName(unittest.TestCase):
    def board(self, name):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "board", name], capture_output=True, text=True
        )

    def test_slugs_are_accepted(self):
        for name in ("front", "rear-van", "a1", "ci-board", "x-1a", "sixteenchars-abc"[:16]):
            with self.subTest(name=name):
                result = self.board(name)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_non_slugs_are_rejected_before_anything_is_built(self):
        for name in ("", "Front", "1front", "front_", "front--x", "-front", "front-", "a b", "fr\u00f6nt", "esp32/x"):
            with self.subTest(name=name):
                result = self.board(name)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("slug", result.stderr)

    def test_a_name_ending_in_dash_digits_is_rejected(self):
        for name in ("front-1", "rear-16", "a-b-07"):
            with self.subTest(name=name):
                result = self.board(name)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("-<digits>", result.stderr)

    def test_a_name_too_long_for_the_esphome_node_name_is_rejected(self):
        # `renewvan-esp32-<board>` is the node name; ESPHome allows 31 characters.
        self.assertEqual(self.board("a" * 16).returncode, 0)
        result = self.board("a" * 17)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("16", result.stderr)

    def test_validate_board_returns_the_problems(self):
        self.assertEqual(variants.validate_board("front"), [])
        self.assertTrue(variants.validate_board("front-1"))


class Discovery(unittest.TestCase):
    def tree(self, **kwargs):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        make_tree(root, **kwargs)
        return root

    def test_list_is_sorted_and_comes_from_manifests_only(self):
        root = self.tree(
            manifests={"b-board": MANIFEST, "a-board": MANIFEST},
            firmware=["a-board", "b-board", "unlisted"],
        )
        result = run("list", root)
        self.assertEqual(json.loads(result.stdout), ["a-board", "b-board"])

    def test_sound_tree_passes(self):
        root = self.tree(manifests={"demo-board": MANIFEST}, firmware=["demo-board"])
        result = run("check", root)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_driver_field_in_a_manifest_fails_and_is_named(self):
        for driver in ("esp32", "other", "demo-board"):
            with self.subTest(driver=driver):
                root = self.tree(manifests={"demo-board": {**MANIFEST, "driver": driver}}, firmware=["demo-board"])
                result = run("check", root)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("manifests/demo-board.json", result.stderr)
                self.assertIn("'driver'", result.stderr)

    def test_two_variants_pass(self):
        root = self.tree(manifests={"a-board": MANIFEST, "b-board": MANIFEST}, firmware=["a-board", "b-board"])
        self.assertEqual(run("check", root).returncode, 0)

    def test_manifest_without_firmware_fails_and_is_named(self):
        root = self.tree(manifests={"demo-board": MANIFEST}, firmware=[])
        result = run("check", root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("firmware/demo-board.yaml", result.stderr)

    def test_firmware_without_manifest_fails_and_is_named(self):
        root = self.tree(manifests={"demo-board": MANIFEST}, firmware=["demo-board", "orphan"])
        result = run("check", root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("firmware/orphan.yaml", result.stderr)

    def test_the_secrets_symlink_in_firmware_is_not_an_orphan_variant(self):
        root = self.tree(manifests={"demo-board": MANIFEST}, firmware=["demo-board"])
        (root / "firmware" / "secrets.yaml").write_text("wifi_ssid: x\n")
        self.assertEqual(run("check", root).returncode, 0)

    def test_no_manifests_fails(self):
        root = self.tree()
        result = run("check", root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no variants", result.stderr)

    def test_unparseable_manifest_fails_and_is_named(self):
        root = self.tree(firmware=["demo-board"])
        (root / "manifests" / "demo-board.json").write_text("{not json")
        result = run("check", root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("manifests/demo-board.json", result.stderr)

    def test_resolve_manifest_tells_a_name_from_a_path(self):
        self.assertEqual(variants.resolve_manifest("demo-board", Path("/r")), (Path("/r/manifests/demo-board.json"), "demo-board"))
        self.assertEqual(variants.resolve_manifest("manifests/demo-board.json"), (Path("manifests/demo-board.json"), None))
        self.assertEqual(variants.resolve_manifest("x.json"), (Path("x.json"), None))


if __name__ == "__main__":
    unittest.main()

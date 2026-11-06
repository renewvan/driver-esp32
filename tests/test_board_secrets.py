"""Seam: shared secrets + secrets/<board>.yaml -> the one file a board's build reads.

Observed through the script's command line, the way flash.sh calls it, against synthetic trees.
"""

import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "board_secrets.py"

SHARED = 'wifi_ssid: "van"\nota_password: "shared"\nmqtt_username: ""\n'


def make_tree(root, shared=SHARED, boards=None):
    (root / "scripts").mkdir()
    shutil.copy(SCRIPT, root / "scripts" / SCRIPT.name)
    if shared is not None:
        (root / "secrets.yaml").write_text(shared)
    (root / "secrets").mkdir()
    for name, text in (boards or {}).items():
        (root / "secrets" / f"{name}.yaml").write_text(text)


def run(root, *args):
    return subprocess.run(
        [sys.executable, str(root / "scripts" / SCRIPT.name), *args],
        capture_output=True,
        text=True,
        cwd=root,
    )


class BoardSecretsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_board_keys_override_shared_and_shared_fills_the_rest(self):
        make_tree(self.root, boards={"front": '# mine\nota_password: "front-pw"\nmqtt_username: "esp32-front"\n'})
        done = run(self.root, "front", "--write", str(self.root / ".build" / "secrets.yaml"))
        self.assertEqual(done.returncode, 0, done.stderr)
        merged = (self.root / ".build" / "secrets.yaml").read_text()
        self.assertIn('wifi_ssid: "van"', merged)
        self.assertIn('ota_password: "front-pw"', merged)
        self.assertNotIn('"shared"', merged)
        self.assertIn('mqtt_username: "esp32-front"', merged)

    def test_two_boards_hold_their_own_secrets(self):
        make_tree(
            self.root,
            boards={"front": 'ota_password: "a"\n', "rear": 'ota_password: "b"\n'},
        )
        for board, expected in (("front", "a"), ("rear", "b")):
            done = run(self.root, board, "--get", "ota_password")
            self.assertEqual(done.stdout.strip(), expected)

    def test_missing_board_file_is_an_error_naming_the_file(self):
        make_tree(self.root)
        done = run(self.root, "front", "--get", "ota_password")
        self.assertEqual(done.returncode, 2)
        self.assertIn("secrets/front.yaml", done.stderr)

    def test_get_unquotes_and_prints_nothing_when_unset(self):
        make_tree(self.root, boards={"front": 'ota_address: "10.0.0.7"\n'})
        self.assertEqual(run(self.root, "front", "--get", "ota_address").stdout.strip(), "10.0.0.7")
        done = run(self.root, "front", "--get", "nope")
        self.assertEqual((done.returncode, done.stdout), (0, ""))

    def test_written_file_is_owner_only(self):
        make_tree(self.root, boards={"front": 'ota_password: "a"\n'})
        out = self.root / ".build" / "secrets.yaml"
        run(self.root, "front", "--write", str(out))
        self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o600)

    def test_non_flat_line_is_rejected_without_echoing_its_content(self):
        make_tree(self.root, boards={"front": "ota_password: x\n  nested: oops\n"})
        done = run(self.root, "front", "--get", "ota_password")
        self.assertEqual(done.returncode, 2)
        self.assertIn("secrets/front.yaml: line 2", done.stderr)
        self.assertNotIn("oops", done.stderr)

    def test_works_without_a_shared_file(self):
        make_tree(self.root, shared=None, boards={"front": 'ota_password: "a"\n'})
        self.assertEqual(run(self.root, "front", "--get", "ota_password").stdout.strip(), "a")


if __name__ == "__main__":
    unittest.main()

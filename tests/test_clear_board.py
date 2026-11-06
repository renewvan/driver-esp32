"""Seam: a board name + the retained topics on the broker -> exactly the topics to clear.

The broker itself is not exercised (no mosquitto in CI); the selection, parsing and the
command line's refusals are.
"""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "clear_board.py"
sys.path.insert(0, str(ROOT / "scripts"))
import clear_board  # noqa: E402

BUS = [
    "renewvan/esp32-front/info",
    "renewvan/esp32-front/health",
    "renewvan/esp32-front-left/info",
    "renewvan/esp32-rear/health",
    "renewvan/relay/front-01/state",
    "renewvan/relay/front-01/name",
    "renewvan/relay/front-01/driver",
    "renewvan/relay/front-16/state",
    "renewvan/relay/front-left-01/state",
    "renewvan/relay/frontier-01/state",
    "renewvan/relay/rear-01/state",
    "renewvan/other/front-01",
]


class TopicsToClear(unittest.TestCase):
    def test_selects_the_drivers_and_its_relays_only(self):
        self.assertEqual(
            clear_board.topics_to_clear("front", BUS),
            [
                "renewvan/esp32-front/health",
                "renewvan/esp32-front/info",
                "renewvan/relay/front-01/driver",
                "renewvan/relay/front-01/name",
                "renewvan/relay/front-01/state",
                "renewvan/relay/front-16/state",
            ],
        )

    def test_a_hyphenated_name_owns_its_own_relays_only(self):
        self.assertEqual(
            clear_board.topics_to_clear("front-left", BUS),
            ["renewvan/esp32-front-left/info", "renewvan/relay/front-left-01/state"],
        )

    def test_unknown_board_owns_nothing(self):
        self.assertEqual(clear_board.topics_to_clear("ghost", BUS), [])

    def test_parse_retained_keeps_the_payload(self):
        out = 'renewvan/esp32-front/health "online"\nrenewvan/relay/front-01/state true\n'
        self.assertEqual(
            clear_board.parse_retained(out),
            {"renewvan/esp32-front/health": '"online"', "renewvan/relay/front-01/state": "true"},
        )


class CommandLine(unittest.TestCase):
    def test_invalid_board_name_is_refused_before_touching_the_broker(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "Front-01"], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("board name", result.stderr)


if __name__ == "__main__":
    unittest.main()

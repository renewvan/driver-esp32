"""The relay board BLE command format (packages/ble-wake.yaml), against the shared test vectors.

The same vectors are in renewvan/apps `@renewvan/core/boardBle`: the firmware, the bench tool and the
app must sign byte-for-byte alike.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ble_command import describe, signed_command

SECRET = "correct horse battery"
NONCE = "0011223344556677"


class SignedCommandTest(unittest.TestCase):
    def test_hub_wake_vector(self):
        self.assertEqual(
            signed_command(SECRET, NONCE, "01", True),
            f"{NONCE}|01|on|cd08404b0e1cd9ba47dffbfd9b1fc780fbf5e195a53d1d74e1996fba583a5dfe",
        )

    def test_direct_control_vector(self):
        self.assertEqual(
            signed_command(SECRET, NONCE, "03", False),
            f"{NONCE}|03|off|418594107f646b73516495d9d6169677af69429baf3ef0aba5a86639043f9a0a",
        )

    def test_a_nonce_that_is_not_16_lowercase_hex_is_refused(self):
        for nonce in ("", "AABBCCDDEEFF0011", NONCE[:-1], NONCE + "0"):
            with self.subTest(nonce=nonce), self.assertRaises(ValueError):
                signed_command(SECRET, nonce, "01", True)

    def test_a_channel_that_is_not_01_to_16_is_refused(self):
        for nn in ("", "1", "00", "17", "01|", "relay-x8-01"):
            with self.subTest(nn=nn), self.assertRaises(ValueError):
                signed_command(SECRET, NONCE, nn, True)


class DescribeTest(unittest.TestCase):
    def test_hub_power_then_each_direct_control_channel(self):
        self.assertEqual(describe("01|000c", "0005"), "Hub power 01=on, 03=on, 04=off")

    def test_a_board_with_nothing_open(self):
        self.assertEqual(describe("|0000", "0000"), "nothing")


if __name__ == "__main__":
    unittest.main()

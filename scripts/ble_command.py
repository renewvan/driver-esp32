#!/usr/bin/env python3
"""Bench client for a relay board's Bluetooth (packages/ble-wake.yaml): Hub wake and Direct control.

The Renewvan mobile app is the real client (renewvan/hub ADR 0034). This is for the bench and the
README's Acceptance steps: it speaks the same challenge-response contract from a laptop near the board.

usage: ble_command.py <board> info                  the board's channels and states
       ble_command.py <board> <nn> on|off           read a nonce, sign, write, print the result
       ble_command.py <board> --replay <nn> on|off
                                                    send the same signed command twice: the second
                                                    must come back `stale`

The secret is `ble_wake_secret` from secrets/<board>.yaml (never printed). The board is found by its
BLE name, the Driver key `esp32-<board>` cut to 20 characters. Needs `pip install bleak`; the signing
below is pure and tested without it.
"""

import argparse
import asyncio
import hashlib
import hmac
import re
import sys

import board_secrets
import variants

UUID = "7e1a00{}-6f6e-4f3a-9c10-52656e657776"
SERVICE, COMMAND, STATES, RESULT, NONCE, CHANNELS, BOARD = (
    UUID.format(x) for x in ("01", "02", "03", "04", "05", "06", "07")
)
NONCE_TEXT = re.compile(r"^[0-9a-f]{16}$")
CHANNEL = re.compile(r"^(0[1-9]|1[0-6])$")


def signed_command(secret, nonce, nn, on):
    """`<nonce>|<nn>|<on|off>|<mac>`, mac = HMAC-SHA256(secret, the first three fields)."""
    if not NONCE_TEXT.match(nonce):
        raise ValueError("the nonce is not 16 lowercase hex characters")
    if not CHANNEL.match(nn):
        raise ValueError(f"'{nn}' is not a channel number 01..16")
    message = f"{nonce}|{nn}|{'on' if on else 'off'}"
    mac = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return f"{message}|{mac}"


def describe(channels, states):
    """`channels` and `states` as one line: Hub power, then each Direct control channel and its state."""
    hub, _, mask = channels.partition("|")
    on = int(states or "0", 16)
    listed = [nn for nn in range(1, 17) if int(mask or "0", 16) >> (nn - 1) & 1]
    parts = [f"Hub power {hub}={'on' if on >> (int(hub) - 1) & 1 else 'off'}"] if hub else []
    parts += [f"{nn:02d}={'on' if on >> (nn - 1) & 1 else 'off'}" for nn in listed]
    return ", ".join(parts) or "nothing"


async def run(board, nn, on, replay):
    from bleak import BleakClient, BleakScanner

    name = variants.driver_key(board)[:20]
    device = await BleakScanner.find_device_by_name(name, timeout=15)
    if device is None:
        print(f"no board advertising '{name}' in range", file=sys.stderr)
        return 1
    async with BleakClient(device) as client:
        text = lambda b: bytes(b).decode()
        channels = text(await client.read_gatt_char(CHANNELS))
        state = lambda s: print("states:", describe(channels, s))
        print(f"board:   {text(await client.read_gatt_char(BOARD))}  channels: {channels}")
        state(text(await client.read_gatt_char(STATES)))
        if nn is None:
            return 0
        secret = board_secrets.unquote(board_secrets.load(board).get("ble_wake_secret", ""))
        results = asyncio.Queue()
        await client.start_notify(RESULT, lambda _, data: results.put_nowait(text(data)))
        command = signed_command(secret, text(await client.read_gatt_char(NONCE)), nn, on)
        for attempt in range(2 if replay else 1):
            await client.write_gatt_char(COMMAND, command.encode(), response=True)
            result = await asyncio.wait_for(results.get(), timeout=5)
            print(f"result{' (replay)' if attempt else ''}:", result)
        await asyncio.sleep(1)
        state(text(await client.read_gatt_char(STATES)))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("board")
    parser.add_argument("channel", help="a channel number (01..16), or `info`")
    parser.add_argument("action", nargs="?", choices=("on", "off"))
    parser.add_argument("--replay", action="store_true", help="send the same command twice")
    args = parser.parse_args(argv)
    if args.channel != "info" and args.action is None:
        parser.error("a channel needs on or off")
    nn = None if args.channel == "info" else args.channel
    return asyncio.run(run(args.board, nn, args.action == "on", args.replay))


if __name__ == "__main__":
    sys.exit(main())

# driver-esp32-relay

ESPHome YAML config for the 16-channel switched-load relay device (lights, a water pump, a fridge,
a heater, an inverter enable) on an ESP32-WROOM with two chained SN74HC595 shift registers. No
custom firmware. Named for its board, not its source: see
[ADR 0012](https://github.com/renewvan/hub/blob/main/docs/adr/0012-board-named-relay-node.md). The wire
contract is
[ADR 0013](https://github.com/renewvan/hub/blob/main/docs/adr/0013-writable-relay-and-its-wire-contract.md)
and `schema/relay.schema.json` in `renewvan/hub`.

The device key is `esp32-relay`, so it publishes `renewvan/esp32-relay/info` and
`renewvan/esp32-relay/health`. The name `driver-relay` is deliberately left free for a later
Pi-wired device.

## Hardware

ESP32-WROOM and two chained SN74HC595 shift registers driving sixteen relay outputs.

| Signal               | GPIO   | Note                                                                |
| -------------------- | ------ | ------------------------------------------------------------------- |
| Data (`SER`)         | GPIO14 |                                                                     |
| Clock (`SRCLK`)      | GPIO13 |                                                                     |
| Latch (`RCLK`)       | GPIO12 | Strapping pin. **No external pull-up** (GPIO12 high selects 1.8 V). |
| Output enable (`OE`) | GPIO5  | Strapping pin. External pull-up **required**, see below.            |

Channel `relay_01` is shift-register output 0 (`QA` of the register wired to the ESP32 data line)
and `relay_16` is output 15. The chain order is read from the ESPHome source, not from the wiring;
confirm it on the bench.

## Wire contract

Per channel `relay_01` to `relay_16`:

| Topic                          | Retained | Payload                                                     |
| ------------------------------ | -------- | ----------------------------------------------------------- |
| `renewvan/relay/<id>/state`    | yes      | JSON `true` / `false`, published after the output changed   |
| `renewvan/relay/<id>/name`     | yes      | JSON string, only once a name has been set                  |
| `renewvan/relay/<id>/set`      | no       | JSON `true` or `false` only. There is no toggle.            |
| `renewvan/relay/<id>/name/set` | no       | JSON string, 1 to 63 bytes (bytes, so non-ASCII is shorter) |

`state` means the output was commanded and latched. It does **not** mean the load is energised: with
no feedback sensor a stuck relay or a blown fuse is not detected.

A `set` with any other payload is ignored and logged. A `name/set` that is not a JSON string, is
empty, or is over 63 bytes is ignored and logged: the retained `name` is then unchanged, so a consumer
keeps showing the stored name. A consumer must tolerate a `set` or `name/set` being ignored; there is
no ack.

`set` and `name/set` are described here and in the schema description, not as separate schema files.
ESPHome cannot tell a retained command from a live one, so a retained `set` would be applied at every
subscribe: publishers must not retain commands.

### Boot and failure behaviour

- **Every channel is off after any restart** (reset, brownout, update, crash). No state is restored.
  The device alone owns boot state; the hub never re-asserts a desired state.
- **Relays hold their last state while WiFi or the broker is down.** There is no firmware
  timeout-to-off and no local control. A manual override is a hardware concern.
- **A `set` published while the device was offline is not replayed on reconnect** (`clean_session`).
- **No `api:` block**, so ESPHome's fifteen-minute no-client reboot cannot flip a load. **No
  `web_server:`**: it would be an unauthenticated second control path that bypasses this contract.
  The captive-portal fallback adds an OTA upload endpoint that is only reachable on the device's own
  fallback access point.
- **Interlocks live in hardware**, never in this firmware: a pump dry-run cutoff, a heater thermal
  cutoff. The device and the bus do no interlock logic.
- **WiFi power save is off** (`power_save_mode: NONE`). ESPHome's default `LIGHT` made the radio
  sleep between beacons: measured on the board, ping was 55 ms to 3.6 s with 4 of 10 lost, so a
  `set` regularly took longer than the dashboard's 4 second give-up. With it off, ping is about
  7 ms and a `set` latches in about 40 ms.
- **A rename can be lost for up to 60 seconds** after a crash or power cut (ESPHome's flash write
  interval); a rename survives an OTA.

On every MQTT connect, in one chain, the device publishes (1) all sixteen retained states (and the
retained name of every channel that has one), then (2) its retained Device info, then (3) retained
`online`. So a consumer that sees `online` never finds a stale "on" for a load that is off, and info
stays immediately before `online` (ADR 0011). The last-will and shutdown messages publish `offline`;
a will carries one topic, so it cannot clear sixteen state topics: **a consumer treats `state` as
unknown whenever this Device's health is not `online`.**

If a publish is dropped after the connect wait, the previous retained value, possibly stale, stays
until the next reconnect.

## Required: the output-enable pull-up

ESPHome drives nothing before `setup()`, and runs 32 shift cycles at boot, so a glitch on the outputs
exists whatever the restore mode. An **external pull-up on `OE` (GPIO5)** keeps the shift register
outputs high-impedance until firmware drives it. Which pull-up is correct depends on the relay
board's polarity (active-low or active-high); check the board before fitting. Fitting it is an
acceptance step, below.

## Customizing channels

Sixteen channels, one line each in `esp32-relay-driver.yaml` under `packages:`:

```yaml
relay_03: !include { file: pkg/relay-channel.yaml, vars: { ch: relay_03, bit: 2 } }
```

`ch` is the id on the bus and `bit` is the shift-register output 0 to 15. ESPHome rejects a `bit`
above 15, a duplicate `bit` and a duplicate `ch`; it does not notice a skipped `bit`. Labels are not
set here: publish a `name/set` (the dashboard's Settings does this), and the name is stored on the
board. Changing a channel's `ch` orphans its stored name.

The connect chain in `esp32-relay-driver.yaml` lists every `ch` once, so the sixteen states are
published in one ordered chain. Keep the two in step if you add or rename a channel; CI fails on a
mismatch.

## Flashing

```bash
pip install esphome
cp secrets.yaml.example secrets.yaml   # fill in your WiFi/MQTT/OTA values
scripts/flash.sh                       # first flash: connect via USB
```

Always flash with `scripts/flash.sh`, not `esphome run esp32-relay-driver.yaml` directly. The script
stamps the firmware version from your checkout and merges `manifest.json` into the build, and
passes any extra arguments through to `esphome run` (e.g. `scripts/flash.sh --device /dev/ttyUSB0`).

A bare `esphome run esp32-relay-driver.yaml` fails, on purpose: `manifest.json` is the only source of
the device's identity (`device`, `product`, `source`, `publishes`), so the YAML does not declare them.
ESPHome only warns about an undeclared substitution and would otherwise use the literal `${device}` as
an MQTT topic.

Subsequent updates can go over WiFi (run the script again once the device has joined your network)
using the OTA password in `secrets.yaml`.

## Version stamp

The firmware version is `git describe --tags --always --dirty` of the checkout you flash from, and
the flash script **always** passes it to the build:

| Checkout                             | Stamped version     |
| ------------------------------------ | ------------------- |
| exactly on tag `v0.2.0`              | `v0.2.0`            |
| 3 commits past `v0.2.0`              | `v0.2.0-3-gabc1234` |
| no tags at all                       | `abc1234`           |
| uncommitted changes to tracked files | `...-dirty`         |

An untagged tree still flashes, with a hash version; the script never refuses.
`scripts/flash.sh --print-version` prints the stamp without building.

The firmware itself defaults the version to `dev` (`substitutions.version` in
`esp32-relay-driver.yaml`). **Keep that default.** ESPHome only warns about an undeclared substitution
and then ships the literal `${version}` as the version, so without a default a missing build argument
would silently publish a placeholder. CI additionally fails if the stamp is lost.

**Releases are git tags.** There is no `version` file. Start a release from **Actions → Release →
Run workflow**, or `gh workflow run release.yml -f bump=minor`: one run works out the next version
from the latest `v*` tag, tags `main`, creates the GitHub release, and compiles the tagged tree as a
gate. Then flash from that tag with `scripts/flash.sh`. **No binary is attached**: WiFi, MQTT and the
OTA password are compiled in from `secrets.yaml`, so a CI-built binary contains placeholders and
cannot be flashed onto a van (and would publish a known OTA password). The process is shared by every
renewvan repo and lives in `hub` (`hub/docs/adr/0015-one-release-process-via-reusable-workflows.md`).

## Device info and health

The device appears on the dashboard's Device page like every other Device. The static fields live in
`manifest.json`, the single source. It must not contain `version` or `board_serial`. Optional fields
(`manufacturer`, `homepage`) are omitted from the info when empty.
`scripts/manifest_substitutions.py` turns it into the build's substitutions, for both the flash
script and CI. `board_serial` is the board's MAC in the form `AA:BB:CC:DD:EE:FF`, so it can be
compared with the label on the board.

`ip` is the IPv4 address DHCP gave the board, so the dashboard can show where to reach it (for the
OTA update, or to find it on the router). It is read when the info is published, so it is as fresh
as the board's last (re)connect to the broker, and it is omitted, never `0.0.0.0`, while the board
has no address. Reserve the address on your router if you want it to stay put.

## Acceptance (on the board, before it goes in the van)

CI validates the YAML and the version stamp. Nothing in CI can exercise the board, so these are
manual:

1. **Bench test across 20 or more resets with the `OE` pull-up fitted:** no channel clicks on
   during boot. Repeat across an OTA update and a pulled power lead.
2. Confirm there is **no fifteen-minute reboot** with no client connected.
3. Watch `mosquitto_sub -h <broker> -v 'renewvan/#'` while the board boots: the sixteen `state`
   topics, then `renewvan/esp32-relay/info`, then `renewvan/esp32-relay/health` = `online`.
   The info carries `"ip"`: confirm it is the address your router's DHCP table shows for the
   board, and that it also reads on the dashboard under Settings › Devices › ESP32 relay.
4. `mosquitto_pub -t renewvan/relay/relay_01/set -m true` switches channel 1 and `state` becomes
   `true` afterwards; `-m false` switches it off.
5. Publish `'"Water pump"'` to `renewvan/relay/relay_03/name/set` and confirm the retained `name`;
   power-cycle after 60 seconds and confirm it persists.
6. Unplug the board's network: `health` becomes `offline`, the retained `info` stays, and the relays
   hold their state.

## CI

`.github/workflows/validate.yml` runs the script tests, then builds `esp32-relay-driver.yaml` with
`esphome/build-action` (pinned by commit SHA, with ESPHome pinned) against the placeholder
`secrets.yaml.example`. It passes a CI version (`ci-<short sha>`) and the manifest as substitutions,
then fails if:

- the action's reported project version differs from the CI value, or
- the resolved configuration (`esphome config`) still contains an unexpanded `$placeholder`, or
- the connect chain and the `packages:` list name different channels.

The placeholder check exists because ESPHome exits 0 on an undeclared substitution.

There is no versioned image to publish: the device is flashed once per board from the owner's
checkout of a release tag, and `hub`'s deployment manifest references this repo's flash instructions.

> **Two different `manifest.json` files.** The build action also writes its own `manifest.json` (an
> ESP Web Tools manifest) into its output folder, named after the device. That is unrelated to the
> `manifest.json` at this repo's root, which describes the Device. The root one is the source of the
> Device info; the action's is a build artifact and is not used here.

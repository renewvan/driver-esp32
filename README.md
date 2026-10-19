# node-relay

ESPHome YAML config for the 8-channel switched-load relay node (lights,
fan, USB outlets, etc.) — no custom firmware. Per
`hub/.scratch/renewvan-hub-v0-build/issues/03-esp32-relay-node-config.md`
and the interface decision in
`hub/.scratch/renewvan-hub-v0/issues/03-esp32-relay-node-driver-interface.md`.

## Hardware

Bare ESP32 dev board + a separate 8-channel relay board wired to ESP32
GPIO (not an integrated relay+MCU board — keeps switching decoupled
from the hub's own lifecycle). Each channel also has a physical
momentary/toggle button wired to its own GPIO input (pulled up
internally, switched to GND when pressed).

| Channel | Default id        | Relay GPIO | Button GPIO |
| ------- | ----------------- | ---------- | ----------- |
| 1       | `lights_ceiling`  | GPIO4      | GPIO14      |
| 2       | `lights_reading`  | GPIO5      | GPIO15      |
| 3       | `lights_kitchen`  | GPIO13     | GPIO21      |
| 4       | `lights_bathroom` | GPIO16     | GPIO22      |
| 5       | `lights_awning`   | GPIO17     | GPIO25      |
| 6       | `fan_vent`        | GPIO18     | GPIO26      |
| 7       | `usb_outlets`     | GPIO19     | GPIO27      |
| 8       | `aux_1`           | GPIO23     | GPIO32      |

## Switching path — fully local, no MQTT command topic

Each channel pairs a `binary_sensor` (button) with a `switch` (relay
output): `on_press` on the button directly calls `switch.toggle` on the
paired relay, entirely on-device. This automation runs regardless of
WiFi/MQTT connectivity — physical buttons keep working even with the
Pi, dashboard, or broker down. There is no MQTT command topic for
relays in v0 (read-only dashboard, no tap-to-toggle); nothing subscribes
to control a relay remotely.

## Renewvan bus MQTT interface

Every relay is `internal: true` (no Home Assistant/ESPHome-API
frontend, no discovery — `mqtt: { discovery: false }` too). Its only
MQTT presence is an explicit `mqtt.publish` in `on_turn_on`/
`on_turn_off`, which publishes retained `"true"`/`"false"` directly to
`renewvan/relay/<id>/state` on every state change — matching the v0.1
`relay.schema.json` boolean `state` field.

(ESPHome's built-in `payload_on`/`payload_off` switch options — as
described in the ticket 03 decision doc — turned out not to exist on
ESPHome's actual `MQTT Component` base config; only `state_topic`/
`command_topic` do, and those still emit ESPHome's native `"ON"`/`"OFF"`
strings, not `"true"`/`"false"`. Explicit `mqtt.publish` actions produce
the exact same wire behavior the ticket specifies — retained `"true"`/
`"false"` on `renewvan/relay/<id>/state` on every change — via a documented
ESPHome mechanism instead of a nonexistent config key.)

## Customizing channels

The 8 channel labels above (`lights_ceiling`, etc.) are placeholders —
rename them to match your actual van's loads. For each channel, update
all three of: the `switch.id`, its `mqtt.publish` topic string (both
`on_turn_on` and `on_turn_off`), and the `switch.toggle:` target in the
paired button's `on_press`. GPIO pin assignments are physical wiring —
change only if your board is wired differently.

## Flashing

```bash
pip install esphome
cp secrets.yaml.example secrets.yaml   # fill in your WiFi/MQTT/OTA values
scripts/flash.sh                       # first flash: connect via USB
```

Always flash with `scripts/flash.sh`, not `esphome run relay-node.yaml` directly. The script
stamps the firmware version from your checkout and merges `manifest.json` into the build, and
passes any extra arguments through to `esphome run` (e.g. `scripts/flash.sh --device /dev/ttyUSB0`).

A bare `esphome run relay-node.yaml` fails, on purpose: `manifest.json` is the only source of
the node's identity (`node`, `product`, `source`, `publishes`), so `relay-node.yaml` does not
declare them. ESPHome only warns about an undeclared substitution and would otherwise use the
literal `${node}` as an MQTT topic.

Subsequent updates can go over WiFi (run the script again once the node has joined your
network) using the OTA password in `secrets.yaml`.

## Version stamp

The firmware version is `git describe --tags --always --dirty` of the checkout you flash from,
and the flash script **always** passes it to the build:

| Checkout                             | Stamped version     |
| ------------------------------------ | ------------------- |
| exactly on tag `v0.2.0`              | `v0.2.0`            |
| 3 commits past `v0.2.0`              | `v0.2.0-3-gabc1234` |
| no tags at all                       | `abc1234`           |
| uncommitted changes to tracked files | `...-dirty`         |

An untagged tree still flashes, with a hash version; the script never refuses. Editing channel
labels does not require tagging first. `scripts/flash.sh --print-version` prints the stamp
without building.

The firmware itself defaults the version to `dev` (`substitutions.version` in
`relay-node.yaml`). **Keep that default.** ESPHome only warns about an undeclared substitution
and then ships the literal `${version}` as the version, so without a default a missing build
argument would silently publish a placeholder. CI additionally fails if the stamp is lost.

**Releases are git tags.** There is no `version` file and no release workflow; tag the commit
(`git tag v0.2.0`) and flash from it. There is also no attached binary: a CI-built binary
contains placeholder secrets and cannot be flashed onto a van.

## Node info and health

The relay appears on the dashboard's Device page like every other Node. On every MQTT connect
it publishes, in this order:

1. retained Node info to `renewvan/relay/info` (JSON: `node`, `product`, `source`, `publishes`,
   optional `manufacturer` and `homepage`, `version`, and `host_serial`)
2. retained `online` to `renewvan/relay/health`

The last-will and shutdown messages publish `offline` to the health topic; the info stays
retained, so the dashboard can show "offline, last seen vX". `host_serial` is the board's MAC in
the form `AA:BB:CC:DD:EE:FF`, so it can be compared with the label on the board.

The static fields live in `manifest.json`, the single source. It must not contain `version` or
`host_serial`. Optional fields (`manufacturer`, `homepage`) are omitted from the info when empty.
`scripts/manifest_substitutions.py` turns it into the build's substitutions, for both the flash
script and CI.

The built-in MQTT birth message is disabled, and the connect handler waits for the client to be
connected before publishing (a publish made earlier is silently dropped). If a publish is
dropped after that wait, the previous retained info, possibly a stale version, stays until the
next reconnect.

## Verifying

1. With the ESP32 flashed and powered, physically disconnect it from
   WiFi/the renewvan bus (or just don't configure `wifi_ssid` yet) — confirm
   each physical button still toggles its relay.
2. Reconnect to the renewvan bus, press a button, and confirm
   `renewvan/relay/<id>/state` publishes `"true"`/`"false"` (retained) —
   e.g. `mosquitto_sub -h <broker> -t 'renewvan/relay/#' -v`.
3. Watch `mosquitto_sub -h <broker> -v 'renewvan/relay/#'` while the board boots: `info` must
   appear **before** `online`, with the MAC in `AA:BB:CC:DD:EE:FF` form.
4. Unplug the board's network: `renewvan/relay/health` becomes `offline` and the retained `info`
   stays.

## CI

`.github/workflows/validate.yml` runs the script tests, then builds `relay-node.yaml` with
`esphome/build-action` (pinned by commit SHA, with ESPHome pinned) against the placeholder
`secrets.yaml.example`. It passes a CI version (`ci-<short sha>`) and the manifest as
substitutions, then fails if:

- the action's reported project version differs from the CI value, or
- the resolved configuration (`esphome config`) still contains an unexpanded `$placeholder`.

The second check exists because ESPHome exits 0 on an undeclared substitution.

There is no release workflow and no versioned image to publish: the relay is flashed once per
node from the owner's checkout, and `hub`'s deployment manifest references this repo's flash
instructions.

> **Two different `manifest.json` files.** The build action also writes its own `manifest.json`
> (an ESP Web Tools manifest) into its output folder, named after the device. That is unrelated
> to the `manifest.json` at this repo's root, which describes the Node. The root one is the
> source of the Node info; the action's is a build artifact and is not used here.

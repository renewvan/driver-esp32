# driver-esp32

Every ESP32 firmware the Renewvan van ships, in one repo. Each firmware is a **variant**: ESPHome YAML (no
custom firmware) for one kind of board, flashed once per physical board. Today there is one:

| Variant           | Board                                                      | Publishes |
| ----------------- | ---------------------------------------------------------- | --------- |
| `esp32-16x-relay` | ESP32-WROOM + two chained SN74HC595, sixteen relay outputs | `relay`   |

Variants are named for their board, not their source: see
[ADR 0012](https://github.com/renewvan/hub/blob/main/docs/adr/0012-board-named-relay-node.md). The wire contract of
the relay is
[ADR 0013](https://github.com/renewvan/hub/blob/main/docs/adr/0013-writable-relay-and-its-wire-contract.md)
and `schema/relay.schema.json` in `renewvan/hub`.

## What a variant is, and the Driver key

A variant is **one firmware image for one kind of board**. Its name is the stem shared by its
`firmware/<variant>.yaml` and `manifests/<variant>.json`, and CI enforces that every firmware has its manifest
and every manifest its firmware. It also names the ESPHome node (`renewvan-<variant>`) and project
(`renewvan.driver-esp32-<variant>`).

The **Driver key is repo-wide: `esp32`**, the repo name minus `driver-`. Every manifest says `"driver": "esp32"`
(CI enforces it), and every variant publishes `renewvan/esp32/info` and `renewvan/esp32/health`, and its entities'
retained `driver` is `"esp32"`. The variant is not on the wire. The consequences, accepted by the owner while
there is a single board:

- **One retained info and one health topic for the whole Driver.** Every board shares the one last-will on
  `renewvan/esp32/health`, so one board dying marks the whole Driver offline, and a board connecting after another
  overwrites that board's retained info.
- **A second kind of board needs the key reconsidered** (a key per variant, or a repo split) before it is
  flashed: today a second variant would clash with the first on these topics.
- **Two identical boards cannot run side by side**, for the same reason, and because the relay's entity ids
  (`relay_01` to `relay_16`, topics `renewvan/relay/<id>/...`) are fixed by the firmware: a second relay board would
  publish over the first board's retained state. There is no build-time override for either; it is not implemented.

The name `driver-relay` is deliberately left free for a later Pi-wired driver.

## Layout

```
firmware/<variant>.yaml     the ESPHome entrypoint of one variant: board, hardware, entities
manifests/<variant>.json    its static Driver fields (the single source, see "Driver info and health")
packages/base.yaml          shared by every variant: WiFi, OTA, logger, captive portal, MQTT, Driver info/health
packages/relay-channel.yaml one relay channel, included once per channel by the relay variant
scripts/                    flash.sh, manifest_substitutions.py, variants.py, and the CI guards
firmware/secrets.yaml       a symlink to ../secrets.yaml (ESPHome looks secrets up next to the entrypoint)
```

`manifests/` is the list of variants: CI, the release build and every script derive them from it
(`python3 scripts/variants.py list`; `variants.py check` verifies every manifest has `driver` equal to the
repo-wide key `esp32` and its `firmware/<variant>.yaml`, and every firmware has its manifest).

`packages/base.yaml` holds the van-bus connect chain, in this order on every MQTT connect: (1) the variant's
retained entity state, (2) retained Driver info, (3) retained `online`. Step (1) is the variant's
`publish_retained_state` script, so the order is one chain and not several `on_connect` entries (whose order
is undefined). A variant provides `variant`, `device_name`, `friendly_name` and `fallback_ap_ssid` substitutions and that
script; the Driver fields come from its manifest.

## Adding a variant

1. `manifests/<variant>.json`: `driver` (always `esp32`, the repo-wide key: read "What a variant is, and the Driver key" first), `product`, `source`, `publishes`, and
   optionally `manufacturer` and `homepage`. No `version` or `board_serial`.
2. `firmware/<variant>.yaml`: the `variant` (equal to `<variant>`), `device_name`, `friendly_name` and `fallback_ap_ssid` substitutions, the
   `esp32:` board, its hardware and entities, a `publish_retained_state` script (publishing each entity's
   retained `driver`, state and name; an entity-less variant leaves it with no actions), and
   `packages: base: !include ../packages/base.yaml`. Copy `firmware/esp32-16x-relay.yaml` as the model.
3. `packages/<name>.yaml` for anything repeated within the variant (the relay's `relay-channel.yaml` is the
   example); anything a second variant also needs belongs in `packages/base.yaml` instead.
4. Nothing else: `scripts/flash.sh <variant>`, the validate matrix and the release build find it through
   `manifests/`. A per-variant guard (like `scripts/check_relay_channels.py`) is added to
   `.github/workflows/validate.yml` with an `if: matrix.variant == '<variant>'`.

## Building and flashing

```bash
pip install esphome
cp secrets.yaml.example secrets.yaml   # fill in your WiFi/MQTT/OTA values
scripts/flash.sh esp32-16x-relay       # first flash: connect via USB
scripts/flash.sh --list                # the variants
```

Always flash with `scripts/flash.sh <variant>`, not `esphome run firmware/<variant>.yaml` directly. The
script stamps the firmware version from your checkout and merges `manifests/<variant>.json` into the build, and
passes any extra arguments through to `esphome run` (e.g. `scripts/flash.sh esp32-16x-relay --device /dev/ttyUSB0`).

A bare `esphome run firmware/<variant>.yaml` fails, on purpose: the manifest is the only source of the
Driver's identity (`driver`, `product`, `source`, `publishes`), so the YAML does not declare them. ESPHome only
warns about an undeclared substitution and would otherwise use the literal `${driver}` as an MQTT topic.

Subsequent updates can go over WiFi (run the script again once the device has joined your network)
using the OTA password in `secrets.yaml`.

### Flashing with Claude Code

The `flash-esp32` skill (`skills/flash-esp32/SKILL.md` in `renewvan/skills`) walks through the same steps
interactively: it finds the variant, asks for the serial port or OTA address, fills `secrets.yaml` from
`secrets.yaml.example` (it never prints the contents), runs the pre-flight checks, flashes with
`scripts/flash.sh`, and verifies the board on the MQTT bus. Run it from this checkout and ask Claude to
"flash the esp32". It drives `scripts/flash.sh` and does not replace it; if the skill and this README disagree,
this README wins.

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

**The version is shared by every variant.** There is one repo tag, and a release stamps that same tag into
every variant, so a change to one variant's firmware also moves the version of the others. This is an accepted
tradeoff for one repo and one release process; a variant's Driver info still says exactly which tag it was
built from.

The firmware itself defaults the version to `dev` (`substitutions.version` in `packages/base.yaml`).
**Keep that default.** ESPHome only warns about an undeclared substitution and then ships the literal
`${version}` as the version, so without a default a missing build argument would silently publish a
placeholder. CI additionally fails if the stamp is lost.

**Releases are git tags.** There is no `version` file. Start a release from **Actions → Release →
Run workflow**, or `gh workflow run release.yml -f bump=minor`: one run works out the next version
from the latest `v*` tag, tags `main`, creates the GitHub release, and compiles the tagged tree (every
variant) as a gate. Then flash from that tag with `scripts/flash.sh <variant>`. **No binary is attached**: WiFi,
MQTT and the OTA password are compiled in from `secrets.yaml`, so a CI-built binary contains placeholders and
cannot be flashed onto a van (and would publish a known OTA password). The process is shared by every
renewvan repo and lives in `hub` (`hub/docs/adr/0015-one-release-process-via-reusable-workflows.md`).

## Driver info and health

The `esp32` Driver appears on the dashboard's Driver page like every other Driver. The static fields live in
`manifests/<variant>.json`, the single source. It must not contain `version` or `board_serial`. Optional fields
(`manufacturer`, `homepage`) are omitted from the info when empty.
`scripts/manifest_substitutions.py <variant>` turns it into the build's substitutions, for both the flash
script and CI. `board_serial` is the board's MAC in the form `AA:BB:CC:DD:EE:FF`, so it can be
compared with the label on the board.

`ip` is the IPv4 address DHCP gave the board, so the dashboard can show where to reach it (for the
OTA update, or to find it on the router). It is read when the info is published, so it is as fresh
as the board's last (re)connect to the broker, and it is omitted, never `0.0.0.0`, while the board
has no address. Reserve the address on your router if you want it to stay put.

## CI

`.github/workflows/validate.yml` runs the script tests and `variants.py check`, then, **for every variant
found under `manifests/`** (a matrix built from the directory), builds `firmware/<variant>.yaml` with
`esphome/build-action` (pinned by commit SHA, with ESPHome pinned) against the placeholder
`secrets.yaml.example`. It passes a CI version (`ci-<short sha>`) and the variant's manifest as substitutions,
then fails if:

- the action's reported project version differs from the CI value, or
- the resolved configuration (`esphome config`) still contains an unexpanded `$placeholder`, or
- the resolved configuration is not the variant's (project name `renewvan.driver-esp32-<variant>`, node name `renewvan-<variant>`) or does not use the repo's health topic `renewvan/esp32/health`, or
- for the relay, the `publish_retained_state` script and the `packages:` list name different channels.

The placeholder check exists because ESPHome exits 0 on an undeclared substitution.

There is no versioned image to publish: each board is flashed once from the owner's checkout of a release tag,
and `hub`'s deployment manifest references this repo's flash instructions.

> **Two different `manifest.json` files.** The build action also writes its own `manifest.json` (an
> ESP Web Tools manifest) into its output folder, named after the device. That is unrelated to
> `manifests/<variant>.json`, which describes the Driver. The latter is the source of the Driver info; the
> action's is a build artifact and is not used here.

## Variant: esp32-16x-relay

16-channel switched-load relay driver (lights, a water pump, a fridge, a heater, an inverter enable) on an
ESP32-WROOM with two chained SN74HC595 shift registers. Entrypoint `firmware/esp32-16x-relay.yaml`, manifest
`manifests/esp32-16x-relay.json`, Driver key `esp32`: it publishes `renewvan/esp32/info` and
`renewvan/esp32/health`.

### Hardware

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

### Wire contract

Per channel `relay_01` to `relay_16`:

| Topic                          | Retained | Payload                                                     |
| ------------------------------ | -------- | ----------------------------------------------------------- |
| `renewvan/relay/<id>/state`    | yes      | JSON `true` / `false`, published after the output changed   |
| `renewvan/relay/<id>/name`     | yes      | JSON string, only once a name has been set                  |
| `renewvan/relay/<id>/driver`   | yes      | JSON string `"esp32"`, the owning Driver, always            |
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

#### Boot and failure behaviour

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

On every MQTT connect, in one chain, the driver publishes (1) all sixteen retained states (with each channel's
retained `driver`, and the retained name of every channel that has one), then (2) its retained Driver info, then (3) retained
`online`. So a consumer that sees `online` never finds a stale "on" for a load that is off, and info
stays immediately before `online` (ADR 0011). The last-will and shutdown messages publish `offline`;
a will carries one topic, so it cannot clear sixteen state topics: **a consumer treats `state` as
unknown whenever this Driver's health is not `online`.**

If a publish is dropped after the connect wait, the previous retained value, possibly stale, stays
until the next reconnect.

### Required: the output-enable pull-up

ESPHome drives nothing before `setup()`, and runs 32 shift cycles at boot, so a glitch on the outputs
exists whatever the restore mode. An **external pull-up on `OE` (GPIO5)** keeps the shift register
outputs high-impedance until firmware drives it. Which pull-up is correct depends on the relay
board's polarity (active-low or active-high); check the board before fitting. Fitting it is an
acceptance step, below.

### Customizing channels

Sixteen channels, one line each in `firmware/esp32-16x-relay.yaml` under `packages:`:

```yaml
relay_03: !include { file: ../packages/relay-channel.yaml, vars: { ch: relay_03, bit: 2 } }
```

`ch` is the id on the bus and `bit` is the shift-register output 0 to 15. ESPHome rejects a `bit`
above 15, a duplicate `bit` and a duplicate `ch`; it does not notice a skipped `bit`. Labels are not
set here: publish a `name/set` (the dashboard's Settings does this), and the name is stored on the
board. Changing a channel's `ch` orphans its stored name.

The `publish_retained_state` script in `firmware/esp32-16x-relay.yaml` lists every `ch` once. It is step (1)
of the one connect chain in `packages/base.yaml`, so the sixteen states are published before the Driver info and
`online`. Keep the two lists in step if you add or rename a channel; `scripts/check_relay_channels.py` (run by CI)
fails on a mismatch.

### Acceptance (on the board, before it goes in the van)

CI validates the YAML and the version stamp. Nothing in CI can exercise the board, so these are
manual:

1. **Bench test across 20 or more resets with the `OE` pull-up fitted:** no channel clicks on
   during boot. Repeat across an OTA update and a pulled power lead.
2. Confirm there is **no fifteen-minute reboot** with no client connected.
3. Watch `mosquitto_sub -h <broker> -v 'renewvan/#'` while the board boots: the sixteen `state`
   topics (each with its `driver` = `"esp32"`), then `renewvan/esp32/info`, then `renewvan/esp32/health` = `online`.
   The info carries `"ip"`: confirm it is the address your router's DHCP table shows for the
   board, and that it also reads on the dashboard under Settings › Drivers › ESP32 16x relay.
4. `mosquitto_pub -t renewvan/relay/relay_01/set -m true` switches channel 1 and `state` becomes
   `true` afterwards; `-m false` switches it off.
5. Publish `'"Water pump"'` to `renewvan/relay/relay_03/name/set` and confirm the retained `name`;
   power-cycle after 60 seconds and confirm it persists.
6. Unplug the board's network: `health` becomes `offline`, the retained `info` stays, and the relays
   hold their state.

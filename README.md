# driver-esp32

Every ESP32 firmware the Renewvan van ships, in one repo. Each firmware is a **variant**: ESPHome YAML (no
custom firmware) for one kind of board, flashed once per physical board. Today there are two. A van can have any number of boards of either variant, each named when flashed and each its own Driver on the bus:

| Variant           | Board                                                      | Publishes |
| ----------------- | ---------------------------------------------------------- | --------- |
| `esp32-16x-relay` | ESP32-WROOM + two chained SN74HC595, sixteen relay outputs | `relay`   |
| `esp32-8x-relay`  | LC-Relay-ESP-8R-D5 (ESP32-E), eight relays on direct GPIOs | `relay`   |

Variants are named for their board, not their source: see
[ADR 0012](https://github.com/renewvan/hub/blob/main/docs/adr/0012-board-named-relay-node.md). The wire contract of
the relay is
[ADR 0013](https://github.com/renewvan/hub/blob/main/docs/adr/0013-writable-relay-and-its-wire-contract.md)
and `schema/relay.schema.json` in `renewvan/hub`.

## What a variant, a board and a Driver are

A **variant** is **one firmware image for one kind of board**. Its name is the stem shared by its
`firmware/<variant>.yaml` and `manifests/<variant>.json`, and CI enforces that every firmware has its manifest
and every manifest its firmware. It names the ESPHome project (`renewvan.driver-esp32-<variant>`) and is never a
Driver. A **board** is one physical unit running a variant, named by its owner once, when flashing it
(`scripts/flash.sh <variant> --board <name>`). A van can have any number of boards, including several of the same
variant (see `GLOSSARY.md`).

**Every board is its own Driver, with the key `esp32-<name>`.** The name is compiled into the firmware, so
reflashing with the same name is the same Driver. Everything on the bus derives from it:

- `renewvan/esp32-<name>/info` and `renewvan/esp32-<name>/health`, retained, with the board's own last-will: a dead
  board marks only its own Driver `offline`. `info` carries an optional, informational `variant` (consumers must
  not branch on it).
- relay ids `<name>-<nn>` (`front-01` to `front-16`, topics `renewvan/relay/<id>/...`), `<nn>` zero-padded and
  positional, and each id's retained `driver` is `"esp32-<name>"`. Two boards cannot share a name, so they cannot
  share an id.
- the ESPHome node name `renewvan-esp32-<name>` (hostname for OTA) and the recovery access point `Renewvan esp32-<name>`.

**The name is validated before anything is built** (`scripts/variants.py board <name>`, called by `flash.sh`): a
slug (lowercase letters and digits, starting with a letter, words joined by single hyphens), at most 16 characters
(the node name is limited to 31), and it must not end in `-<digits>`, so a relay id is never ambiguous with a board
name. Renaming a board is a new Driver: the old retained `renewvan/esp32-<old>/*` and `renewvan/relay/<old>-<nn>/*`
topics must be cleared (see "Removing or renaming a board"). Nothing checks that a name is unused: two boards flashed with
the same name will overwrite each other's retained state.

The name `driver-relay` is deliberately left free for a later Pi-wired driver.

## Layout

```
firmware/<variant>.yaml     the ESPHome entrypoint of one variant: board, hardware, entities
manifests/<variant>.json    the static fields of the kind (the single source, see "Driver info and health"); no `driver`
packages/base.yaml          shared by every variant: WiFi, OTA, logger, captive portal, MQTT, Driver info/health
packages/relay-channel.yaml one relay channel, included once per channel by the relay variant
scripts/                    flash.sh, clear_board.py, manifest_substitutions.py, variants.py, and the CI guards
firmware/secrets.yaml       a symlink to ../secrets.yaml, for plain `esphome config`; flash.sh builds from .build/<board>/ instead
secrets/<board>.yaml        one board's own secrets (gitignored), laid over the shared secrets.yaml by scripts/board_secrets.py
```

`manifests/` is the list of variants: CI, the release build and every script derive them from it
(`python3 scripts/variants.py list`; `variants.py check` verifies every manifest has its `firmware/<variant>.yaml`
and no `driver` key, and every firmware has its manifest).

`packages/base.yaml` holds the van-bus connect chain, in this order on every MQTT connect: (1) the variant's
retained entity state, (2) retained Driver info, (3) retained `online`. Step (1) is the variant's
`publish_retained_state` script, so the order is one chain and not several `on_connect` entries (whose order
is undefined). A variant provides `variant`, `device_name` (`renewvan-esp32-${board}`), `friendly_name` and
`fallback_ap_ssid` substitutions and that script; `board` and `driver` come from `flash.sh --board`, the other Driver
fields from its manifest.

## Adding a variant

1. `manifests/<variant>.json`: `product`, `source`, `publishes`, and optionally `manufacturer` and `homepage`. No
   `driver` (the key is `esp32-<board>`, composed at flash time), `version` or `board_serial`.
2. `firmware/<variant>.yaml`: the `variant` (equal to `<variant>`), `device_name` (`renewvan-esp32-${board}`), `friendly_name` and `fallback_ap_ssid` substitutions, the
   `esp32:` board, its hardware and entities, a `publish_retained_state` script (publishing each entity's
   retained `driver` (`${driver}`), state and name, under the bus id `${board}-<nn>`; an entity-less variant leaves it with no actions), and
   `packages: base: !include ../packages/base.yaml`. Copy `firmware/esp32-16x-relay.yaml` as the model.
3. `packages/<name>.yaml` for anything repeated within the variant (the relay's `relay-channel.yaml` is the
   example); anything a second variant also needs belongs in `packages/base.yaml` instead.
4. Nothing else: `scripts/flash.sh <variant>`, the validate matrix and the release build find it through
   `manifests/`. A per-variant guard (like `scripts/check_relay_channels.py`) is added to
   `.github/workflows/validate.yml` with an `if: matrix.variant == '<variant>'`.

## Building and flashing

```bash
pip install esphome
cp secrets.yaml.example secrets.yaml           # once: the values every board shares (WiFi, broker address)
mkdir -p secrets
cp secrets.yaml.example secrets/front.yaml     # per board: its own account, OTA password, API key
scripts/flash.sh esp32-16x-relay --board front # first flash: connect via USB
scripts/flash.sh --list                        # the variants
```

### Secrets are per board

`secrets.yaml` (repo root, gitignored) holds what every board of the van shares: `wifi_ssid`, `wifi_password`,
`wifi_ap_fallback_password`, `mqtt_broker`, `mqtt_port`. `secrets/<name>.yaml` (gitignored) holds what is that
board's own, and its keys win over the shared file:

| Key                              | Value                                                                                                             |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `mqtt_username`, `mqtt_password` | the board's broker account `esp32-<name>` and its password, the hub's `MQTT_ESP32_<NAME>_PASSWORD` (hub ADR 0027) |
| `ota_password`                   | its own, so updating one board needs no other board's password                                                    |
| `api_encryption_key`             | its own (`esphome secrets api_encryption_key`)                                                                    |
| `ota_address`                    | optional: the board's address, used as the OTA target when `--device` is not given                                |

Both files are flat `key: value` lines (`secrets.yaml.example` lists every key). `flash.sh` merges them with
`scripts/board_secrets.py` into `.build/<name>/`, a gitignored staging copy of the build that only that board's
build reads, so a board can never be built with another board's credentials. A board with no `secrets/<name>.yaml`
is refused with the file to create.

### A second board, and updating a board

```bash
cp secrets.yaml.example secrets/rear.yaml      # fill in rear's own account, OTA password, API key
scripts/flash.sh esp32-8x-relay --board rear --device /dev/ttyUSB0   # first flash of rear: USB
scripts/flash.sh esp32-16x-relay --board front # later: OTA to front only; rear is untouched
```

An update goes over WiFi: `flash.sh <variant> --board <name>` with the same name targets that board, by its
`ota_address` if its secrets set one, otherwise by its hostname `renewvan-esp32-<name>`, and authenticates with
that board's `ota_password`. Another board of the same variant is never reached. `--device <port|address>`
overrides the target. Re-flashing with the same name keeps the same Driver (and the same retained topics).

Optional and best-effort: before a first flash, `mosquitto_sub -h <broker> -C 1 -W 3 -t 'renewvan/esp32-<name>/info'`
(with a credential that may read) prints a line when that name is already retained on the broker, i.e. the name is
taken by another board. `flash.sh` does not do this itself.

### Removing or renaming a board

A removed board leaves its retained topics on the broker, so it keeps showing as a Driver (`offline`). A renamed
board is a new Driver and leaves the old name behind the same way. After powering the old board off (or
reflashing it under its new name), clear the old name:

```bash
scripts/clear_board.py <old-name> --dry-run -- -h <broker> -u <user> -P <password>   # list what would go
scripts/clear_board.py <old-name> -- -h <broker> -u <user> -P <password>             # clear it
```

It finds what is retained for the name, publishes an empty retained message to each topic, and checks that nothing is
left. It clears `renewvan/esp32-<old>/info`, `renewvan/esp32-<old>/health` and every
`renewvan/relay/<old>-<nn>/*` (`state`, `name`, `driver`), and nothing of any other board. It refuses while the old
board's health is still `online` (the board would republish at once) unless `--force`. Everything after `--` goes to
`mosquitto_sub`/`mosquitto_pub` (host, port, credentials, TLS); the credential must be allowed to publish those topics
(the hub's admin account, or the board's own). With its info and health gone, the Driver has nothing left to show on the bus.

Always flash with `scripts/flash.sh <variant>`, not `esphome run firmware/<variant>.yaml` directly. The
script stamps the firmware version from your checkout, compiles in the board name (`--board <name>` is required and
validated, see above) and merges `manifests/<variant>.json` into the build, and passes any other arguments through
to `esphome run` (e.g. `scripts/flash.sh esp32-16x-relay --board front --device /dev/ttyUSB0`). To update a
board over WiFi, flash again with the same `--board` name (see below).

A bare `esphome run firmware/<variant>.yaml` fails, on purpose: the board name and the manifest are the only
sources of the Driver's identity (`board`, `driver`, `product`, `source`, `publishes`), so the YAML does not declare
them. ESPHome only warns about an undeclared substitution and would otherwise use the literal `${driver}` as an
MQTT topic; CI's resolved-config guard fails on that.

Subsequent updates can go over WiFi (run the script again once the device has joined your network)
using the OTA password in the board's `secrets/<name>.yaml`.

### Flashing with Claude Code

The `flash-esp32` skill (`skills/flash-esp32/SKILL.md` in `renewvan/skills`) walks through the same steps
interactively: it finds the variant, asks for the serial port or OTA address, fills `secrets.yaml` and the board's `secrets/<name>.yaml` from
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
MQTT and the OTA password are compiled in from `secrets.yaml` and `secrets/<name>.yaml`, so a CI-built binary contains placeholders and
cannot be flashed onto a van (and would publish a known OTA password). The process is shared by every
renewvan repo and lives in `hub` (`hub/docs/adr/0015-one-release-process-via-reusable-workflows.md`).
The release workflow's pinned hub build step calls `scripts/manifest_substitutions.py` without `--board`, which now
fails loudly instead of building placeholders until hub passes a board name (hub#161, ticket #12).

## Driver info and health

Each board appears as its own Driver (`esp32-<name>`) on the dashboard's Driver page like every other Driver. The
static fields of the kind live in `manifests/<variant>.json`, the single source. It must not contain `driver`,
`version` or `board_serial`. Optional fields
(`manufacturer`, `homepage`) are omitted from the info when empty.
`scripts/manifest_substitutions.py <variant> --board <name>` (`--board` is required; without it the script fails rather than build placeholders) turns it, with the board's `board` and `driver`, into
the build's substitutions, for both the flash script and CI. `info` also carries `variant` (the firmware kind,
informational). `board_serial` is the board's MAC in the form `AA:BB:CC:DD:EE:FF`, so it can be
compared with the label on the board.

`ip` is the IPv4 address DHCP gave the board, so the dashboard can show where to reach it (for the
OTA update, or to find it on the router). It is read when the info is published, so it is as fresh
as the board's last (re)connect to the broker, and it is omitted, never `0.0.0.0`, while the board
has no address. Reserve the address on your router if you want it to stay put.

## CI

`.github/workflows/validate.yml` runs the script tests and `variants.py check`, then, **for every variant
found under `manifests/`** (a matrix built from the directory), builds `firmware/<variant>.yaml` with
`esphome/build-action` (pinned by commit SHA, with ESPHome pinned) against the placeholder
`secrets.yaml.example`. It passes a CI version (`ci-<short sha>`), the variant's manifest and a fixed board name
(`ci-board`, `CI_BOARD` in the workflow, since nothing built there is flashed) as substitutions, then fails if:

- the action's reported project version differs from the CI value, or
- the resolved configuration (`esphome config`) still contains an unexpanded `$placeholder`, or
- the resolved configuration is not the variant's (project name `renewvan.driver-esp32-<variant>`, node name `renewvan-esp32-<board>`) or does not use the board's health topic `renewvan/esp32-<board>/health`, or
- for the relay, the `publish_retained_state` script and the `packages:` list name different channels.

The placeholder check exists because ESPHome exits 0 on an undeclared substitution.

There is no versioned image to publish: each board is flashed once from the owner's checkout of a release tag,
and `hub`'s deployment manifest references this repo's flash instructions.

> **Two different `manifest.json` files.** The build action also writes its own `manifest.json` (an
> ESP Web Tools manifest) into its output folder, named after the device. That is unrelated to
> `manifests/<variant>.json`, which describes the Driver. The latter is the source of the Driver info; the
> action's is a build artifact and is not used here.

## Variant: esp32-8x-relay

8-channel relay driver for the LC Technology LC-Relay-ESP-8R-D5 (ESP32-E, one relay per GPIO, no shift
register). Entrypoint `firmware/esp32-8x-relay.yaml`, manifest `manifests/esp32-8x-relay.json`, channel package
`packages/relay-channel-gpio.yaml`. Same wire contract and safety rules as the 16x variant,
with channels `<board>-01` to `<board>-08` (the channel keys `relay_01` to `relay_08` below exist only inside the
firmware); choose it with `scripts/flash.sh esp32-8x-relay --board <name>`.

| Channel key | GPIO | Channel key | GPIO               |
| ----------- | ---- | ----------- | ------------------ |
| `relay_01`  | 32   | `relay_05`  | 27                 |
| `relay_02`  | 33   | `relay_06`  | 14                 |
| `relay_03`  | 25   | `relay_07`  | 12 (strapping pin) |
| `relay_04`  | 26   | `relay_08`  | 13                 |

Pins come from the [ESPHome device page](https://devices.esphome.io/devices/esp32e-relay-x8/). Relay polarity
(assumed active-high, not inverted) and the GPIO12 boot behaviour are **unverified on the bench**: test with no load
connected first. Each board is its own Driver with its own ids, so it can share a van with any other board, of this
variant or the 16x one.

## Variant: esp32-16x-relay

16-channel switched-load relay driver (lights, a water pump, a fridge, a heater, an inverter enable) on an
ESP32-WROOM with two chained SN74HC595 shift registers. Entrypoint `firmware/esp32-16x-relay.yaml`, manifest
`manifests/esp32-16x-relay.json`. Flashed as `--board <name>` it is the Driver `esp32-<name>`: it publishes
`renewvan/esp32-<name>/info` and `renewvan/esp32-<name>/health`.

### Hardware

ESP32-WROOM and two chained SN74HC595 shift registers driving sixteen relay outputs.

| Signal               | GPIO   | Note                                                                |
| -------------------- | ------ | ------------------------------------------------------------------- |
| Data (`SER`)         | GPIO14 |                                                                     |
| Clock (`SRCLK`)      | GPIO13 |                                                                     |
| Latch (`RCLK`)       | GPIO12 | Strapping pin. **No external pull-up** (GPIO12 high selects 1.8 V). |
| Output enable (`OE`) | GPIO5  | Strapping pin. External pull-up **required**, see below.            |

Channel 01 (`<board>-01`, key `relay_01`) is shift-register output 0 (`QA` of the register wired to the ESP32 data
line) and channel 16 is output 15. The chain order is read from the ESPHome source, not from the wiring;
confirm it on the bench.

### Wire contract

Per channel `<board>-01` to `<board>-16` (`<id>` below):

| Topic                          | Retained | Payload                                                     |
| ------------------------------ | -------- | ----------------------------------------------------------- |
| `renewvan/relay/<id>/state`    | yes      | JSON `true` / `false`, published after the output changed   |
| `renewvan/relay/<id>/name`     | yes      | JSON string, only once a name has been set                  |
| `renewvan/relay/<id>/driver`   | yes      | JSON string `"esp32-<board>"`, the owning Driver, always    |
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
relay_03:
  !include { file: ../packages/relay-channel.yaml, vars: { ch: relay_03, nn: "03", bit: 2 } }
```

`ch` is the channel's key inside the firmware (ESPHome ids and the connect-chain table, never on the bus), `nn` its
zero-padded number (the bus id is `<board>-<nn>`; `check_relay_channels.py` requires `ch` to be `relay_<nn>`), and `bit` is the shift-register output 0 to 15. ESPHome rejects a `bit`
above 15, a duplicate `bit` and a duplicate `ch`; it does not notice a skipped `bit`. Labels are not
set here: publish a `name/set` (the dashboard's Settings does this), and the name is stored on the
board. Changing a channel's `ch` orphans its stored name.

The `publish_retained_state` script in `firmware/esp32-16x-relay.yaml` lists every channel once (as `${board}-<nn>`). It is step (1)
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
   topics (each with its `driver` = `"esp32-<name>"`), then `renewvan/esp32-<name>/info` (with `variant`), then
   `renewvan/esp32-<name>/health` = `online`.
   The info carries `"ip"`: confirm it is the address your router's DHCP table shows for the
   board, and that it also reads on the dashboard under Settings › Drivers › ESP32 16x relay.
4. `mosquitto_pub -t renewvan/relay/<name>-01/set -m true` switches channel 1 and `state` becomes
   `true` afterwards; `-m false` switches it off.
5. Publish `'"Water pump"'` to `renewvan/relay/<name>-03/name/set` and confirm the retained `name`;
   power-cycle after 60 seconds and confirm it persists.
6. Unplug the board's network: its `health` becomes `offline`, the retained `info` stays, and the relays
   hold their state. With a second board on the bus, only the unplugged board's Driver goes `offline`.

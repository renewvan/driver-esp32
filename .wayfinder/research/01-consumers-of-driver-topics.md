# Research 01: what assumes one Driver per key, fixed relay ids, one source per id

Ticket: `.wayfinder/tickets/01-consumers-of-driver-topics.md`. Sources: local checkouts of `hub`, `dashboard`,
`logger`, `mobile` (nothing changed). Paths are relative to `Renewvan/`. Line numbers are as of the checkouts on
2026-11-06; those marked `~` are approximate.

## Short answer

- The **wire contract is the real constraint**, not the consumers. Hub ADR 0020 says it outright: two boards on key
  `esp32` share one `info`, one `health` (one last will) and must not share entity ids (ADR 0008), so "two identical
  boards are still unsupported" and "adding a second ESP32 board type must revisit this key"
  (`hub/docs/adr/0020-one-driver-esp32-repo-many-firmware-variants.md:29-30`).
- **Dashboard** is already Driver-keyed and mostly multi-Driver-ready (rows per `<driver>` key, instances join by their
  own `driver` property). Two things do not scale: relay trust is one global boolean, and the relay UI is a flat list
  of ids with no board grouping.
- **Logger** and **mobile** ignore `info`/`health` entirely and key relays by `id` alone. No change for N boards,
  provided ids are unique.
- **Hub** has two hard-coded per-Driver-key places: the broker ACL (`esp32` account, `renewvan/esp32/#`) and the
  schemas/docs that define one `info`/`health` per key. No hub runtime code reads Driver topics or `relay_01..16`.
- No consumer hard-codes `relay_01..relay_16` as a set (ADR 0013: "No schema constrains an id, and the dashboard has no
  relay-id assumption", confirmed). Only owner config and demo/test data name ids.

## 1. The wire contract (hub schema and ADRs)

| Topic                                     | Today                                                                                                | Source                                                                                                           |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `renewvan/<driver>/info`                  | retained, one per Driver key, published before `online` on every connect, left retained when offline | `hub/docs/adr/0011-node-manifest-and-retained-info-topic.md` (Info bullet), `hub/schema/driver-info.schema.json` |
| `renewvan/<driver>/health`                | retained bare word `online`/`offline`, one MQTT last will per client                                 | ADR 0011 (Rules this sets), ADR 0013 "Unknown" bullet                                                            |
| `renewvan/relay/<id>/{state,name,driver}` | retained; `driver` is the publisher's key                                                            | `hub/schema/relay.schema.json` (properties)                                                                      |
| `renewvan/relay/<id>/set`, `/name/set`    | unretained commands                                                                                  | relay.schema.json description; ADR 0013 Contract                                                                 |

Single-instance assumptions written into the contract:

- `driver-info.schema.json`: required = driver, product, source, publishes, version. `driver` is "the Driver's key; must
  equal the `<driver>` topic segment". No board/instance field. `board_serial` and `ip` are optional free fields on that
  one message: "a support identity for display, never a join key" and "every Driver on one Host publishes the same
  value".
- `driver-manifest.schema.json` / `driver-info.schema.json` `driver` pattern
  `^(?!driver-)(?!demo$)[a-z][a-z0-9]*(-[a-z0-9]+)*$`: a per-board key such as `esp32-front` already validates. Only
  `demo` and a `driver-` prefix are rejected.
- `relay.schema.json` description: "One source per id: two Drivers must not publish the same `renewvan/relay/<id>/...`
  topic". ADR 0013 Contract: "Ids. Positional and zero-padded: `relay_01` to `relay_16` ... No schema constrains an id"
  and "One source per id". ADR 0008 (`hub/docs/adr/0008-node-naming-and-entity-neutrality.md:28`): "the id is derived
  from the source".
- `relay.schema.json` `driver` property: when absent a consumer attributes the instance to every Driver whose info
  `publishes` lists `relay`. Wrong once there are N relay Drivers.
- ADR 0011 "Rules this sets": same-type Drivers "both show the same instances ... accepted limit". ADR 0019 fixed that by
  adding the per-instance `driver` property
  (`hub/docs/adr/0019-entity-instances-name-their-driver-and-shared-primary-battery.md:18,34-37`).
- Relay trust assumes one health word covers all channels: ADR 0013 "Unknown" bullet ("a will cannot clear sixteen
  topics") and rejected "Per-relay health". With N boards, one will per board (one key per board) is needed so a dead
  board does not mark all relays unknown (see dashboard).
- Topic shapes: entity `renewvan/<entity>/<id>/<prop>` is 4 segments, `info`/`health` are 3. A relay id may be any
  non-`/` string (ADR 0013 "No reserved ids"). Board-scoped ids such as `front_relay_01` need no schema change.

### Hub infrastructure that keys on the Driver

- **Broker ACL** (`hub/bin/broker-accounts.sh:77`): the single `esp32` account may write `renewvan/esp32/#`,
  `renewvan/relay/+/state`, `+/name`, `+/driver`. Boards under other Driver keys would be denied their own
  `info`/`health` unless the ACL is widened (MQTT wildcards cannot express a prefix like `esp32-*`, so this needs a
  topic scheme, a rule per key, or one account per board). All boards share the one `esp32` account today
  (`:40`, `"esp32:esp32:"`), and its password is compiled into firmware and rotated only by OTA
  (`hub/bin/rotate-secret.sh:10-11,27-28`, `hub/bin/broker-accounts.sh:269`). Account list pinned in
  `hub/bin/test_compose_hardening.py:141`, `hub/bin/test_ensure_secrets.py:185,292`,
  `hub/bin/check-broker-auth.sh:117,131`, ADR 0025 (`hub/docs/adr/0025-broker-has-per-client-accounts-and-anonymous-read-only.md:9`).
- **Authoring doc** `hub/docs/authoring-a-driver.md:28,117` ("driver-esp32 is the one Driver"; manifest `driver` equals
  the topic segment); `:61` requires each entity `driver` equal that key.
- **Demo fleet**: `hub/schema/demo/fleet.demo-fleet.json:~78-80` declares one `esp32` Driver (16-channel relay);
  `relay_01..` scenarios in `hub/schema/demo/relay.relay_0N.demo.json`; `validate-demo.py` requires a fleet Driver that
  publishes an entity named in `initial.driver` (ADR 0019 line 37);
  `hub/schema/test_validate_demo_fleet.py:89` enforces info key equals entry key. A second relay board in the demo needs
  new scenarios with unique ids.
- `hub/plugins/hub/hub_status.py` reads no Driver info/health or relays (status, primary battery, icons only).

## 2. Dashboard (`dashboard/src`)

State and patterns (`hooks/useRenewvanBus.ts`):

- `~87-91` `entityPattern`: `renewvan/(tank|relay|...)/<id>/<prop>`, id any non-`/`. No fixed relay set.
- `95-106` `driverPattern`: `renewvan/<driver>/(info|health)`, key any non-`/`, `demo` excluded on the real root.
  Accumulates `state.drivers[key] = {info?, health?}` (`applyDriverMessage` `:291`, dispatch `:376`, type `DriverRecord`
  `types.ts:452`). Per key, so N Drivers work; a second board under one key overwrites (last info wins, ADR 0020).
- `~335-365` `applyRelayMessage`: `state`, `name`, `driver` per id; clearing `state` deletes the relay. Relays are
  `Record<string, Relay>` keyed by id alone (`types.ts:366-367,461`). Duplicate ids from two boards collide silently.
- `:588` `routerHealth: state.drivers.router?.health`: a hard-coded `router` key (single-router assumption, same
  pattern, not relay related).

Driver listing (`lib/drivers.ts`):

- `95-97` `instancesOf`, `~99-110` `entitiesWhere`, `151-185` `driverRows`: one row per `state.drivers` key. An instance
  belongs to the Driver named by its `driver` property; with none, to every Driver whose `publishes` includes its type;
  with an unknown `driver`, to a fallback row `domain:<type>`. Already correct for N boards under distinct keys if each
  relay publishes `driver`.
- `:75-85` `KEY_ACRONYMS`/`driverName()`: `esp32-16x-relay` shows "ESP32 16x Relay". `DriverRow.name` ignores `product`;
  a board display name would need a new source.
- **`227-232` `relayDriversOnline`** (used at `App.tsx:420`; consumed `components/relays/RelaysPage.tsx:24,182-183,206,212,236`):
  true only if at least one Driver publishes `relay` and every such Driver is `online`. With two relay boards one
  offline board freezes the whole Relays page and shows the "Unknown" banner for the healthy board. Needs per-relay
  trust by `relay.driver`; define behaviour for a relay with no `driver` (legacy: all relay Drivers).
- `components/settings/drivers/InstanceView.tsx:132-139`, `lib/instances.ts:18-33` (`ownerName`, `instanceLabel`) resolve
  the owner by `record.driver`; already per-Driver.
- `components/settings/drivers/DriverInfoView.tsx:21-22` shows `board_serial` and `ip` from the single info. Per-board
  keys give each board its own page; a shared key shows whichever board spoke last.
- `components/settings/drivers/RelaysView.tsx:45-64` lists all relay ids sorted numerically with no board grouping; empty
  text "Waiting for the relay driver to publish" (singular). `DriverView.tsx:23` maps `relay: 'relays'` to that same
  view; I read only the call sites, so whether a Driver page shows only its own relays or all relays is unconfirmed.
- `components/relays/RelaysPage.tsx:~217-252`: `ids = Object.keys(relays)`, panels via `panelsFor(ids)`; command phases
  keyed by id (`useCommandPhases`, `~54-110`).
- `config/relayPanels.ts:12-14,~40-60`: owner-edited (empty by default), keyed by channel id string (`relay_03` is the
  doc example); unlisted ids go to "Unassigned". With N boards, ids must be globally unique or config must key on
  `(driver, id)`.
- Hard-coded relay ids: none in production code; only tests/fixtures.

Commands: `renewvan/relay/<id>/set` routes by id only (ACL for `command` is `renewvan/relay/+/set`,
`hub/bin/broker-accounts.sh:~80-84`), so ids must be unique across boards.

## 3. Logger (`logger/logger/mapping.py`)

- `:101-104` `topic.split("/")`, requires 4 parts and `parts[0] == "renewvan"`: `info`/`health` (3) and `name/set` (5)
  are ignored. It never consumes Driver topics.
- `:30-32` relay fields `{"state": bool}` only; the point is `Point(domain).tag("id", entity_id).field(prop, value)`
  (`~:123`). Series keyed by `id` alone; `driver` is not logged (not in `_FIELDS["relay"]`).
- N boards: unique ids give separate series, no change. Duplicate ids across boards would merge into one series. History
  would not record which board an id belongs to; adding a `driver` tag is a logger change (out of scope per the map).
- `logger/README.md:10-17` documents `relay` as `state` only.

## 4. Mobile (`mobile/src`)

- `hooks/useRenewvanBus.ts:20` `TOPIC_PATTERN = /^renewvan\/(tank|relay|battery)\/([^/]+)\/([^/]+)$/`, `:88`
  `subscribe('renewvan/#')`. No `info`/`health` handling; relays keyed by id (`types.ts:77-91`).
- `tabs/SwitchesTab.tsx:12` `Object.keys(relays).sort()`; labels from `config/relayLabels.ts:35-40`
  (`EXPO_PUBLIC_RELAY_LABELS`, JSON `id -> label`). Its header comment says the wire has no label field (stale; the
  schema now has `name`). Read-only: no `set`, no trust logic, so a dead board's stale "on" reads as live (true today).
- Nothing needed for N boards with unique ids. Optional: show `name`/`driver`, gate on Driver health.

## 5. What breaks or needs to change for several boards (per-board info/health, unique ids)

Wire and infra (must change):

1. Pick the Driver key per **board instance** (for example `esp32-<board>`) or add an instance field. Today the key is the
   repo name (`hub/docs/adr/0018-device-to-driver-rename.md:37`, ADR 0020 line 9). ADR 0020 lists both options and defers
   them. A per-board key needs **no schema change** (`driver-info`, `driver-manifest`, `relay` already accept it); a
   same-key design needs a new field.
2. Unique relay ids van-wide (ADR 0008). `relay_01..16` is positional per board, so two boards collide. Ids need a board
   component or derive from the Driver key.
3. Broker ACL: the `esp32` write rule and shared account (`broker-accounts.sh:40,77`) must fit per-board topic roots; tests
   and `check-broker-auth.sh` pin the account list.
4. Firmware: `info`, `health` plus last will, and every entity `driver` value use the board's own key (the `driver` value
   must equal the `<driver>` segment, ADR 0019 line 34).
5. Demo fleet and examples need a second relay Driver with unique ids.

Dashboard (spec only): 6. Replace global `relayDriversOnline(state)` (`lib/drivers.ts:227`, `App.tsx:420`, `RelaysPage.tsx:182,212`) with a
per-relay check by `relay.driver`. 7. Group the Relays page and settings list by board; name boards (needs a display-name source: `product` or a new optional
manifest field); key `relayPanels` on unique ids. 8. Confirm `DriverView.tsx:23`/`RelaysView.tsx:45` list only the Driver's own relays.

No change: logger (given unique ids), mobile, hub runtime (`hub_status.py`), `describeDriver`/row building.

## 6. Risks and open points

- Retained leftovers: `info` stays retained after a board dies (ADR 0011) and a removed board leaves retained `info`,
  `health` and relay topics. ADR 0011 puts cleanup out of scope; with per-board keys the dashboard lists ghost Drivers
  forever (one row per `state.drivers` key, `lib/drivers.ts:151-170`).
- `board_serial` (the MAC) is the natural stable board identity but the schema forbids using it as a join key.
- Sonoff/Shelly later: extra Drivers under their own keys publishing `relay` with `driver`; the dashboard join already
  handles that except for the global trust boolean.
- Not verified: no code or tests were run. `graphify query` was used for hub and dashboard; logger and mobile have no graph
  and were read directly.

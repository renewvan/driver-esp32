# Research: how Sonoff and Shelly relays speak MQTT natively

Ticket: `.wayfinder/tickets/03-sonoff-shelly-mqtt-surface.md` (map: any number of relay boards per van).
Date: 2026-11-06. Throwaway branch, never merged.
Contract compared against: hub `docs/adr/0013-writable-relay-and-its-wire-contract.md`, `schema/relay.schema.json`.

Confidence: facts are taken from the cited primary pages. Items marked **UNVERIFIED** were not on the fetched page
(or the page was truncated) and need a check against a real device or the source before a design depends on them.

## 1. The renewvan contract

- `renewvan/relay/<id>/state`: retained JSON boolean, published only after the physical output changed.
- `renewvan/relay/<id>/name`: optional retained non-empty JSON string.
- `renewvan/relay/<id>/set`: unretained, JSON `true`/`false` only; no toggle.
- `renewvan/relay/<id>/name/set`: unretained JSON string.
- Optional retained `renewvan/relay/<id>/driver`.
- State is unknown whenever the owning Driver health is not `online` or absent; one last will per Driver (ADR 0011).
- After any restart every channel is off; the Driver owns boot state; the hub never re-asserts. Clean MQTT session. One source per id.
- ADR 0013 explicitly rejects "ESPHome's native command topic" because it speaks only `ON`/`OFF`/`TOGGLE`.

## 2. Tasmota (Sonoff running Tasmota)

Sources: <https://tasmota.github.io/docs/MQTT/>, <https://tasmota.github.io/docs/Commands/>

- Topic layout: `cmnd|stat|tele` prefixes (`Prefix1..3`), `FullTopic` default `%prefix%/%topic%/`, device `Topic` default
  `tasmota_XXXXXX` (last 6 of MAC). All configurable, so the namespace can be re-pointed, but the command/result suffixes cannot.
- Command: `cmnd/<topic>/POWER` (`POWER1`..`POWERn` for multi-relay; `SetOption26` forces the index for one relay).
  Payloads: `0|off|false`, `1|on|true`, `2|toggle`, `3|blink`, `4|blinkoff`. Empty payload = query.
- Result: `stat/<topic>/POWER` = `ON`/`OFF` (plain text); `stat/<topic>/RESULT` JSON. `SetOption4` switches the reply topic
  between RESULT and %COMMAND%. `SetOption59` adds `tele/<topic>/STATE` after commands. Periodic `tele/<topic>/STATE` every `TelePeriod` (default 300 s).
- Retain: `PowerRetain` default `0`, so `stat/.../POWER` is NOT retained by default. `StateRetain` default 0. Docs warn a retained
  power message "will always override the PowerOnState".
- Last will: `tele/<topic>/LWT`, `Online` / `Offline`, retained.
- Boot state: `PowerOnState` 0 OFF, 1 ON, 2 TOGGLE, 3 restore last saved (**default**), 4 ON and lock, 5 ON after PulseTime.
  Default conflicts with ADR 0013; set `PowerOnState 0`.
- Local controls: `SetOption114` detaches switches from relays (sends `{"Switch1":{"Action":"ON"}}`); `SetOption73` decouples buttons.
- **UNVERIFIED**: clean-session setting; whether the LWT payload text can be changed; case rules of `true`/`false`.

## 3. ESPHome on Sonoff

Sources: <https://esphome.io/components/mqtt.html>, <https://esphome.io/components/switch/>, and in GitHub
<https://github.com/esphome/esphome/tree/dev/esphome/components/mqtt> (`mqtt_switch.cpp`, `mqtt_component.cpp`, `mqtt_client.cpp`).

- Default topics: state `<topic_prefix>/switch/<object_id>/state`, command `<topic_prefix>/switch/<object_id>/command`;
  `topic_prefix` defaults to the app name. `state_topic` and `command_topic` are overridable per entity (`null` disables).
- State payload: `state ? "ON" : "OFF"` (plain text), published on every change and as initial state.
- Command payloads: code routes `PARSE_ON`/`PARSE_OFF`/`PARSE_TOGGLE`; anything else logs a warning. Exact accepted strings and case
  live in `parse_on_off`: **UNVERIFIED** (not in the fetched files).
- Retain: base MQTT `retain` "Defaults to `true`"; `command_retain` defaults `false`; per-entity `retain` override.
- Birth/will: default birth = retained `<topic_prefix>/status` `online`; will = same topic `offline`. Overridable
  (`birth_message`, `will_message`, `shutdown_message`), so topic and payload can be set to the Driver health values.
- `clean_session` default `false` (conflicts with ADR 0013; settable). `reboot_timeout` default 15 min with no MQTT (`0s` disables).
- Boot state: switch `restore_mode` default `ALWAYS_OFF` (matches ADR 0013).
- This is the cheapest case: driver-esp32 already builds ESPHome variants with the renewvan topic layer.

## 4. Shelly Gen2 / Gen3 / Plus (RPC)

Sources: <https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Mqtt>,
<https://shelly-api-docs.shelly.cloud/gen2/Components/FunctionalComponents/Switch>
(the older `.../FunctionalComponents/Mqtt` URL returns 404).

- Config: `topic_prefix` (default null = device id; no `$ # + % ?`, max 300 chars), `client_id`, `rpc_ntf` (default true),
  `status_ntf` (default false), `enable_control` (default true).
- Availability/LWT: `<prefix>/online` = `true` on connect, LWT `false` on abrupt disconnect. Plain text booleans.
- Command: `<prefix>/command/switch:<id>` payload `on`, `off`, `toggle` (`on,<seconds>` / `off,<seconds>` for flip-back), `status_update`.
  Errors on `<prefix>/error/switch:<id>`. RPC alternative: `<prefix>/rpc` with `Switch.Set` (`id`, `on` boolean, `toggle_after`).
- Status: `<prefix>/status/switch:<id>` JSON object, e.g. `{"id":0,"source":"init","output":false,...}`; the boolean is `output`.
  Notifications on `<prefix>/events/rpc` (`NotifyStatus`).
- Retain: not mentioned on the MQTT or Switch pages. **UNVERIFIED**; treat as not retained until tested.
- Boot state: switch config `initial_state` in `off`, `on`, `restore_last`, `match_input`. Must be `off`. `auto_off` must stay disabled.
- Clean session: not documented on the MQTT page. **UNVERIFIED**.

## 5. Shelly Gen1

Source: <https://shelly-api-docs.shelly.cloud/gen1/#shelly-mqtt> (first 100k of 420k characters read; the rest is **UNVERIFIED**).

- Status: `shellies/<model>-<deviceid>/relay/<n>` = `on` | `off` | `overpower` (1PM only). Plain text.
- Command: `shellies/<model>-<deviceid>/relay/<n>/command` = `on` | `off` | `toggle`.
- Availability: `shellies/<model>-<deviceid>/online` = `true` on connect; LWT `false`. Announce JSON on `shellies/announce` and `.../announce`.
- Retain: LWT topic retained only "if the Retain flag is set" (`mqtt_retain`); docs "do not recommend using retained MQTT messages".
- `mqtt_clean_session` and `mqtt_keep_alive` (example 60 s) are settable through `/settings`.
- `default_state` exists per relay (example `off`); the full value list was not on the fetched content (**UNVERIFIED**).

## 6. Gap analysis vs the renewvan relay contract

| Contract point   | Tasmota                           | ESPHome                   | Shelly Gen2+                | Shelly Gen1                 |
| ---------------- | --------------------------------- | ------------------------- | --------------------------- | --------------------------- |
| State topic      | `stat/<t>/POWER`                  | `<p>/switch/<id>/state`   | `<p>/status/switch:<n>`     | `shellies/<m>/relay/<n>`    |
| State form       | text `ON`/`OFF`                   | text `ON`/`OFF`           | JSON object, `output` bool  | text `on`/`off`/`overpower` |
| State retained   | no (default)                      | yes (default)             | not documented              | not documented              |
| Command topic    | `cmnd/<t>/POWER`                  | `<p>/switch/<id>/command` | `<p>/command/switch:<n>`    | `.../relay/<n>/command`     |
| Command form     | text; `true`/`false` listed       | text ON/OFF/TOGGLE        | text on/off/toggle          | text on/off/toggle          |
| Toggle on device | yes                               | yes                       | yes                         | yes                         |
| LWT / health     | `tele/<t>/LWT` `Online`/`Offline` | configurable              | `<p>/online` `true`/`false` | `.../online` `true`/`false` |
| Name on wire     | none                              | none                      | none                        | none                        |
| Boot state       | default restore last              | default `ALWAYS_OFF`      | `initial_state`             | `default_state`             |
| Clean session    | not documented                    | default false             | not documented              | configurable                |

Key gaps:

1. No device speaks `renewvan/relay/<id>/...`. Tasmota (`Prefix`/`FullTopic`/`Topic`) and Shelly Gen2 (`topic_prefix`) let you move the
   prefix, but suffixes (`/POWER`, `/command/switch:0`) are fixed; the contract needs exact `state`, `set`, `name`, `name/set`.
   Only ESPHome can match exactly, through per-entity `state_topic`/`command_topic`.
2. Payload shape: bare text, not JSON booleans; Shelly Gen2 state is an object. Tasmota lists `true`/`false` as command words, which
   is byte-identical to JSON `true`/`false` (case handling **UNVERIFIED**). Every device also accepts `toggle`, so the no-toggle rule
   must be enforced by the sender; devices will not reject it.
3. Retain: state is not retained by default on Tasmota and (undocumented) Shelly. `PowerRetain 1` fixes Tasmota but interacts with `PowerOnState`.
4. Health: LWT topics and payloads differ from the contract's per-Driver `online` health; a device LWT is per device, the contract's is per Driver.
5. `name` and `name/set` have no equivalent on any of these devices.
6. Boot/session defaults conflict for Tasmota (restore last) and ESPHome (`clean_session false`); all configurable at provisioning.
7. Shelly Gen1 `overpower` is a third state with no contract equivalent.

## 7. Minimal path to appear as a renewvan relay entity

- **ESPHome on Sonoff**: no bridge. Use a driver-esp32 package; override `state_topic`/`command_topic` per relay to
  `renewvan/relay/<id>/state` and `/set`; set will/birth to the Driver health topic; `clean_session: true`;
  `restore_mode: ALWAYS_OFF`. Remaining gap: native payloads are `ON`/`OFF`, so JSON `true`/`false` needs the same custom
  handling the existing variants use (ADR 0013 rejected the native topic for this reason). Name via a template text entity.
- **Tasmota or Shelly via device config only**: insufficient. Even best case (`PowerRetain 1`, `PowerOnState 0`, custom `FullTopic`)
  leaves wrong suffixes, text payloads and no name.
- **Bridge Driver** (one per vendor family, its own Driver key, health and last will):
  - subscribe `renewvan/relay/<id>/set` (JSON bool), translate to `cmnd/<t>/POWER ON|OFF`, `<p>/command/switch:<n> on|off` or
    `.../relay/<n>/command on|off`; never forward `toggle`;
  - subscribe the device state (Gen2 `output`) and publish retained JSON boolean `renewvan/relay/<id>/state` only after the device reports it;
  - publish `name` and handle `name/set` itself (names live in bridge config);
  - map device LWT into Driver health (open: per-device vs per-Driver, see map "Health semantics");
  - enforce boot-off at provisioning (`PowerOnState 0`, `initial_state off`, `default_state off`), not at runtime.
- Provisioning checklist: Tasmota `PowerOnState 0`, `PowerRetain` as the bridge needs, `SetOption114 1` if wall switches must not drive
  relays directly; Shelly Gen2 `initial_state: off`, `auto_off: false`, `status_ntf: true`; Shelly Gen1 `default_state` off, `mqtt_clean_session` true.

## 8. Implications for the map

- A non-ESP32 relay Driver is a separate Driver key; ADR 0013's "one source per id" and per-Driver health already allow several Drivers
  publishing disjoint relay ids.
- The optional retained `driver` field in `relay.schema.json` exists for this; the bridge should publish `renewvan/relay/<id>/driver`.
- Security: these devices share the anonymous broker, and their web UIs are separate control paths, comparable to the web-server concern in ADR 0013.

## Sources

- <https://tasmota.github.io/docs/MQTT/>
- <https://tasmota.github.io/docs/Commands/>
- <https://esphome.io/components/mqtt.html>
- <https://esphome.io/components/switch/>
- <https://github.com/esphome/esphome/blob/dev/esphome/components/mqtt/mqtt_switch.cpp>
- <https://github.com/esphome/esphome/blob/dev/esphome/components/mqtt/mqtt_component.cpp>
- <https://github.com/esphome/esphome/blob/dev/esphome/components/mqtt/mqtt_client.cpp>
- <https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Mqtt>
- <https://shelly-api-docs.shelly.cloud/gen2/Components/FunctionalComponents/Switch>
- <https://shelly-api-docs.shelly.cloud/gen1/#shelly-mqtt>
- hub `docs/adr/0013-writable-relay-and-its-wire-contract.md`, `schema/relay.schema.json` (read-only)

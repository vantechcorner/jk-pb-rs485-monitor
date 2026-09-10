# Home Assistant — IRIV IOC - JK BMS

MQTT sensor package for the CircuitPython poller on Cytron IRIV IOC.

| Field | Value |
|-------|--------|
| **Name** | IRIV IOC - JK BMS |
| **Manufacturer** | Cytron Technologies |
| **Topics** | `iriv/jkbms/...` |
| **Payload** | `{"value": <number>}` |

Field-tested: MQTT sensors + [`web/`](../web/) dashboard OK against broker `172.16.10.40`.

![IRIV IOC - JK BMS in Home Assistant](../docs/images/IRIV-IOC-JK-BMS-Home-Assistant.png)

![MQTT sensor package in HA](../docs/images/IRIV-IOC-JK-BMS-Home-Assistant-Sensor-Config.png)

## Add to HA

1. MQTT integration → broker (e.g. `172.16.10.40:1883`).
2. Include as a package (file already starts with `mqtt:`):

```yaml
# configuration.yaml
homeassistant:
  packages:
    iriv_jkbms: !include homeassistant/mqtt_cytron_iriv_ioc_jkbms.yaml
```

Or merge the `sensor:` list into an existing `mqtt:` block (do not nest `mqtt:` twice).

3. Check configuration → Restart Home Assistant.

`unique_id` values stay stable (`cytron_iriv_ioc_jkbms_*`) so entities are not duplicated when only the device display name changes.

## Pack series

Keep in sync with IRIV [`settings.toml`](../iriv-ioc/firmware/settings.toml) `JK_CELLS` and [`web/app.js`](../web/app.js) `CELL_COUNT`:

| Pack | Firmware / web | HA cells in YAML |
|------|----------------|------------------|
| 4S | `JK_CELLS = 4` | uncomment 4S block; comment 8S/16S |
| 8S (lab) | `JK_CELLS = 8` | cells 1–8 active |
| 16S | `JK_CELLS = 16` | keep 1–8 + uncomment 9–16 |

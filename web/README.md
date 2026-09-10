# JK-PB MQTT web dashboard

Static page for **IRIV IOC - JK BMS** topics (`iriv/jkbms/#`). Browser uses **MQTT over WebSockets** (not TCP 1883).

Field-tested against lab broker with the CircuitPython IRIV firmware.

![IRIV IOC - JK BMS web dashboard](../docs/images/IRIV-IOC-JK-BMS-Web.png)

## Run locally

```powershell
cd web
python -m http.server 8081
```

Open `http://127.0.0.1:8081`. Defaults: `ws://172.16.10.40:9001`, prefix `iriv/jkbms` (gear icon to change).

Set `CELL_COUNT` in `app.js` to **4 / 8 / 16** (must match IRIV `JK_CELLS`). Lab default **8S**.

Status bar **Feed**: **Live** = publish after connect; **Retain only** = broker cache on subscribe (dimmed).

## Mosquitto WebSockets

```conf
# /etc/mosquitto/conf.d/websockets.conf
listener 9001
protocol websockets
allow_anonymous true
```

```bash
sudo systemctl restart mosquitto
```

Keep `9001/tcp` on LAN/Tailscale only.

## Topics

Payload `{"value": <number>}`. Suffixes: `pack/voltage|current|power|soc|…`, `cells/1`…`N`, `temp/mos|battery1|battery2`, …

SOC: if raw `> 100`, UI uses **low byte** of JK `0x12A6`.

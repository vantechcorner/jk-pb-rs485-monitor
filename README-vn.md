# JK-PB RS485 Monitor

Cong cu **monitor** BMS JiKong **JK-PB\*** qua **Modbus RTU (RS485)** UART1: poller PC, IRIV MQTT, va (sap toi) ESP32.

> English: [README.md](README.md)

**Du an chi em:** [deye-sg06-rs485-monitor](../deye-sg06-rs485-monitor) — bien tan Deye (bus 9600 rieng).

## Da thu nghiem

**JK-PB1A16S10P** tren pack **24 V 8S**: UART1 = **001**, slave **15**, **115200**.

## Nhanh

```bash
pip install -r requirements.txt
python jk-pb-modbus-read.py --port COM35 --cells 8 --once --full
python _gen_jkbms_iriv_jobs.py
```

IRIV: import `jkbms-iriv-ioc-config.json`, topic `iriv/jkbms/...`. Toi da **26** job bat tren gateway lab.

ESP32: xem `docs/esp32/README.md`.

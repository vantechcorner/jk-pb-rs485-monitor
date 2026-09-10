# SPDX-License-Identifier: MIT
"""IRIV IOC — JK-PB BMS Modbus block read → MQTT.

Flash CircuitPython for cytron_iriv_io_controller, copy this tree + Adafruit
libs to CIRCUITPY (see README.md). One Modbus master on the JK RS485 bus.
"""

import os
import time

import board
import digitalio

from iriv_eth import init_ethernet
from iriv_rs485 import ModbusRTU
from jk_bms import read_live
from mqtt_publish import ensure_connected, make_client, publish_map


def _getenv(key, default):
    v = os.getenv(key)
    return default if v is None or v == "" else v


def _led():
    led = digitalio.DigitalInOut(board.LED)
    led.direction = digitalio.Direction.OUTPUT
    led.value = False
    return led


def main():
    led = _led()
    broker = _getenv("MQTT_BROKER", "172.16.10.40")
    port = int(_getenv("MQTT_PORT", "1883"))
    base = _getenv("MQTT_BASE", "iriv/jkbms")
    client_id = _getenv("MQTT_CLIENT_ID", "iriv-ioc-jkbms")
    user = _getenv("MQTT_USER", "")
    password = _getenv("MQTT_PASS", "")
    qos = int(_getenv("MQTT_QOS", "1"))
    retain = str(_getenv("MQTT_RETAIN", "true")).lower() in ("1", "true", "yes", "on")

    slave = int(_getenv("JK_SLAVE", "15"))
    baud = int(_getenv("JK_BAUD", "115200"))
    cells = int(_getenv("JK_CELLS", "8"))
    timeout_s = float(_getenv("JK_TIMEOUT_S", "1.0"))
    poll_ms = int(_getenv("POLL_MS", "1000"))
    poll_s = max(0.2, poll_ms / 1000.0)

    print("JK-PB MQTT poller starting")
    print("  broker=%s:%s base=%s" % (broker, port, base))
    print("  slave=%d baud=%d cells=%d poll=%dms" % (slave, baud, cells, poll_ms))

    while True:
        try:
            eth, pool = init_ethernet()
            break
        except Exception as exc:
            print("ETH retry:", exc)
            led.value = not led.value
            time.sleep(3.0)

    mqtt = make_client(pool, broker, port, client_id, user, password)
    while not ensure_connected(mqtt):
        print("MQTT retry…")
        led.value = not led.value
        time.sleep(3.0)

    bus = ModbusRTU(baud=baud, timeout_s=timeout_s)
    next_poll = time.monotonic()
    fails = 0
    print("Ready (RS485 optional until BMS is wired)")

    while True:
        try:
            mqtt.loop(timeout=1.0)
        except Exception as exc:
            print("MQTT loop:", exc)
            ensure_connected(mqtt)

        now = time.monotonic()
        if now < next_poll:
            time.sleep(0.01)
            continue
        next_poll = now + poll_s

        try:
            values = read_live(bus, slave, cells)
            fails = 0
            led.value = True
            publish_map(mqtt, base, values, qos=qos, retain=retain)
            led.value = False
            print(
                "OK V=%.3f I=%.3f SOC=%s cells=%d"
                % (
                    values["pack/voltage"],
                    values["pack/current"],
                    values["pack/soc"],
                    cells,
                )
            )
        except Exception as exc:
            fails += 1
            led.value = fails % 2 == 0
            # Expected until JK RS485 is connected.
            print("POLL fail #%d: %s" % (fails, exc))
            if fails >= 3:
                try:
                    ensure_connected(mqtt)
                except Exception:
                    pass


try:
    main()
except Exception as e:
    print("FATAL:", e)
    try:
        led = digitalio.DigitalInOut(board.LED)
        led.direction = digitalio.Direction.OUTPUT
        while True:
            led.value = not led.value
            time.sleep(0.25)
    except Exception:
        while True:
            time.sleep(1)

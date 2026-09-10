# SPDX-License-Identifier: MIT
"""Publish decoded JK metrics to MQTT (Adafruit MiniMQTT)."""

import json

import adafruit_minimqtt.adafruit_minimqtt as MQTT


def _env_bool(val, default=True):
    if val is None:
        return default
    s = str(val).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    return default


def make_client(pool, broker, port, client_id, user="", password=""):
    kwargs = {
        "broker": broker,
        "port": int(port),
        "client_id": client_id,
        "is_ssl": False,
        "socket_pool": pool,
        "ssl_context": None,
        "keep_alive": 60,
    }
    if user:
        kwargs["username"] = user
        kwargs["password"] = password or ""
    client = MQTT.MQTT(**kwargs)

    def _on_connect(c, _ud, _flags, _rc):
        print("MQTT: connected to", broker)

    def _on_disconnect(c, _ud, _rc):
        print("MQTT: disconnected")

    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    return client


def ensure_connected(client, retries=5, delay_s=2.0):
    import time

    for attempt in range(retries):
        try:
            if not client.is_connected():
                print("MQTT: connecting…")
                client.connect()
            return True
        except Exception as exc:
            print("MQTT: connect failed:", exc)
            time.sleep(delay_s * (attempt + 1))
    return False


def publish_map(client, base, values, qos=1, retain=True):
    """Publish each suffix -> {"value": n} under base/."""
    base = base.rstrip("/")
    for suffix, value in values.items():
        topic = "%s/%s" % (base, suffix)
        payload = json.dumps({"value": value})
        client.publish(topic, payload, retain=retain, qos=qos)

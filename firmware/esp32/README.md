# DeviceOps ESP32 reference firmware

This PlatformIO project is the verified DeviceOps reference implementation for
an ESP32-S3 with a BME280 sensor and an onboard WS2812 RGB LED. It demonstrates
the version 1 MQTT protocol; DeviceOps devices are not required to use ESP32,
this board, or this firmware.

## Hardware

- ESP32-S3 development board compatible with `esp32-s3-devkitc-1`
- BME280 at I2C address `0x76`
- Onboard WS2812 RGB LED on GPIO 48 for the verified board

Wire the BME280 as follows:

| BME280 | ESP32-S3 |
| --- | --- |
| VCC | 3.3V |
| GND | GND |
| SDA | GPIO 8 |
| SCL | GPIO 9 |

## Local secrets

From `firmware/esp32`, create the ignored local header:

```powershell
Copy-Item include\secrets.example.h include\secrets.h
```

Edit `include/secrets.h` and set `WIFI_SSID`, `WIFI_PASSWORD`, `MQTT_BROKER`,
`DEVICE_ID`, and `DEVICE_SECRET`. The device ID and one-time secret come from a
DeviceOps device registration. Use the LAN IPv4 address of the computer running
Mosquitto for `MQTT_BROKER`; `127.0.0.1` would refer to the ESP32 itself. The
committed example contains placeholders only. The real `secrets.h` is ignored by
Git and must never be committed.

## Build, upload, and monitor

Install PlatformIO Core or use the PlatformIO IDE extension, then run:

```powershell
cd firmware\esp32
pio run
pio run --target upload
pio device monitor --baud 115200
```

Do not upload firmware that still contains placeholder or build-only device
credentials. Register the physical device in DeviceOps and set its returned
`DEVICE_ID` and `DEVICE_SECRET` first.

PlatformIO normally detects the upload and monitor port. If more than one serial
device is connected, pass the appropriate port with `--upload-port` or
`--port` instead of committing a machine-specific COM port.

## DeviceOps behavior

The firmware:

- connects to Wi-Fi, synchronizes UTC time with NTP, and reconnects Wi-Fi/MQTT;
- derives an MQTT signing key from `DEVICE_SECRET` without sending the plaintext
  secret over MQTT;
- creates one random session ID per boot and retains it across MQTT reconnects;
- publishes signed, retained QoS 1 `online`/`offline` presence with a signed MQTT
  Last Will;
- publishes temperature, humidity, pressure, RSSI, and uptime telemetry with
  signed QoS 0 messages and no retention;
- verifies the session and HMAC before handling `set_led`,
  `set_reporting_interval`, or `request_diagnostics`;
- publishes signed command acknowledgements with QoS 1 and no retention.

Topics and payloads follow [`../../contracts/mqtt.md`](../../contracts/mqtt.md).
Protocol version 1 does not provide general anti-replay protection: captured
authenticated messages can be replayed, including an older signed `online`
message. Session matching still protects the normal delayed stale-Last-Will case
after a newer boot session has been established.

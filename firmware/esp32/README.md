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

Edit `include/secrets.h` and set `WIFI_SSID`, `WIFI_PASSWORD`, and
`MQTT_BROKER`. Use the LAN IPv4 address of the computer running Mosquitto for
`MQTT_BROKER`; `127.0.0.1` would refer to the ESP32 itself. The committed example
contains placeholders only, and the real `secrets.h` is ignored by Git.

## Build, upload, and monitor

Install PlatformIO Core or use the PlatformIO IDE extension, then run:

```powershell
cd firmware\esp32
pio run
pio run --target upload
pio device monitor --baud 115200
```

PlatformIO normally detects the upload and monitor port. If more than one serial
device is connected, pass the appropriate port with `--upload-port` or
`--port` instead of committing a machine-specific COM port.

## DeviceOps behavior

The reference device ID is `esp32-001`. The firmware:

- connects to Wi-Fi, synchronizes UTC time with NTP, and reconnects Wi-Fi/MQTT;
- publishes retained QoS 1 `online`/`offline` presence with an MQTT Last Will;
- publishes temperature, humidity, pressure, RSSI, and uptime telemetry with
  QoS 0 and no retention;
- handles `set_led`, `set_reporting_interval`, and `request_diagnostics`;
- publishes command acknowledgements with QoS 1 and no retention.

Topics and payloads follow [`../../contracts/mqtt.md`](../../contracts/mqtt.md).

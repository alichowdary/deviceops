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

## Hosted DeviceOps setup

Register a new device in the DeviceOps console and save the returned device ID
and one-time device secret. From `firmware/esp32`, create the ignored local
header:

```powershell
Copy-Item include\secrets.example.h include\secrets.h
```

Edit `include/secrets.h` and set only:

- `WIFI_SSID`
- `WIFI_PASSWORD`
- `DEVICE_ID`
- `DEVICE_SECRET`

The committed example contains placeholders only. The real `secrets.h` is
ignored by Git and must never be committed.

Hosted mode is the default. The firmware automatically connects to
`mqtt.deviceops.net:443` using verified TLS, the device ID as both MQTT username
and client ID, and a broker password derived locally from the one-time device
secret. There is no second MQTT credential to copy or store. The firmware never
prints the device secret, signing key, or derived broker password.

Broker authentication is separate from the signed DeviceOps message envelopes.
Both use key material derived from the device secret, but the broker password is
domain-separated with `deviceops-broker-auth-v1`; the existing application
message signature algorithm remains unchanged.

TLS uses `WiFiClientSecure`, verifies the broker hostname and certificate chain,
and trusts the committed public Let's Encrypt ISRG Root X1 CA. The firmware
never calls `setInsecure()` or disables verification.

## Explicit local MQTT development

To use the repository's anonymous local Mosquitto broker instead of hosted
DeviceOps, uncomment the explicit mode switch in `include/secrets.h` and set the
development computer's LAN IPv4 address:

```cpp
#define DEVICEOPS_LOCAL_MQTT
#define DEVICEOPS_LOCAL_MQTT_BROKER "192.168.1.100"
```

Local mode is fixed to plaintext anonymous MQTT on port `1883`. Use the LAN
address of the computer running Docker; `localhost` and `127.0.0.1` refer to the
ESP32 itself. This switch does not weaken or alter hosted TLS configuration.

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
- derives the application signing key and domain-separated hosted broker
  password from `DEVICE_SECRET` without sending the plaintext secret over MQTT;
- creates one random session ID per boot and retains it across MQTT reconnects;
- publishes signed, retained QoS 1 `online`/`offline` presence with a signed MQTT
  Last Will;
- publishes a signed, retained QoS 1 capability manifest after every MQTT
  connection, declaring temperature, humidity, pressure, RSSI, uptime, LED,
  reporting-interval, and diagnostics support (and deliberately no battery);
- publishes temperature, humidity, pressure, RSSI, and uptime telemetry with
  signed QoS 0 messages and no retention;
- verifies the session and HMAC before handling `set_led`,
  `set_reporting_interval`, or `request_diagnostics`;
- stores a successfully applied reporting interval in local ESP32 NVS so it
  survives reboot and power cycles;
- publishes signed command acknowledgements with QoS 1 and no retention.

Topics and payloads follow [`../../contracts/mqtt.md`](../../contracts/mqtt.md).
Protocol version 1 does not provide general anti-replay protection: captured
authenticated messages can be replayed, including an older signed `online`
message. Session matching still protects the normal delayed stale-Last-Will case
after a newer boot session has been established.

DeviceOps does not automatically discover arbitrary sensors. This reference
firmware explicitly initializes and reads its BME280 and publishes the matching
capability manifest. Firmware adapted for another sensor must read that hardware
and advertise its own compatible manifest.

## Adapting another sensor

Your firmware remains responsible for reading its hardware. For example, a
PM2.5 implementation might call `float pm25 = readSensor();`, advertise a
`pm25_ugm3` telemetry capability with type `number`, label `PM2.5`, and unit
`µg/m³`, then publish each reading under that same `pm25_ugm3` key. DeviceOps
will provide the applicable scalar value, recent-sample column, numeric chart,
and threshold-alert choice from the manifest; no PM2.5-specific frontend branch
is needed. The device developer still owns the sensor driver, wiring, sampling,
and conversion code.

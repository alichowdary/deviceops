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

Edit `include/secrets.h` and set the Wi-Fi, MQTT, `DEVICE_ID`, and
`DEVICE_SECRET` values. The device ID and one-time secret come from a DeviceOps
device registration. The committed example contains placeholders only. The real
`secrets.h` is ignored by Git and must never be committed.

For local anonymous Mosquitto, use the computer's LAN IPv4 address, port `1883`,
`MQTT_TLS_ENABLED = false`, and empty MQTT username/password strings.
`127.0.0.1` would refer to the ESP32 itself.

Production HiveMQ credentials are operator-managed secrets and are not supplied
by this public repository. An operator connecting this reference device to
HiveMQ Cloud uses the following transport shape with locally supplied broker
credentials:

```cpp
constexpr char MQTT_BROKER[] =
    "YOUR_MQTT_BROKER_HOST";
constexpr uint16_t MQTT_PORT = 8883;
constexpr bool MQTT_TLS_ENABLED = true;
constexpr char MQTT_USERNAME[] = "YOUR_HIVEMQ_USERNAME";
constexpr char MQTT_PASSWORD[] = "YOUR_HIVEMQ_PASSWORD";
```

TLS mode uses `WiFiClientSecure`, verifies the broker hostname and certificate
chain, and trusts the committed public Let's Encrypt ISRG Root X1 CA. It never
uses insecure certificate mode. Broker authentication remains separate from the
existing signed DeviceOps message envelopes.

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

## Adapting another sensor

Your firmware remains responsible for reading its hardware. For example, a
PM2.5 implementation might call `float pm25 = readSensor();`, advertise a
`pm25_ugm3` telemetry capability with type `number`, label `PM2.5`, and unit
`µg/m³`, then publish each reading under that same `pm25_ugm3` key. DeviceOps
will provide the applicable scalar value, recent-sample column, numeric chart,
and threshold-alert choice from the manifest; no PM2.5-specific frontend branch
is needed. The device developer still owns the sensor driver, wiring, sampling,
and conversion code.

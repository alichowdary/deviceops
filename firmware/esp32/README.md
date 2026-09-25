# DeviceOps ESP32 reference firmware

This PlatformIO project contains two related pieces:

- `lib/DeviceOpsClient` is the reusable ESP32 Arduino client for hosted
  DeviceOps protocol and MQTT plumbing.
- `src/main.cpp` is the verified ESP32-S3 + BME280 + WS2812 reference
  application built on that client.

DeviceOps does not require this board or sensor and does not automatically
discover hardware. Application firmware still initializes and reads its own
sensors, converts units, declares capabilities, and performs command effects.

## Hardware used by the reference application

- ESP32-S3 development board compatible with `esp32-s3-devkitc-1`
- BME280 at I2C address `0x76`
- Onboard WS2812 RGB LED on GPIO 48 for the verified board

| BME280 | ESP32-S3 |
| --- | --- |
| VCC | 3.3V |
| GND | GND |
| SDA | GPIO 8 |
| SCL | GPIO 9 |

## Hosted DeviceOps setup

Register a device in the DeviceOps console and save its Device ID and one-time
DeviceOps secret. Create the ignored local header:

```powershell
cd firmware\esp32
Copy-Item include\secrets.example.h include\secrets.h
```

Set only these values in `include/secrets.h`:

- `WIFI_SSID`
- `WIFI_PASSWORD`
- `DEVICE_ID`
- `DEVICE_SECRET`

Do not commit that file. Hosted mode automatically uses:

- `mqtt.deviceops.net:443`
- verified TLS with the ISRG Root X1 CA
- the Device ID as MQTT username and client ID
- a broker password derived locally from the one-time DeviceOps secret

There is no second MQTT credential. The firmware never prints the device
secret, signing key, or derived broker password.

## Build, upload, and monitor

```powershell
cd firmware\esp32
C:\Users\HP\.platformio\penv\Scripts\pio.exe run
C:\Users\HP\.platformio\penv\Scripts\pio.exe run --target upload
C:\Users\HP\.platformio\penv\Scripts\pio.exe device monitor --baud 115200
```

Do not upload firmware that still has placeholders. The upload and monitor port
can be passed explicitly if PlatformIO finds more than one serial device.

## Ownership boundary

The reference application owns:

- Wi-Fi credentials and `WiFi.begin()`/reconnection;
- BME280 and I2C initialization and reads;
- WS2812 initialization and LED changes;
- metric selection, labels, units, and telemetry cadence;
- the hardware-specific `set_led` and diagnostics callback bodies.

`DeviceOpsClient` owns:

- hosted endpoint, port, verified TLS, and CA trust;
- signing-key and broker-password derivation;
- MQTT username/client ID, topics, connection, and reconnect attempts;
- UTC/NTP synchronization and refusal to publish with an invalid clock;
- one random boot session ID, signed retained presence, and retained Last Will;
- signed capability, telemetry, command, and acknowledgement envelopes;
- telemetry sequence numbering;
- protocol/session/device validation for incoming commands;
- reporting-interval validation and NVS persistence.

Wi-Fi deliberately remains application-owned because provisioning and reconnect
policy vary by product. UTC synchronization remains client-owned because valid
timestamps are required DeviceOps protocol plumbing. Connect Wi-Fi before
calling `device.begin()`, call `device.loop()` frequently, and call
`device.syncClock()` after the application restores a lost Wi-Fi connection.

## Reusing the client with another sensor

The public API registers scalar capabilities before `begin()` and publishes all
metrics for one sample in a single JSON object:

```cpp
#include <ArduinoJson.h>
#include <DeviceOpsClient.h>
#include <WiFi.h>

#include "secrets.h"

DeviceOpsClient device(DEVICE_ID, DEVICE_SECRET);
unsigned long lastSample = 0;

bool collectDiagnostics(
    JsonObjectConst arguments,
    JsonObject result,
    String& error
) {
    (void)arguments;
    (void)error;
    result["sensor_ready"] = mySensorReady();
    result["uptime_s"] = millis() / 1000UL;
    return true;
}

void setup() {
    initializeMySensor();

    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    while (WiFi.status() != WL_CONNECTED) delay(250);

    device.addNumberMetric("pm25_ugm3", "PM2.5", "µg/m³");
    device.addIntegerMetric("uptime_s", "Uptime", "s");
    device.onDiagnostics(collectDiagnostics);
    device.begin();
}

void loop() {
    device.loop();

    if (millis() - lastSample >= 5000UL) {
        lastSample = millis();
        JsonDocument sample;
        sample["pm25_ugm3"] = readMyPm25Sensor();
        sample["uptime_s"] = millis() / 1000UL;
        device.publishTelemetry(sample.as<JsonObjectConst>());
    }
}
```

Available metric declarations are `addNumberMetric()`, `addIntegerMetric()`,
`addBooleanMetric()`, and `addStringMetric()`. Keys use lowercase letters,
digits, and underscores and must begin with a letter. Numeric metrics receive
charts and threshold-alert choices in the DeviceOps console.

The current backend accepts only three protocol-v1 command types. Register only
the ones the device actually implements:

```cpp
device.onSetLed(handleSetLed);
device.enableReportingInterval(5);
device.onDiagnostics(collectDiagnostics);
```

`onSetLed()` and `onDiagnostics()` callbacks perform application-specific work,
return success/failure, and add safe fields to the supplied result object. The
client validates the command and publishes the full signed ACK. The reporting
interval command is handled and persisted by the client; the application uses
`device.reportingIntervalSeconds()` to schedule readings.

See [`lib/DeviceOpsClient/README.md`](lib/DeviceOpsClient/README.md) for the
compact client API and lifecycle reference.

## Explicit local MQTT development

Hosted mode is the default. To use the repository's anonymous plaintext local
broker, uncomment the explicit switch and set a reachable LAN address in the
ignored `include/secrets.h`:

```cpp
#define DEVICEOPS_LOCAL_MQTT
#define DEVICEOPS_LOCAL_MQTT_BROKER "192.168.1.100"
```

The reference application then constructs
`DeviceOpsTransport::local(DEVICEOPS_LOCAL_MQTT_BROKER)`, which uses port 1883
without TLS or broker credentials. Signed DeviceOps envelopes are still used.
This explicit mode cannot weaken hosted TLS configuration.

## Preserved reference behavior

The refactored application continues to provide BME280 temperature, humidity,
and pressure; RSSI and uptime; online/offline presence; capability publication;
LED ON/OFF; persisted reporting interval; application-supplied diagnostics;
command ACKs; verified hosted TLS; reconnects; and the authenticated retained
Last Will. One boot session ID is retained across MQTT reconnects, and a reset
creates a new session.

The deterministic startup self-test verifies signing-key derivation, the
DeviceOps message-signature test vector, and broker-password derivation without
using real credentials. Protocol details and replay limitations remain defined
by [`../../contracts/mqtt.md`](../../contracts/mqtt.md).

# DeviceOps ESP32 reference firmware

This PlatformIO project contains two related pieces:

- `lib/DeviceOpsClient` is the reusable ESP32 Arduino client for hosted
  DeviceOps protocol and MQTT plumbing.
- `src/main.cpp` is the verified ESP32-S3 + BME280 + WS2812 reference
  application built on that client.

DeviceOps does not require this board or sensor and does not automatically
discover hardware. Application firmware still initializes and reads its own
sensors, converts units, declares capabilities, and performs command effects.

## Quick start: run the reference ESP32 device

### Step 1 — Gather the hardware

You need:

- an ESP32-S3 development board compatible with `esp32-s3-devkitc-1`;
- a BME280 environmental sensor configured at I2C address `0x76`;
- four jumper wires; and
- a USB data cable. Some USB cables provide power only and cannot upload code.

The verified board also provides an onboard WS2812 RGB LED on GPIO 48.

### Step 2 — Wire the BME280

Unplug USB power before changing wires. I2C is the two-wire connection used here
for the environmental sensor.

| BME280 pin | Connect to ESP32-S3 |
| --- | --- |
| VCC | 3.3V |
| GND | GND |
| SDA | GPIO 8 |
| SCL | GPIO 9 |

### Step 3 — Install the software

Install:

- [Git](https://git-scm.com/downloads);
- [Visual Studio Code](https://code.visualstudio.com/); and
- the [PlatformIO IDE extension](https://platformio.org/install/ide?install=vscode).

PlatformIO builds the firmware and uploads it to the ESP32. Advanced users may
instead install standalone [PlatformIO
Core](https://docs.platformio.org/en/latest/core/installation/index.html).

### Step 4 — Clone the repository

Open PowerShell and run:

```powershell
git clone https://github.com/alichowdary/deviceops.git
cd deviceops
```

`cd` means “change directory.” In VS Code, open the `firmware/esp32` folder as
the PlatformIO project.

### Step 5 — Register a DeviceOps device

Open [deviceops.net](https://deviceops.net), sign in, open **Fleet**, and select
**Add device** to generate the registration. Copy the Device ID and one-time
DeviceOps secret before closing the dialog. The ID identifies the board; the
secret proves that it may connect. There is no second MQTT password to copy.
After registration, you may open the device from Fleet and use **Rename** on
Device Detail to assign a friendly display name.

### Step 6 — Create `secrets.h`

From the repository root, run:

```powershell
cd firmware\esp32
Copy-Item include\secrets.example.h include\secrets.h
```

Open `include/secrets.h` and replace the four placeholder values:

```cpp
constexpr char WIFI_SSID[] = "YOUR_WIFI_SSID";
constexpr char WIFI_PASSWORD[] = "YOUR_WIFI_PASSWORD";
constexpr char DEVICE_ID[] = "YOUR_REGISTERED_DEVICE_ID";
constexpr char DEVICE_SECRET[] = "YOUR_ONE_TIME_DEVICE_SECRET";
```

Use your Wi-Fi network name and password plus the Device ID and secret copied
from Fleet. Do not commit `secrets.h`; Git intentionally ignores it.

### Step 7 — Build the firmware

From `firmware/esp32`, run:

```powershell
pio run
```

A successful build ends with `SUCCESS`. Do not continue if the file still
contains placeholder credentials.

### Step 8 — Connect the board

Connect the ESP32-S3 with a data-capable USB cable. PlatformIO should detect its
serial port. If Windows reports a new COM port, that is the board connection.

### Step 9 — Upload the firmware

Run:

```powershell
pio run --target upload
```

A successful upload ends with `SUCCESS`; the board then resets and starts the
firmware.

### Step 10 — Open the serial monitor

Run:

```powershell
pio device monitor --baud 115200
```

Expected output includes:

- `MQTT auth self-test: PASS`
- `BME280 initialized.`
- `Wi-Fi connected.`
- `UTC clock synchronized.`
- `MQTT mode: hosted DeviceOps with verified TLS`
- `MQTT connected.`
- `Published retained ONLINE status.`
- recurring telemetry summaries

### Step 11 — Check DeviceOps

Open [deviceops.net](https://deviceops.net), go to Fleet, and select the device.
Confirm that it is **Online** and that telemetry cards, samples, and numeric
charts begin updating.

### Step 12 — Test commands

From Device Detail, test LED ON, LED OFF, a new reporting interval, and a
diagnostics request. An ACK is an acknowledgement: the device tells DeviceOps
whether the command actually succeeded or failed. A command remains `pending`
until that ACK is validated and stored.

### Step 13 — Test offline detection

While the device is Online, unplug it and wait for DeviceOps to show it as
Offline. Reconnect it and confirm that it becomes Online again. MQTT Last Will
is the broker feature that publishes the saved offline message when a device
disconnects unexpectedly.

### Troubleshooting

- **`pio` is not recognized:** restart VS Code after installing PlatformIO or
  use its built-in terminal. On Windows, the fallback is
  `& "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run`.
- **Build cannot find `secrets.h`:** copy `include/secrets.example.h` to
  `include/secrets.h` and keep the copy untracked.
- **Upload port is ambiguous or unavailable:** try another data-capable USB
  cable, close other serial monitors, or add `--upload-port <port>`. Text inside
  `<...>` is a placeholder; replace it with the detected COM port and do not
  type the angle brackets.
- **BME280 is not detected:** unplug power and recheck 3.3 V, GND, GPIO 8/9, and
  address `0x76`.
- **Wi-Fi never connects:** verify the SSID and password and confirm the ESP32
  can use that network.
- **TLS/MQTT connection fails:** confirm internet access, valid UTC time, and
  that the Device ID and secret belong to the same current registration. Hosted
  TLS cannot be disabled.
- **Local broker is unreachable:** use the development computer's LAN IP, not
  `localhost`. A LAN IP identifies that computer on the local network.

## Use DeviceOpsClient in your own ESP32 project

The reusable client is documented in
[`lib/DeviceOpsClient/README.md`](lib/DeviceOpsClient/README.md). The sections
below summarize the integration boundary and show how the reference application
uses the same public API available to another ESP32 Arduino project.

### Ownership boundary

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

### Integration example

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

### Explicit local MQTT development

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

## Reference behavior and protocol checks

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

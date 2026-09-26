# DeviceOpsClient

`DeviceOpsClient` is for developers who already have an ESP32 Arduino project
managed by PlatformIO. Your application continues to own Wi-Fi, sensors, GPIO,
unit conversion, sampling, and hardware command effects. The client adds the
DeviceOps protocol and hosted MQTT connection.

It currently targets ESP32 with the Arduino framework. It does not discover
sensors or automatically decide what your hardware should publish.

## Add DeviceOps to an existing ESP32 project

### Step 1 — Copy the library

From this repository, copy the complete directory:

```text
firmware/esp32/lib/DeviceOpsClient
```

into:

```text
<your-project>/lib/DeviceOpsClient
```

`<your-project>` means the root folder of your own PlatformIO project. Text
inside `<...>` is a placeholder; replace it with your own value and do not type
the angle brackets. The included `library.json` declares the MQTT and
ArduinoJson dependencies.

### Step 2 — Add DeviceOps credentials

Register a device from Fleet at [deviceops.net](https://deviceops.net) and save
its Device ID and one-time secret. Put them in an ignored `secrets.h` alongside
your Wi-Fi credentials:

```cpp
constexpr char WIFI_SSID[] = "YOUR_WIFI_SSID";
constexpr char WIFI_PASSWORD[] = "YOUR_WIFI_PASSWORD";
constexpr char DEVICE_ID[] = "YOUR_REGISTERED_DEVICE_ID";
constexpr char DEVICE_SECRET[] = "YOUR_ONE_TIME_DEVICE_SECRET";
```

Do not commit or print this file. The client derives the broker password and
message-signing key locally and never sends the plaintext secret in MQTT
payloads.

### Step 3 — Connect Wi-Fi in your application

`DeviceOpsClient` does not manage Wi-Fi. Connect it before starting the client:

```cpp
WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
while (WiFi.status() != WL_CONNECTED) delay(250);
```

Your application remains responsible for its Wi-Fi provisioning and reconnect
policy.

### Step 4 — Create the client

Include the library and construct the hosted client:

```cpp
#include <DeviceOpsClient.h>

DeviceOpsClient device(DEVICE_ID, DEVICE_SECRET);
```

Hosted mode uses `mqtt.deviceops.net:443`, verified TLS, and the Device ID as
the MQTT username and client ID.

### Step 5 — Register capabilities

Capabilities tell the DeviceOps website which values and controls this device
supports. Register every metric before `begin()`:

```cpp
device.addNumberMetric("temperature_c", "Temperature", "C");
device.addIntegerMetric("sample_count", "Sample count");
device.addBooleanMetric("occupied", "Occupied");
device.addStringMetric("air_quality", "Air quality");
```

Metric keys must begin with a lowercase letter and contain only lowercase
letters, digits, and underscores.

### Step 6 — Register supported commands

Register only commands that your hardware implements:

```cpp
device.onSetLed(handleSetLed);
device.enableReportingInterval(5);
device.onDiagnostics(collectDiagnostics);
```

`handleSetLed` and `collectDiagnostics` are callback functions supplied by your
application.

DeviceOps protocol v1 supports only `set_led`, `set_reporting_interval`, and
`request_diagnostics`. Arbitrary command names are not currently supported.
The LED and diagnostics callbacks perform application-specific work. The client
validates each command and publishes its signed acknowledgement.

### Step 7 — Start DeviceOps

After Wi-Fi is connected and all capabilities are registered, call:

```cpp
bool clientStarted = device.begin();
```

`begin()` returns `false` for invalid configuration or when it cannot establish
a valid UTC clock. An initial broker failure is retried later by `loop()`.

### Step 8 — Call `device.loop()`

Call this frequently from the Arduino `loop()` function:

```cpp
device.loop();
```

It processes MQTT traffic, incoming commands, acknowledgements, and reconnect
attempts. Long blocking work in the application can delay those operations.

### Step 9 — Publish telemetry

One telemetry sample can contain multiple registered scalar values:

```cpp
JsonDocument sample;
sample["temperature_c"] = readTemperature();
sample["sample_count"] = sampleCount;
sample["occupied"] = isOccupied();
sample["air_quality"] = currentAirQuality();
device.publishTelemetry(sample.as<JsonObjectConst>());
```

Publish only after `connected()` returns `true`. Use
`reportingIntervalSeconds()` if the device advertises the reporting-interval
command.

### Step 10 — Confirm the integration

Open the device in DeviceOps. It should become **Online**, show every published
metric, create charts for numeric values, and show only the controls registered
by the firmware.

## Complete hosted example

```cpp
#include <ArduinoJson.h>
#include <DeviceOpsClient.h>
#include <WiFi.h>

#include "secrets.h"

DeviceOpsClient device(DEVICE_ID, DEVICE_SECRET);
bool clientStarted = false;
unsigned long lastSampleMs = 0;

void setup() {
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    while (WiFi.status() != WL_CONNECTED) delay(250);

    device.addNumberMetric("temperature_c", "Temperature", "C");
    clientStarted = device.begin();
}

void loop() {
    if (!clientStarted) return;
    device.loop();

    if (!device.connected() || millis() - lastSampleMs < 5000UL) return;
    lastSampleMs = millis();

    JsonDocument sample;
    sample["temperature_c"] = readMyTemperatureSensor();
    device.publishTelemetry(sample.as<JsonObjectConst>());
}
```

Call `publishTelemetry()` once per sample with all current scalar metrics in one
JSON object. `end()` publishes a signed retained offline status before a
deliberate disconnect.

## Public API

| API | Purpose |
| --- | --- |
| `DeviceOpsClient(id, secret)` | Create a hosted client for `mqtt.deviceops.net:443` with verified TLS. |
| `DeviceOpsClient(id, secret, transport)` | Use an explicit `DeviceOpsTransport`, currently hosted or local. |
| `addNumberMetric`, `addIntegerMetric` | Advertise an ordered numeric scalar, with an optional unit. |
| `addBooleanMetric`, `addStringMetric` | Advertise an ordered non-numeric scalar. |
| `onSetLed(handler, label)` | Advertise and handle protocol-v1 `set_led`. |
| `enableReportingInterval(default, namespace, key, label)` | Advertise, validate, and persist `set_reporting_interval`. |
| `onDiagnostics(handler, label)` | Advertise and handle `request_diagnostics`. |
| `begin()` | Validate configuration, establish UTC, prepare identity/session state, and start MQTT. |
| `loop()` | Service MQTT traffic and bounded reconnect attempts; call frequently. |
| `end()` | Publish retained offline presence and disconnect deliberately. |
| `syncClock(timeoutMs)` | Re-establish valid UTC after application-managed Wi-Fi recovery. |
| `publishTelemetry(metrics)` | Validate and publish one signed scalar sample. |
| `publishCapabilities()` | Republish the current signed retained manifest. |
| `connected()` | Report current MQTT connection state. |
| `reportingIntervalSeconds()` | Read the current persisted reporting interval. |
| `sessionId()` | Read the current boot-session identifier. |
| `runAuthenticationSelfTest()` | Run fixed derivation/signature vectors without real credentials. |

Register metrics and commands before `begin()`. Publish only registered scalar
keys. The client has fixed manifest and MQTT buffer limits; failed registration
or publish calls return `false` and should be handled by the application.

After Wi-Fi loss, continue calling `loop()`. If the application reconnects
Wi-Fi after a long outage, call `syncClock()` before expecting publishes to
resume. One boot session is retained across MQTT reconnects; a reset creates a
new session.

## Protocol-v1 commands

The three supported command registrations behave as follows:

- `onSetLed(handler)` validates `{ "on": boolean }`; the handler changes the
  hardware and adds safe result fields.
- `enableReportingInterval()` validates the 1–60 second range and persists the
  current value in ESP32 NVS. Application code schedules sensor work using
  `reportingIntervalSeconds()`.
- `onDiagnostics(handler)` lets the application add device-specific diagnostic
  fields without building an acknowledgement envelope itself.

Handlers use this signature:

```cpp
bool handler(JsonObjectConst arguments, JsonObject result, String& error);
```

Return `true` after applying the operation and populate `result`. Return `false`
and set a concise `error` if it fails. The client publishes the complete signed
succeeded/failed acknowledgement.

## Local development

Local mode is explicit and does not alter hosted TLS:

```cpp
DeviceOpsClient device(
    DEVICE_ID,
    DEVICE_SECRET,
    DeviceOpsTransport::local("192.168.1.100")
);
```

It uses anonymous plaintext MQTT on port 1883 while retaining signed DeviceOps
message envelopes. A LAN address identifies the development computer on the
local network. Use that address for the ESP32, not `localhost`, which means the
ESP32 itself.

`runAuthenticationSelfTest()` verifies fixed signing-key, message-signature,
and broker-password interoperability vectors without real credentials.

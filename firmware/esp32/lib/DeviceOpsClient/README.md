# DeviceOpsClient

`DeviceOpsClient` is the reusable DeviceOps protocol and MQTT client for ESP32
Arduino firmware. It is packaged as a conventional PlatformIO project library
and currently targets ESP32 with the Arduino framework.

The application owns Wi-Fi credentials and connection, sensor/GPIO setup,
hardware reads, unit conversion, and command side effects. The client owns UTC
clock synchronization, hosted TLS/MQTT, derived broker authentication, signed
DeviceOps envelopes, topics, sessions, presence, capabilities, telemetry
sequence numbers, command verification, acknowledgements, and reconnects.

The `firmware/esp32` project discovers the library automatically from
`lib/DeviceOpsClient`. To use it in another PlatformIO project, copy that
complete directory into the target project's `lib/DeviceOpsClient` directory;
its `library.json` declares the MQTT and ArduinoJson dependencies. Include it
with `#include <DeviceOpsClient.h>`.

## Minimal hosted setup

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

    device.addNumberMetric("temperature_c", "Temperature", "°C");
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

Hosted mode always uses `mqtt.deviceops.net:443`, verified TLS, and the device
ID as MQTT username and client ID. The broker password and message-signing key
are derived locally from the one-time DeviceOps device secret.

Keep the device secret in an ignored local header or another device-appropriate
secret store. Do not commit it, print it, or pass derived credentials into
application logs. The client does not send the plaintext secret in MQTT
payloads.

Call `device.loop()` frequently. Call `publishTelemetry()` once per sample with
all current scalar metrics in one JSON object. Register every published metric
before `begin()` with `addNumberMetric()`, `addIntegerMetric()`,
`addBooleanMetric()`, or `addStringMetric()`.

`begin()` returns `false` for invalid identity/transport configuration or when a
valid UTC clock cannot be established. An initial broker failure is retried by
`loop()`; use `connected()` before producing telemetry. `end()` publishes a
signed retained offline status before a deliberate disconnect.

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

Register metrics and commands before `begin()`. Metric keys must start with a
lowercase letter and contain only lowercase letters, digits, and underscores.
Publish only registered scalar keys, grouped into one JSON object per sample.
The client has fixed manifest and MQTT buffer limits; failed registration or
publish calls return `false` and should be handled by the application.

After Wi-Fi loss, continue calling `loop()`. If the application reconnects
Wi-Fi after a long outage, call `syncClock()` before expecting publishes to
resume. A single boot session is retained across MQTT reconnects; constructing
the client after a reset creates a new session.

## Protocol-v1 commands

The client deliberately supports only the commands accepted by DeviceOps v1:

- `onSetLed(handler)` registers the `set_led` capability. The client validates
  `{ "on": boolean }`; the handler changes hardware and adds safe result fields.
- `enableReportingInterval()` registers `set_reporting_interval`, validates the
  1–60 second range, and persists the current value in ESP32 NVS. Application
  code schedules its sensor work using `reportingIntervalSeconds()`.
- `onDiagnostics(handler)` registers `request_diagnostics`. The handler adds
  device-specific diagnostics without encoding an acknowledgement envelope.

Handlers use this signature:

```cpp
bool handler(JsonObjectConst arguments, JsonObject result, String& error);
```

Return `true` after applying the operation and populate `result`. Return `false`
and set a concise `error` if the hardware operation fails. The client publishes
the signed succeeded/failed acknowledgement.

## Local development

Local mode is explicit and does not alter hosted TLS:

```cpp
DeviceOpsClient device(
    DEVICE_ID,
    DEVICE_SECRET,
    DeviceOpsTransport::local("192.168.1.100")
);
```

It uses anonymous plaintext MQTT on port 1883 by default while retaining signed
DeviceOps message envelopes. Use a LAN address reachable by the ESP32, not
`localhost`.

`runAuthenticationSelfTest()` verifies the fixed signing-key, message-signature,
and broker-password interoperability vectors without real credentials.

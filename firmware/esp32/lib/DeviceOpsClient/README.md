# DeviceOpsClient

`DeviceOpsClient` is the reusable DeviceOps protocol and MQTT client for ESP32
Arduino firmware. It is packaged as a conventional PlatformIO project library.

The application owns Wi-Fi credentials and connection, sensor/GPIO setup,
hardware reads, unit conversion, and command side effects. The client owns UTC
clock synchronization, hosted TLS/MQTT, derived broker authentication, signed
DeviceOps envelopes, topics, sessions, presence, capabilities, telemetry
sequence numbers, command verification, acknowledgements, and reconnects.

## Minimal hosted setup

```cpp
#include <ArduinoJson.h>
#include <DeviceOpsClient.h>
#include <WiFi.h>

DeviceOpsClient device(DEVICE_ID, DEVICE_SECRET);

void setup() {
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    while (WiFi.status() != WL_CONNECTED) delay(250);

    device.addNumberMetric("temperature_c", "Temperature", "°C");
    device.begin();
}

void loop() {
    device.loop();

    JsonDocument sample;
    sample["temperature_c"] = readMyTemperatureSensor();
    device.publishTelemetry(sample.as<JsonObjectConst>());
}
```

Hosted mode always uses `mqtt.deviceops.net:443`, verified TLS, and the device
ID as MQTT username and client ID. The broker password and message-signing key
are derived locally from the one-time DeviceOps device secret.

Call `device.loop()` frequently. Call `publishTelemetry()` once per sample with
all current scalar metrics in one JSON object. Register every published metric
before `begin()` with `addNumberMetric()`, `addIntegerMetric()`,
`addBooleanMetric()`, or `addStringMetric()`.

`begin()` returns `false` for invalid identity/transport configuration or when a
valid UTC clock cannot be established. An initial broker failure is retried by
`loop()`; use `connected()` before producing telemetry. `end()` publishes a
signed retained offline status before a deliberate disconnect.

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

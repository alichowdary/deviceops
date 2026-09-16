#include <Arduino.h>
#include <Adafruit_BME280.h>
#include <Adafruit_NeoPixel.h>
#include <Adafruit_Sensor.h>
#include <ArduinoJson.h>
#include <MQTT.h>
#include <WiFi.h>
#include <Wire.h>
#include <time.h>

#include "secrets.h"


namespace {

constexpr char DEVICE_ID[] = "esp32-001";
constexpr uint16_t MQTT_PORT = 1883;

constexpr char STATUS_TOPIC[] = "deviceops/v1/devices/esp32-001/status";
constexpr char TELEMETRY_TOPIC[] = "deviceops/v1/devices/esp32-001/telemetry";
constexpr char COMMAND_TOPIC[] = "deviceops/v1/devices/esp32-001/commands";
constexpr char COMMAND_ACK_TOPIC[] =
    "deviceops/v1/devices/esp32-001/command-acks";

constexpr uint8_t I2C_SDA = 8;
constexpr uint8_t I2C_SCL = 9;
constexpr uint8_t BME280_I2C_ADDRESS = 0x76;
constexpr uint8_t RGB_LED_PIN = 48;
constexpr unsigned long DEFAULT_TELEMETRY_INTERVAL_MS = 5000;

WiFiClient network;
MQTTClient mqttClient(1024);
Adafruit_BME280 bme;
Adafruit_NeoPixel rgbLed(1, RGB_LED_PIN, NEO_GRB + NEO_KHZ800);

bool bmeReady = false;
bool ledOn = false;
unsigned long lastTelemetryPublish = 0;
unsigned long telemetryIntervalMs = DEFAULT_TELEMETRY_INTERVAL_MS;
uint32_t telemetrySequence = 0;


void setLed(bool on) {
    ledOn = on;

    if (on) {
        rgbLed.setPixelColor(0, rgbLed.Color(0, 50, 0));
        Serial.println("Physical RGB LED -> ON");
    } else {
        rgbLed.clear();
        Serial.println("Physical RGB LED -> OFF");
    }

    rgbLed.show();
}


void connectWiFi() {
    Serial.print("Connecting to Wi-Fi");
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }

    Serial.println();
    Serial.println("Wi-Fi connected!");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
    Serial.print("Signal strength: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
}


void syncClock() {
    Serial.print("Synchronizing UTC clock");
    configTime(0, 0, "pool.ntp.org", "time.nist.gov");

    time_t now = time(nullptr);
    int attempts = 0;
    while (now < 1700000000 && attempts < 30) {
        delay(500);
        Serial.print(".");
        now = time(nullptr);
        attempts++;
    }

    Serial.println();
    if (now < 1700000000) {
        Serial.println("WARNING: NTP sync failed.");
    } else {
        Serial.println("UTC clock synchronized.");
    }
}


bool getUtcTimestamp(char* buffer, size_t bufferSize) {
    const time_t now = time(nullptr);
    if (now < 1700000000) {
        return false;
    }

    struct tm utcTime;
    gmtime_r(&now, &utcTime);
    strftime(buffer, bufferSize, "%Y-%m-%dT%H:%M:%SZ", &utcTime);
    return true;
}


bool publishAckDocument(JsonDocument& document) {
    char payload[768];
    const size_t payloadLength =
        serializeJson(document, payload, sizeof(payload));

    if (payloadLength == 0) {
        Serial.println("ACK JSON serialization failed.");
        return false;
    }

    if (!mqttClient.publish(COMMAND_ACK_TOPIC, payload, false, 1)) {
        Serial.println("Failed to publish command ACK.");
        return false;
    }

    return true;
}


void publishCommandAck(
    const char* commandId,
    const char* status,
    bool includeLedResult = false,
    int intervalResult = -1,
    const char* errorMessage = nullptr
) {
    char timestamp[32];
    if (!getUtcTimestamp(timestamp, sizeof(timestamp))) {
        Serial.println("Cannot ACK command: UTC clock unavailable.");
        return;
    }

    JsonDocument document;
    document["protocol_version"] = 1;
    document["command_id"] = commandId;
    document["device_id"] = DEVICE_ID;
    document["sent_at"] = timestamp;
    document["status"] = status;

    JsonObject result = document["result"].to<JsonObject>();
    if (includeLedResult) {
        result["on"] = ledOn;
    }
    if (intervalResult >= 0) {
        result["interval_s"] = intervalResult;
    }
    if (errorMessage != nullptr) {
        result["error"] = errorMessage;
    }

    if (publishAckDocument(document)) {
        Serial.print("Published command ACK: ");
        Serial.println(status);
    }
}


void publishDiagnosticsAck(const char* commandId) {
    char timestamp[32];
    if (!getUtcTimestamp(timestamp, sizeof(timestamp))) {
        Serial.println("Cannot ACK diagnostics: UTC clock unavailable.");
        return;
    }

    JsonDocument document;
    document["protocol_version"] = 1;
    document["command_id"] = commandId;
    document["device_id"] = DEVICE_ID;
    document["sent_at"] = timestamp;
    document["status"] = "succeeded";

    JsonObject result = document["result"].to<JsonObject>();
    result["led_on"] = ledOn;
    result["reporting_interval_s"] = telemetryIntervalMs / 1000UL;
    result["uptime_s"] = millis() / 1000UL;
    result["rssi_dbm"] = WiFi.RSSI();
    result["bme280_ready"] = bmeReady;

    if (bmeReady) {
        result["temperature_c"] = bme.readTemperature();
        result["humidity_pct"] = bme.readHumidity();
        result["pressure_hpa"] = bme.readPressure() / 100.0F;
    }

    if (publishAckDocument(document)) {
        Serial.println("Published diagnostics ACK: succeeded");
        Serial.print("LED: ");
        Serial.println(ledOn ? "ON" : "OFF");
        Serial.print("Reporting interval: ");
        Serial.print(telemetryIntervalMs / 1000UL);
        Serial.println(" s");
        Serial.print("Uptime: ");
        Serial.print(millis() / 1000UL);
        Serial.println(" s");
        Serial.print("RSSI: ");
        Serial.print(WiFi.RSSI());
        Serial.println(" dBm");

        if (bmeReady) {
            Serial.print("Temperature: ");
            Serial.print(bme.readTemperature(), 2);
            Serial.println(" C");
            Serial.print("Humidity: ");
            Serial.print(bme.readHumidity(), 2);
            Serial.println(" %");
            Serial.print("Pressure: ");
            Serial.print(bme.readPressure() / 100.0F, 2);
            Serial.println(" hPa");
        }
    }
}


void handleCommand(String& topic, String& payload) {
    if (topic != COMMAND_TOPIC) {
        return;
    }

    Serial.println();
    Serial.println("Received DeviceOps command:");
    Serial.println(payload);

    JsonDocument document;
    const DeserializationError error = deserializeJson(document, payload);
    if (error) {
        Serial.print("Invalid command JSON: ");
        Serial.println(error.c_str());
        return;
    }

    const int protocolVersion = document["protocol_version"] | -1;
    const char* commandId = document["command_id"] | "";
    const char* deviceId = document["device_id"] | "";
    const char* commandType = document["type"] | "";

    if (strlen(commandId) == 0) {
        Serial.println("Command missing command_id.");
        return;
    }

    if (protocolVersion != 1) {
        publishCommandAck(
            commandId, "failed", false, -1, "unsupported protocol version"
        );
        return;
    }

    if (strcmp(deviceId, DEVICE_ID) != 0) {
        publishCommandAck(commandId, "failed", false, -1, "device_id mismatch");
        return;
    }

    if (strcmp(commandType, "set_led") == 0) {
        JsonObject arguments = document["arguments"].as<JsonObject>();
        if (arguments.isNull() || !arguments["on"].is<bool>()) {
            publishCommandAck(
                commandId,
                "failed",
                false,
                -1,
                "set_led requires boolean argument 'on'"
            );
            return;
        }

        setLed(arguments["on"].as<bool>());
        publishCommandAck(commandId, "succeeded", true);
        return;
    }

    if (strcmp(commandType, "set_reporting_interval") == 0) {
        JsonObject arguments = document["arguments"].as<JsonObject>();
        if (arguments.isNull() || !arguments["interval_s"].is<int>()) {
            publishCommandAck(
                commandId,
                "failed",
                false,
                -1,
                "set_reporting_interval requires integer interval_s"
            );
            return;
        }

        const int requestedInterval = arguments["interval_s"].as<int>();
        if (requestedInterval < 1 || requestedInterval > 60) {
            publishCommandAck(
                commandId,
                "failed",
                false,
                -1,
                "interval_s must be between 1 and 60"
            );
            return;
        }

        telemetryIntervalMs =
            static_cast<unsigned long>(requestedInterval) * 1000UL;
        lastTelemetryPublish = millis();
        Serial.print("Reporting interval -> ");
        Serial.print(requestedInterval);
        Serial.println(" seconds");
        publishCommandAck(commandId, "succeeded", false, requestedInterval);
        return;
    }

    if (strcmp(commandType, "request_diagnostics") == 0) {
        Serial.println("Collecting device diagnostics...");
        publishDiagnosticsAck(commandId);
        return;
    }

    publishCommandAck(
        commandId, "failed", false, -1, "unsupported command type"
    );
}


void connectMqtt() {
    Serial.print("Connecting to MQTT");

    while (!mqttClient.connected()) {
        if (mqttClient.connect(DEVICE_ID)) {
            Serial.println();
            Serial.println("MQTT connected!");

            if (mqttClient.subscribe(COMMAND_TOPIC, 1)) {
                Serial.println("Subscribed to DeviceOps command topic.");
            } else {
                Serial.println("Failed to subscribe to command topic.");
            }

            if (mqttClient.publish(STATUS_TOPIC, "online", true, 1)) {
                Serial.println("Published retained ONLINE status.");
            } else {
                Serial.println("Failed to publish ONLINE status.");
            }
        } else {
            Serial.print(".");
            delay(1000);
        }
    }
}


void publishTelemetry() {
    if (!bmeReady || !mqttClient.connected()) {
        return;
    }

    char timestamp[32];
    if (!getUtcTimestamp(timestamp, sizeof(timestamp))) {
        Serial.println("Skipping telemetry: clock not synchronized.");
        return;
    }

    const float temperature = bme.readTemperature();
    const float humidity = bme.readHumidity();
    const float pressure = bme.readPressure() / 100.0F;
    const int rssi = WiFi.RSSI();
    const uint32_t uptimeSeconds = millis() / 1000UL;
    telemetrySequence++;

    JsonDocument document;
    document["protocol_version"] = 1;
    document["device_id"] = DEVICE_ID;
    document["sent_at"] = timestamp;
    document["sequence"] = telemetrySequence;

    JsonObject metrics = document["metrics"].to<JsonObject>();
    metrics["temperature_c"] = temperature;
    metrics["humidity_pct"] = humidity;
    metrics["pressure_hpa"] = pressure;
    metrics["rssi_dbm"] = rssi;
    metrics["uptime_s"] = uptimeSeconds;

    char payload[512];
    const size_t payloadLength =
        serializeJson(document, payload, sizeof(payload));
    if (payloadLength == 0) {
        Serial.println("Telemetry JSON serialization failed.");
        return;
    }

    if (!mqttClient.publish(TELEMETRY_TOPIC, payload, false, 0)) {
        Serial.println("Telemetry MQTT publish failed.");
        return;
    }

    Serial.println();
    Serial.println("Published DeviceOps telemetry:");
    Serial.print("Sequence: ");
    Serial.println(telemetrySequence);
    Serial.print("Temperature: ");
    Serial.print(temperature, 2);
    Serial.println(" C");
    Serial.print("Humidity: ");
    Serial.print(humidity, 2);
    Serial.println(" %");
    Serial.print("Pressure: ");
    Serial.print(pressure, 2);
    Serial.println(" hPa");
    Serial.print("RSSI: ");
    Serial.print(rssi);
    Serial.println(" dBm");
    Serial.print("Uptime: ");
    Serial.print(uptimeSeconds);
    Serial.println(" s");
    Serial.print("Reporting interval: ");
    Serial.print(telemetryIntervalMs / 1000UL);
    Serial.println(" s");
    Serial.print("Timestamp: ");
    Serial.println(timestamp);
}

}  // namespace


void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println();
    Serial.println("DeviceOps ESP32 hardware integration");
    Serial.println();

    rgbLed.begin();
    rgbLed.clear();
    rgbLed.show();
    setLed(false);

    Wire.begin(I2C_SDA, I2C_SCL);
    Serial.println("Initializing BME280...");
    if (bme.begin(BME280_I2C_ADDRESS, &Wire)) {
        bmeReady = true;
        Serial.println("BME280 initialized!");
    } else {
        Serial.println("BME280 initialization FAILED.");
    }
    Serial.println();

    connectWiFi();
    syncClock();

    mqttClient.begin(MQTT_BROKER, MQTT_PORT, network);
    mqttClient.onMessage(handleCommand);
    mqttClient.setWill(STATUS_TOPIC, "offline", true, 1);
    mqttClient.setKeepAlive(5);
    connectMqtt();

    Serial.println();
}


void loop() {
    mqttClient.loop();
    delay(10);

    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("Wi-Fi disconnected. Reconnecting...");
        connectWiFi();
        syncClock();
    }

    if (!mqttClient.connected()) {
        Serial.println("MQTT disconnected. Reconnecting...");
        connectMqtt();
    }

    if (millis() - lastTelemetryPublish >= telemetryIntervalMs) {
        lastTelemetryPublish = millis();
        publishTelemetry();
    }
}

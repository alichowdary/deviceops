#include <Arduino.h>
#include <Adafruit_BME280.h>
#include <Adafruit_NeoPixel.h>
#include <Adafruit_Sensor.h>
#include <ArduinoJson.h>
#include <MQTT.h>
#include <Preferences.h>
#include <WiFi.h>
#include <Wire.h>
#include <time.h>

#include <cstring>

#include "mqtt_auth.h"
#include "secrets.h"


namespace {

constexpr uint16_t MQTT_PORT = 1883;
constexpr size_t TOPIC_BUFFER_SIZE = 128;
constexpr size_t MQTT_BUFFER_SIZE = 3072;

constexpr uint8_t I2C_SDA = 8;
constexpr uint8_t I2C_SCL = 9;
constexpr uint8_t BME280_I2C_ADDRESS = 0x76;
constexpr uint8_t RGB_LED_PIN = 48;
constexpr unsigned long DEFAULT_TELEMETRY_INTERVAL_MS = 5000;
constexpr uint32_t MIN_TELEMETRY_INTERVAL_S = 1;
constexpr uint32_t MAX_TELEMETRY_INTERVAL_S = 60;
constexpr char CONFIG_NAMESPACE[] = "deviceops";
constexpr char REPORTING_INTERVAL_KEY[] = "report_s";

WiFiClient network;
MQTTClient mqttClient(MQTT_BUFFER_SIZE);
Adafruit_BME280 bme;
Adafruit_NeoPixel rgbLed(1, RGB_LED_PIN, NEO_GRB + NEO_KHZ800);

char statusTopic[TOPIC_BUFFER_SIZE];
char telemetryTopic[TOPIC_BUFFER_SIZE];
char commandTopic[TOPIC_BUFFER_SIZE];
char commandAckTopic[TOPIC_BUFFER_SIZE];
char capabilitiesTopic[TOPIC_BUFFER_SIZE];
char bootSessionId[mqtt_auth::SESSION_ID_HEX_SIZE + 1];
uint8_t signingKey[mqtt_auth::SIGNING_KEY_SIZE];
String offlineEnvelope;

bool bmeReady = false;
bool ledOn = false;
unsigned long lastTelemetryPublish = 0;
unsigned long telemetryIntervalMs = DEFAULT_TELEMETRY_INTERVAL_MS;
uint32_t telemetrySequence = 0;


bool isReportingIntervalValid(uint32_t intervalSeconds) {
    return
        intervalSeconds >= MIN_TELEMETRY_INTERVAL_S &&
        intervalSeconds <= MAX_TELEMETRY_INTERVAL_S;
}


void loadReportingInterval() {
    uint32_t intervalSeconds = DEFAULT_TELEMETRY_INTERVAL_MS / 1000UL;
    bool loadedPersistedInterval = false;
    Preferences preferences;

    if (preferences.begin(CONFIG_NAMESPACE, false)) {
        if (preferences.isKey(REPORTING_INTERVAL_KEY)) {
            const uint32_t savedInterval =
                preferences.getUInt(REPORTING_INTERVAL_KEY, 0);
            if (isReportingIntervalValid(savedInterval)) {
                intervalSeconds = savedInterval;
                loadedPersistedInterval = true;
            }
        }
        preferences.end();
    }

    telemetryIntervalMs =
        static_cast<unsigned long>(intervalSeconds) * 1000UL;
    Serial.print("Reporting interval: ");
    Serial.print(intervalSeconds);
    Serial.println(
        loadedPersistedInterval ? " s (persisted)" : " s (default)"
    );
}


bool persistReportingInterval(uint32_t intervalSeconds) {
    Preferences preferences;
    if (!preferences.begin(CONFIG_NAMESPACE, false)) {
        return false;
    }

    const size_t bytesWritten =
        preferences.putUInt(REPORTING_INTERVAL_KEY, intervalSeconds);
    preferences.end();
    return bytesWritten == sizeof(intervalSeconds);
}


bool isDeviceIdValid(const char* value) {
    if (value == nullptr) {
        return false;
    }

    const size_t length = strlen(value);
    if (length == 0 || length > 64) {
        return false;
    }

    const auto isLetterOrDigit = [](char character) {
        return
            (character >= 'A' && character <= 'Z') ||
            (character >= 'a' && character <= 'z') ||
            (character >= '0' && character <= '9');
    };
    if (!isLetterOrDigit(value[0])) {
        return false;
    }

    for (size_t index = 1; index < length; index++) {
        const char character = value[index];
        if (!isLetterOrDigit(character) && character != '.' &&
            character != '_' && character != '-') {
            return false;
        }
    }
    return true;
}


bool buildTopic(char* output, size_t outputSize, const char* suffix) {
    const int written = snprintf(
        output,
        outputSize,
        "deviceops/v1/devices/%s/%s",
        DEVICE_ID,
        suffix
    );
    return written > 0 && static_cast<size_t>(written) < outputSize;
}


bool initializeDeviceAuthentication() {
    if (!isDeviceIdValid(DEVICE_ID)) {
        Serial.println("Invalid DEVICE_ID configuration.");
        return false;
    }
    if (DEVICE_SECRET[0] == '\0') {
        Serial.println("DEVICE_SECRET must not be empty.");
        return false;
    }
    if (WIFI_SSID[0] == '\0' || MQTT_BROKER[0] == '\0') {
        Serial.println("Wi-Fi SSID and MQTT broker must not be empty.");
        return false;
    }
    if (
        !buildTopic(statusTopic, sizeof(statusTopic), "status") ||
        !buildTopic(telemetryTopic, sizeof(telemetryTopic), "telemetry") ||
        !buildTopic(commandTopic, sizeof(commandTopic), "commands") ||
        !buildTopic(capabilitiesTopic, sizeof(capabilitiesTopic), "capabilities") ||
        !buildTopic(
            commandAckTopic,
            sizeof(commandAckTopic),
            "command-acks"
        )
    ) {
        Serial.println("Device MQTT topic construction failed.");
        return false;
    }
    if (!mqtt_auth::deriveSigningKey(DEVICE_SECRET, signingKey)) {
        Serial.println("MQTT signing-key derivation failed.");
        return false;
    }
    return true;
}


bool createAuthenticatedPayload(
    const String& body,
    mqtt_auth::Direction direction,
    const char* topic,
    String& envelope
) {
    if (!mqtt_auth::createEnvelope(
            body,
            signingKey,
            direction,
            topic,
            bootSessionId,
            envelope
        )) {
        Serial.println("MQTT authenticated-envelope creation failed.");
        return false;
    }
    return true;
}


bool publishAuthenticated(
    const char* topic,
    const String& body,
    bool retained,
    int qos
) {
    String envelope;
    if (!createAuthenticatedPayload(
            body,
            mqtt_auth::Direction::DeviceToServer,
            topic,
            envelope
        )) {
        return false;
    }
    return mqttClient.publish(topic, envelope, retained, qos);
}


void haltStartup() {
    Serial.println("Firmware startup halted.");
    while (true) {
        delay(1000);
    }
}


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
    String body;
    body.reserve(768);
    const size_t payloadLength = serializeJson(document, body);

    if (payloadLength == 0) {
        Serial.println("ACK JSON serialization failed.");
        return false;
    }

    if (!publishAuthenticated(commandAckTopic, body, false, 1)) {
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
    if (topic != commandTopic) {
        return;
    }

    Serial.println();
    Serial.println("Received DeviceOps command envelope.");

    mqtt_auth::Envelope envelope;
    if (!mqtt_auth::parseEnvelope(payload, envelope)) {
        Serial.println("Rejected command: invalid authentication envelope.");
        return;
    }
    if (envelope.sessionId != bootSessionId) {
        Serial.println("Rejected command: MQTT session mismatch.");
        return;
    }
    if (!mqtt_auth::verifyEnvelope(
            envelope,
            signingKey,
            mqtt_auth::Direction::ServerToDevice,
            commandTopic
        )) {
        Serial.println("Rejected command: invalid signature.");
        return;
    }

    JsonDocument document;
    const DeserializationError error =
        deserializeJson(document, envelope.body);
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
        if (
            requestedInterval < static_cast<int>(MIN_TELEMETRY_INTERVAL_S) ||
            requestedInterval > static_cast<int>(MAX_TELEMETRY_INTERVAL_S)
        ) {
            publishCommandAck(
                commandId,
                "failed",
                false,
                -1,
                "interval_s must be between 1 and 60"
            );
            return;
        }

        if (!persistReportingInterval(
                static_cast<uint32_t>(requestedInterval)
            )) {
            Serial.println("Failed to persist reporting interval.");
            publishCommandAck(
                commandId,
                "failed",
                false,
                -1,
                "failed to persist reporting interval"
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


bool publishCapabilities() {
    char timestamp[32];
    if (!getUtcTimestamp(timestamp, sizeof(timestamp))) {
        Serial.println("Cannot publish capabilities: UTC clock unavailable.");
        return false;
    }

    JsonDocument document;
    document["protocol_version"] = 1;
    document["capabilities_version"] = 1;
    document["device_id"] = DEVICE_ID;
    document["sent_at"] = timestamp;

    JsonObject telemetry = document["telemetry"].to<JsonObject>();
    JsonObject temperature = telemetry["temperature_c"].to<JsonObject>();
    temperature["type"] = "number";
    temperature["label"] = "Temperature";
    temperature["unit"] = "°C";
    JsonObject humidity = telemetry["humidity_pct"].to<JsonObject>();
    humidity["type"] = "number";
    humidity["label"] = "Humidity";
    humidity["unit"] = "%";
    JsonObject pressure = telemetry["pressure_hpa"].to<JsonObject>();
    pressure["type"] = "number";
    pressure["label"] = "Pressure";
    pressure["unit"] = "hPa";
    JsonObject rssi = telemetry["rssi_dbm"].to<JsonObject>();
    rssi["type"] = "integer";
    rssi["label"] = "RSSI";
    rssi["unit"] = "dBm";
    JsonObject uptime = telemetry["uptime_s"].to<JsonObject>();
    uptime["type"] = "integer";
    uptime["label"] = "Uptime";
    uptime["unit"] = "s";

    JsonObject commands = document["commands"].to<JsonObject>();
    JsonObject setLed = commands["set_led"].to<JsonObject>();
    setLed["label"] = "LED";
    JsonObject ledArguments = setLed["arguments"].to<JsonObject>();
    JsonObject on = ledArguments["on"].to<JsonObject>();
    on["type"] = "boolean";
    on["label"] = "On";

    JsonObject setInterval =
        commands["set_reporting_interval"].to<JsonObject>();
    setInterval["label"] = "Reporting interval";
    JsonObject intervalArguments =
        setInterval["arguments"].to<JsonObject>();
    JsonObject interval = intervalArguments["interval_s"].to<JsonObject>();
    interval["type"] = "integer";
    interval["label"] = "Interval";
    interval["unit"] = "s";
    interval["min"] = MIN_TELEMETRY_INTERVAL_S;
    interval["max"] = MAX_TELEMETRY_INTERVAL_S;

    JsonObject diagnostics =
        commands["request_diagnostics"].to<JsonObject>();
    diagnostics["label"] = "Request diagnostics";
    diagnostics["arguments"].to<JsonObject>();

    String body;
    body.reserve(1400);
    if (serializeJson(document, body) == 0) {
        Serial.println("Capabilities JSON serialization failed.");
        return false;
    }
    if (!publishAuthenticated(capabilitiesTopic, body, true, 1)) {
        Serial.println("Capabilities MQTT publish failed.");
        return false;
    }
    Serial.println("Published retained device capabilities.");
    return true;
}


void connectMqtt() {
    Serial.print("Connecting to MQTT");

    while (!mqttClient.connected()) {
        if (mqttClient.connect(DEVICE_ID)) {
            Serial.println();
            Serial.println("MQTT connected!");

            if (mqttClient.subscribe(commandTopic, 1)) {
                Serial.println("Subscribed to DeviceOps command topic.");

                if (publishAuthenticated(statusTopic, "online", true, 1)) {
                    Serial.println("Published retained ONLINE status.");
                    publishCapabilities();
                } else {
                    Serial.println("Failed to publish ONLINE status.");
                }
            } else {
                Serial.println("Failed to subscribe to command topic.");
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

    String body;
    body.reserve(512);
    const size_t payloadLength = serializeJson(document, body);
    if (payloadLength == 0) {
        Serial.println("Telemetry JSON serialization failed.");
        return;
    }

    if (!publishAuthenticated(telemetryTopic, body, false, 0)) {
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

    loadReportingInterval();

    if (mqtt_auth::runInteroperabilitySelfTest()) {
        Serial.println("MQTT auth self-test: PASS");
    } else {
        Serial.println("MQTT auth self-test: FAIL");
        haltStartup();
    }
    if (!initializeDeviceAuthentication()) {
        haltStartup();
    }

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

    mqtt_auth::generateBootSessionId(bootSessionId);
    if (!createAuthenticatedPayload(
            "offline",
            mqtt_auth::Direction::DeviceToServer,
            statusTopic,
            offlineEnvelope
        )) {
        haltStartup();
    }

    mqttClient.begin(MQTT_BROKER, MQTT_PORT, network);
    mqttClient.onMessage(handleCommand);
    mqttClient.setWill(statusTopic, offlineEnvelope.c_str(), true, 1);
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

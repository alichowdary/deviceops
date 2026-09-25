#include "DeviceOpsClient.h"

#include <WiFi.h>
#include <time.h>

#include <cmath>
#include <cstring>

#include "isrg_root_x1.h"
#include "mqtt_auth.h"


namespace {

constexpr char HOSTED_MQTT_BROKER[] = "mqtt.deviceops.net";
constexpr uint16_t HOSTED_MQTT_PORT = 443;
constexpr time_t MIN_VALID_UTC = 1700000000;


bool isLetterOrDigit(char character) {
    return
        (character >= 'A' && character <= 'Z') ||
        (character >= 'a' && character <= 'z') ||
        (character >= '0' && character <= '9');
}


bool isDeviceIdValid(const char* value) {
    if (value == nullptr) {
        return false;
    }

    const size_t length = strlen(value);
    if (length == 0 || length > 64 || !isLetterOrDigit(value[0])) {
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


bool isCapabilityIdentifierValid(const char* value) {
    if (value == nullptr) {
        return false;
    }

    const size_t length = strlen(value);
    if (length == 0 || length > 64 ||
        !((value[0] >= 'a' && value[0] <= 'z'))) {
        return false;
    }

    for (size_t index = 1; index < length; index++) {
        const char character = value[index];
        if (!(
                (character >= 'a' && character <= 'z') ||
                (character >= '0' && character <= '9') ||
                character == '_'
            )) {
            return false;
        }
    }
    return true;
}


bool isTextLengthValid(
    const char* value,
    size_t maximum,
    bool optional = false
) {
    if (value == nullptr) {
        return optional;
    }
    const size_t length = strlen(value);
    return (optional || length > 0) && length <= maximum;
}


bool isUuidV4(const char* value) {
    if (value == nullptr || strlen(value) != 36) {
        return false;
    }

    for (size_t index = 0; index < 36; index++) {
        if (index == 8 || index == 13 || index == 18 || index == 23) {
            if (value[index] != '-') {
                return false;
            }
            continue;
        }
        if (!(
                (value[index] >= '0' && value[index] <= '9') ||
                (value[index] >= 'a' && value[index] <= 'f')
            )) {
            return false;
        }
    }

    return
        value[14] == '4' &&
        (value[19] == '8' || value[19] == '9' ||
         value[19] == 'a' || value[19] == 'b');
}

}  // namespace


DeviceOpsTransport DeviceOpsTransport::hosted() {
    return {Mode::Hosted, HOSTED_MQTT_BROKER, HOSTED_MQTT_PORT};
}


DeviceOpsTransport DeviceOpsTransport::local(
    const char* host,
    uint16_t port
) {
    return {Mode::Local, host == nullptr ? "" : host, port};
}


DeviceOpsClient::DeviceOpsClient(
    const char* deviceId,
    const char* deviceSecret
) : DeviceOpsClient(
        deviceId,
        deviceSecret,
        DeviceOpsTransport::hosted()
    ) {}


DeviceOpsClient::DeviceOpsClient(
    const char* deviceId,
    const char* deviceSecret,
    DeviceOpsTransport transport
) :
    deviceId_(deviceId == nullptr ? "" : deviceId),
    deviceSecret_(deviceSecret == nullptr ? "" : deviceSecret),
    transport_(transport),
    mqttClient_(MQTT_BUFFER_SIZE),
    reportingIntervalSeconds_(5),
    telemetrySequence_(0),
    lastReconnectAttemptMs_(0),
    reportingIntervalEnabled_(false),
    initialized_(false) {
    memset(statusTopic_, 0, sizeof(statusTopic_));
    memset(telemetryTopic_, 0, sizeof(telemetryTopic_));
    memset(commandTopic_, 0, sizeof(commandTopic_));
    memset(commandAckTopic_, 0, sizeof(commandAckTopic_));
    memset(capabilitiesTopic_, 0, sizeof(capabilitiesTopic_));
    memset(bootSessionId_, 0, sizeof(bootSessionId_));
    memset(signingKey_, 0, sizeof(signingKey_));
    memset(brokerPassword_, 0, sizeof(brokerPassword_));
    capabilities_["telemetry"].to<JsonObject>();
    capabilities_["commands"].to<JsonObject>();
}


DeviceOpsClient::~DeviceOpsClient() {
    deviceSecret_ = "";
    memset(signingKey_, 0, sizeof(signingKey_));
    memset(brokerPassword_, 0, sizeof(brokerPassword_));
}


bool DeviceOpsClient::addMetric(
    const char* key,
    const char* label,
    const char* type,
    const char* unit
) {
    if (
        initialized_ || !isCapabilityIdentifierValid(key) ||
        !isTextLengthValid(label, 80) ||
        !isTextLengthValid(unit, 24, true)
    ) {
        return false;
    }

    const String metricKey(key);
    JsonObject telemetry = capabilities_["telemetry"].as<JsonObject>();
    JsonObjectConst existingTelemetry = telemetry;
    if (!existingTelemetry[metricKey].isNull() || telemetry.size() >= 128) {
        return false;
    }

    JsonObject descriptor = telemetry[metricKey].to<JsonObject>();
    descriptor["type"] = type;
    descriptor["label"] = String(label);
    if (unit != nullptr) {
        descriptor["unit"] = String(unit);
    }
    return true;
}


bool DeviceOpsClient::addNumberMetric(
    const char* key,
    const char* label,
    const char* unit
) {
    return addMetric(key, label, "number", unit);
}


bool DeviceOpsClient::addIntegerMetric(
    const char* key,
    const char* label,
    const char* unit
) {
    return addMetric(key, label, "integer", unit);
}


bool DeviceOpsClient::addBooleanMetric(
    const char* key,
    const char* label
) {
    return addMetric(key, label, "boolean", nullptr);
}


bool DeviceOpsClient::addStringMetric(
    const char* key,
    const char* label
) {
    return addMetric(key, label, "string", nullptr);
}


bool DeviceOpsClient::addCommandCapability(
    const char* command,
    const char* label
) {
    if (initialized_ || !isTextLengthValid(label, 80)) {
        return false;
    }

    JsonObject commands = capabilities_["commands"].as<JsonObject>();
    JsonObjectConst existingCommands = commands;
    if (!existingCommands[command].isNull()) {
        return false;
    }
    JsonObject descriptor = commands[command].to<JsonObject>();
    descriptor["label"] = String(label);
    descriptor["arguments"].to<JsonObject>();
    return true;
}


bool DeviceOpsClient::onSetLed(
    CommandHandler handler,
    const char* label
) {
    if (!handler || !addCommandCapability("set_led", label)) {
        return false;
    }

    JsonObject argument =
        capabilities_["commands"]["set_led"]["arguments"]["on"]
            .to<JsonObject>();
    argument["type"] = "boolean";
    argument["label"] = "On";
    setLedHandler_ = handler;
    return true;
}


bool DeviceOpsClient::enableReportingInterval(
    uint32_t defaultSeconds,
    const char* preferencesNamespace,
    const char* preferencesKey,
    const char* label
) {
    if (
        defaultSeconds < MIN_REPORTING_INTERVAL_S ||
        defaultSeconds > MAX_REPORTING_INTERVAL_S ||
        !isTextLengthValid(preferencesNamespace, 15) ||
        !isTextLengthValid(preferencesKey, 15) ||
        !addCommandCapability("set_reporting_interval", label)
    ) {
        return false;
    }

    preferencesNamespace_ = preferencesNamespace;
    preferencesKey_ = preferencesKey;
    if (!loadReportingInterval(defaultSeconds)) {
        return false;
    }

    JsonObject argument =
        capabilities_["commands"]["set_reporting_interval"]
            ["arguments"]["interval_s"].to<JsonObject>();
    argument["type"] = "integer";
    argument["label"] = "Interval";
    argument["unit"] = "s";
    argument["min"] = MIN_REPORTING_INTERVAL_S;
    argument["max"] = MAX_REPORTING_INTERVAL_S;
    reportingIntervalEnabled_ = true;
    return true;
}


bool DeviceOpsClient::onDiagnostics(
    CommandHandler handler,
    const char* label
) {
    if (!handler || !addCommandCapability("request_diagnostics", label)) {
        return false;
    }
    diagnosticsHandler_ = handler;
    return true;
}


bool DeviceOpsClient::buildTopic(
    char* output,
    size_t outputSize,
    const char* suffix
) const {
    const int written = snprintf(
        output,
        outputSize,
        "deviceops/v1/devices/%s/%s",
        deviceId_.c_str(),
        suffix
    );
    return written > 0 && static_cast<size_t>(written) < outputSize;
}


bool DeviceOpsClient::initializeIdentity() {
    if (
        !isDeviceIdValid(deviceId_.c_str()) || deviceSecret_.length() == 0 ||
        transport_.host.length() == 0 ||
        transport_.port == 0
    ) {
        Serial.println("Invalid DeviceOps client configuration.");
        return false;
    }

    if (
        !buildTopic(statusTopic_, sizeof(statusTopic_), "status") ||
        !buildTopic(telemetryTopic_, sizeof(telemetryTopic_), "telemetry") ||
        !buildTopic(commandTopic_, sizeof(commandTopic_), "commands") ||
        !buildTopic(
            commandAckTopic_,
            sizeof(commandAckTopic_),
            "command-acks"
        ) ||
        !buildTopic(
            capabilitiesTopic_,
            sizeof(capabilitiesTopic_),
            "capabilities"
        )
    ) {
        Serial.println("DeviceOps topic construction failed.");
        return false;
    }

    if (!mqtt_auth::deriveSigningKey(deviceSecret_.c_str(), signingKey_)) {
        Serial.println("DeviceOps signing-key derivation failed.");
        return false;
    }
    if (
        transport_.mode == DeviceOpsTransport::Mode::Hosted &&
        !mqtt_auth::deriveBrokerPassword(signingKey_, brokerPassword_)
    ) {
        Serial.println("DeviceOps broker-password derivation failed.");
        return false;
    }
    deviceSecret_ = "";
    return true;
}


bool DeviceOpsClient::syncClock(uint32_t timeoutMs) {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("Cannot synchronize UTC clock without Wi-Fi.");
        return false;
    }

    Serial.print("Synchronizing UTC clock");
    configTime(0, 0, "pool.ntp.org", "time.nist.gov");
    const unsigned long startedAt = millis();
    while (
        time(nullptr) < MIN_VALID_UTC &&
        millis() - startedAt < timeoutMs
    ) {
        delay(500);
        Serial.print(".");
    }
    Serial.println();

    if (time(nullptr) < MIN_VALID_UTC) {
        Serial.println("UTC clock synchronization failed.");
        return false;
    }
    Serial.println("UTC clock synchronized.");
    return true;
}


bool DeviceOpsClient::getUtcTimestamp(
    char* buffer,
    size_t bufferSize
) const {
    const time_t now = time(nullptr);
    if (now < MIN_VALID_UTC) {
        return false;
    }

    struct tm utcTime;
    gmtime_r(&now, &utcTime);
    return strftime(
               buffer,
               bufferSize,
               "%Y-%m-%dT%H:%M:%SZ",
               &utcTime
           ) > 0;
}


bool DeviceOpsClient::begin() {
    if (initialized_) {
        return true;
    }
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("Connect Wi-Fi before DeviceOpsClient::begin().");
        return false;
    }
    if (!initializeIdentity() || !syncClock()) {
        return false;
    }

    mqtt_auth::generateBootSessionId(bootSessionId_);
    if (!mqtt_auth::createEnvelope(
            "offline",
            signingKey_,
            mqtt_auth::Direction::DeviceToServer,
            statusTopic_,
            bootSessionId_,
            offlineEnvelope_
        )) {
        Serial.println("DeviceOps Last Will creation failed.");
        return false;
    }

    if (transport_.mode == DeviceOpsTransport::Mode::Hosted) {
        Serial.println("MQTT mode: hosted DeviceOps with verified TLS");
        secureNetwork_.setCACert(ISRG_ROOT_X1);
        mqttClient_.begin(
            transport_.host.c_str(),
            transport_.port,
            secureNetwork_
        );
    } else {
        Serial.print("MQTT mode: local plaintext at ");
        Serial.print(transport_.host);
        Serial.print(":");
        Serial.println(transport_.port);
        mqttClient_.begin(
            transport_.host.c_str(),
            transport_.port,
            plaintextNetwork_
        );
    }

    mqttClient_.onMessage(
        [this](String& topic, String& payload) {
            handleCommand(topic, payload);
        }
    );
    mqttClient_.setWill(statusTopic_, offlineEnvelope_.c_str(), true, 1);
    mqttClient_.setKeepAlive(5);
    initialized_ = true;
    connectMqtt();
    return true;
}


bool DeviceOpsClient::connectMqtt() {
    if (!initialized_ || WiFi.status() != WL_CONNECTED) {
        return false;
    }
    if (mqttClient_.connected()) {
        return true;
    }

    lastReconnectAttemptMs_ = millis();
    Serial.print("Connecting to MQTT at ");
    Serial.print(transport_.host);
    Serial.print(":");
    Serial.println(transport_.port);

    const bool connected =
        transport_.mode == DeviceOpsTransport::Mode::Hosted
            ? mqttClient_.connect(
                deviceId_.c_str(),
                deviceId_.c_str(),
                brokerPassword_
            )
            : mqttClient_.connect(deviceId_.c_str());
    if (!connected) {
        Serial.print("MQTT connection failed: lastError=");
        Serial.print(static_cast<int>(mqttClient_.lastError()));
        Serial.print(" returnCode=");
        Serial.println(static_cast<int>(mqttClient_.returnCode()));
        return false;
    }

    Serial.println("MQTT connected.");
    if (!mqttClient_.subscribe(commandTopic_, 1)) {
        Serial.println("DeviceOps command subscription failed.");
        mqttClient_.disconnect();
        return false;
    }

    if (!publishAuthenticated(statusTopic_, "online", true, 1)) {
        Serial.println("DeviceOps ONLINE publish failed.");
        mqttClient_.disconnect();
        return false;
    }
    Serial.println("Published retained ONLINE status.");
    return publishCapabilities();
}


void DeviceOpsClient::loop() {
    if (!initialized_) {
        return;
    }

    mqttClient_.loop();
    if (WiFi.status() != WL_CONNECTED || mqttClient_.connected()) {
        return;
    }

    if (millis() - lastReconnectAttemptMs_ >= 1000UL) {
        connectMqtt();
    }
}


void DeviceOpsClient::end() {
    if (!initialized_) {
        return;
    }
    if (mqttClient_.connected()) {
        if (publishAuthenticated(statusTopic_, "offline", true, 1)) {
            mqttClient_.loop();
            delay(20);
        }
        mqttClient_.disconnect();
    }
}


bool DeviceOpsClient::publishAuthenticated(
    const char* topic,
    const String& body,
    bool retained,
    int qos
) {
    if (!mqttClient_.connected()) {
        return false;
    }

    String envelope;
    if (!mqtt_auth::createEnvelope(
            body,
            signingKey_,
            mqtt_auth::Direction::DeviceToServer,
            topic,
            bootSessionId_,
            envelope
        )) {
        Serial.println("DeviceOps envelope creation failed.");
        return false;
    }
    return mqttClient_.publish(topic, envelope, retained, qos);
}


bool DeviceOpsClient::publishCapabilities() {
    if (!initialized_ || !mqttClient_.connected()) {
        return false;
    }

    char timestamp[32];
    if (!getUtcTimestamp(timestamp, sizeof(timestamp))) {
        Serial.println("Cannot publish capabilities: UTC clock unavailable.");
        return false;
    }

    JsonDocument document;
    document["protocol_version"] = 1;
    document["capabilities_version"] = 1;
    document["device_id"] = deviceId_;
    document["sent_at"] = timestamp;
    document["telemetry"] = capabilities_["telemetry"];
    document["commands"] = capabilities_["commands"];

    String body;
    body.reserve(1536);
    if (serializeJson(document, body) == 0) {
        Serial.println("Capabilities JSON serialization failed.");
        return false;
    }
    if (!publishAuthenticated(capabilitiesTopic_, body, true, 1)) {
        Serial.println("Capabilities MQTT publish failed.");
        return false;
    }
    Serial.println("Published retained device capabilities.");
    return true;
}


bool DeviceOpsClient::publishTelemetry(JsonObjectConst metrics) {
    if (!initialized_ || !mqttClient_.connected() || metrics.size() == 0) {
        return false;
    }

    JsonObjectConst registered =
        capabilities_["telemetry"].as<JsonObjectConst>();
    for (JsonPairConst metric : metrics) {
        JsonVariantConst value = metric.value();
        if (
            registered[metric.key().c_str()].isNull() || value.isNull() ||
            value.is<JsonObjectConst>() || value.is<JsonArrayConst>()
        ) {
            Serial.println("Telemetry contains an undeclared or nonscalar metric.");
            return false;
        }
        if (value.is<double>() && !std::isfinite(value.as<double>())) {
            Serial.println("Telemetry contains a non-finite numeric value.");
            return false;
        }
    }

    char timestamp[32];
    if (!getUtcTimestamp(timestamp, sizeof(timestamp))) {
        Serial.println("Skipping telemetry: UTC clock unavailable.");
        return false;
    }

    JsonDocument document;
    document["protocol_version"] = 1;
    document["device_id"] = deviceId_;
    document["sent_at"] = timestamp;
    document["sequence"] = ++telemetrySequence_;
    document["metrics"] = metrics;

    String body;
    body.reserve(768);
    if (serializeJson(document, body) == 0) {
        Serial.println("Telemetry JSON serialization failed.");
        return false;
    }
    if (!publishAuthenticated(telemetryTopic_, body, false, 0)) {
        Serial.println("Telemetry MQTT publish failed.");
        return false;
    }
    return true;
}


bool DeviceOpsClient::publishAcknowledgement(
    const char* commandId,
    const char* status,
    JsonObjectConst result
) {
    char timestamp[32];
    if (!getUtcTimestamp(timestamp, sizeof(timestamp))) {
        Serial.println("Cannot ACK command: UTC clock unavailable.");
        return false;
    }

    JsonDocument document;
    document["protocol_version"] = 1;
    document["command_id"] = commandId;
    document["device_id"] = deviceId_;
    document["sent_at"] = timestamp;
    document["status"] = status;
    document["result"] = result;

    String body;
    body.reserve(768);
    if (serializeJson(document, body) == 0) {
        return false;
    }
    if (!publishAuthenticated(commandAckTopic_, body, false, 1)) {
        Serial.println("Command ACK publish failed.");
        return false;
    }
    Serial.print("Published command ACK: ");
    Serial.println(status);
    return true;
}


void DeviceOpsClient::publishFailure(
    const char* commandId,
    const char* message
) {
    JsonDocument resultDocument;
    resultDocument["error"] = message;
    publishAcknowledgement(
        commandId,
        "failed",
        resultDocument.as<JsonObjectConst>()
    );
}


void DeviceOpsClient::handleCommand(String& topic, String& payload) {
    if (topic != commandTopic_) {
        return;
    }

    mqtt_auth::Envelope envelope;
    if (!mqtt_auth::parseEnvelope(payload, envelope)) {
        Serial.println("Rejected command: invalid authentication envelope.");
        return;
    }
    if (envelope.sessionId != bootSessionId_) {
        Serial.println("Rejected command: session mismatch.");
        return;
    }
    if (!mqtt_auth::verifyEnvelope(
            envelope,
            signingKey_,
            mqtt_auth::Direction::ServerToDevice,
            commandTopic_
        )) {
        Serial.println("Rejected command: invalid signature.");
        return;
    }

    JsonDocument document;
    if (deserializeJson(document, envelope.body)) {
        Serial.println("Rejected command: invalid JSON.");
        return;
    }

    JsonObjectConst object = document.as<JsonObjectConst>();
    const char* commandId = object["command_id"] | "";
    if (!isUuidV4(commandId)) {
        Serial.println("Rejected command: invalid command_id.");
        return;
    }
    if (
        object["protocol_version"].is<bool>() ||
        !object["protocol_version"].is<int>() ||
        object["protocol_version"].as<int>() != 1
    ) {
        publishFailure(commandId, "unsupported protocol version");
        return;
    }
    if (strcmp(object["device_id"] | "", deviceId_.c_str()) != 0) {
        publishFailure(commandId, "device_id mismatch");
        return;
    }
    const char* issuedAt = object["issued_at"] | "";
    if (issuedAt[0] == '\0') {
        publishFailure(commandId, "issued_at is required");
        return;
    }

    const char* commandType = object["type"] | "";
    JsonObjectConst arguments = object["arguments"].as<JsonObjectConst>();
    if (arguments.isNull()) {
        publishFailure(commandId, "arguments must be an object");
        return;
    }

    if (strcmp(commandType, "set_led") == 0) {
        if (
            !setLedHandler_ || arguments.size() != 1 ||
            !arguments["on"].is<bool>()
        ) {
            publishFailure(
                commandId,
                setLedHandler_
                    ? "set_led requires exactly {'on': boolean}"
                    : "set_led is not supported"
            );
            return;
        }

        JsonDocument resultDocument;
        String error;
        if (!setLedHandler_(
                arguments,
                resultDocument.to<JsonObject>(),
                error
            )) {
            publishFailure(
                commandId,
                error.length() == 0 ? "set_led failed" : error.c_str()
            );
            return;
        }
        publishAcknowledgement(
            commandId,
            "succeeded",
            resultDocument.as<JsonObjectConst>()
        );
        return;
    }

    if (strcmp(commandType, "set_reporting_interval") == 0) {
        if (
            !reportingIntervalEnabled_ || arguments.size() != 1 ||
            arguments["interval_s"].is<bool>() ||
            !arguments["interval_s"].is<int>()
        ) {
            publishFailure(
                commandId,
                reportingIntervalEnabled_
                    ? "set_reporting_interval requires exactly {'interval_s': integer}"
                    : "set_reporting_interval is not supported"
            );
            return;
        }

        const int interval = arguments["interval_s"].as<int>();
        if (
            interval < static_cast<int>(MIN_REPORTING_INTERVAL_S) ||
            interval > static_cast<int>(MAX_REPORTING_INTERVAL_S)
        ) {
            publishFailure(commandId, "interval_s must be between 1 and 60");
            return;
        }
        if (!persistReportingInterval(static_cast<uint32_t>(interval))) {
            publishFailure(commandId, "failed to persist reporting interval");
            return;
        }

        reportingIntervalSeconds_ = static_cast<uint32_t>(interval);
        JsonDocument resultDocument;
        resultDocument["interval_s"] = interval;
        publishAcknowledgement(
            commandId,
            "succeeded",
            resultDocument.as<JsonObjectConst>()
        );
        return;
    }

    if (strcmp(commandType, "request_diagnostics") == 0) {
        if (!diagnosticsHandler_ || arguments.size() != 0) {
            publishFailure(
                commandId,
                diagnosticsHandler_
                    ? "request_diagnostics arguments must be empty"
                    : "request_diagnostics is not supported"
            );
            return;
        }

        JsonDocument resultDocument;
        String error;
        if (!diagnosticsHandler_(
                arguments,
                resultDocument.to<JsonObject>(),
                error
            )) {
            publishFailure(
                commandId,
                error.length() == 0
                    ? "request_diagnostics failed"
                    : error.c_str()
            );
            return;
        }
        publishAcknowledgement(
            commandId,
            "succeeded",
            resultDocument.as<JsonObjectConst>()
        );
        return;
    }

    publishFailure(commandId, "unsupported command type");
}


bool DeviceOpsClient::loadReportingInterval(uint32_t defaultSeconds) {
    reportingIntervalSeconds_ = defaultSeconds;
    Preferences preferences;
    if (!preferences.begin(preferencesNamespace_.c_str(), true)) {
        Serial.println("Reporting interval NVS unavailable; using default.");
        return true;
    }

    if (preferences.isKey(preferencesKey_.c_str())) {
        const uint32_t saved =
            preferences.getUInt(preferencesKey_.c_str(), defaultSeconds);
        if (
            saved >= MIN_REPORTING_INTERVAL_S &&
            saved <= MAX_REPORTING_INTERVAL_S
        ) {
            reportingIntervalSeconds_ = saved;
        }
    }
    preferences.end();

    Serial.print("Reporting interval: ");
    Serial.print(reportingIntervalSeconds_);
    Serial.println(" s");
    return true;
}


bool DeviceOpsClient::persistReportingInterval(uint32_t intervalSeconds) {
    Preferences preferences;
    if (!preferences.begin(preferencesNamespace_.c_str(), false)) {
        return false;
    }
    const size_t bytesWritten = preferences.putUInt(
        preferencesKey_.c_str(),
        intervalSeconds
    );
    preferences.end();
    return bytesWritten == sizeof(intervalSeconds);
}


bool DeviceOpsClient::connected() {
    return initialized_ && mqttClient_.connected();
}


uint32_t DeviceOpsClient::reportingIntervalSeconds() const {
    return reportingIntervalSeconds_;
}


const char* DeviceOpsClient::sessionId() const {
    return bootSessionId_;
}


bool DeviceOpsClient::runAuthenticationSelfTest() {
    return mqtt_auth::runInteroperabilitySelfTest();
}

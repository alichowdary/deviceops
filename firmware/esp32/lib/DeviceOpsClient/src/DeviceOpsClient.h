#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>
#include <MQTT.h>
#include <Preferences.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>

#include <cstdint>
#include <functional>


struct DeviceOpsTransport {
    enum class Mode : uint8_t {
        Hosted,
        Local,
    };

    Mode mode;
    String host;
    uint16_t port;

    static DeviceOpsTransport hosted();
    static DeviceOpsTransport local(const char* host, uint16_t port = 1883);
};


class DeviceOpsClient {
public:
    using CommandHandler =
        std::function<bool(JsonObjectConst, JsonObject, String&)>;

    DeviceOpsClient(const char* deviceId, const char* deviceSecret);
    DeviceOpsClient(
        const char* deviceId,
        const char* deviceSecret,
        DeviceOpsTransport transport
    );
    ~DeviceOpsClient();

    DeviceOpsClient(const DeviceOpsClient&) = delete;
    DeviceOpsClient& operator=(const DeviceOpsClient&) = delete;

    bool addNumberMetric(
        const char* key,
        const char* label,
        const char* unit = nullptr
    );
    bool addIntegerMetric(
        const char* key,
        const char* label,
        const char* unit = nullptr
    );
    bool addBooleanMetric(const char* key, const char* label);
    bool addStringMetric(const char* key, const char* label);

    bool onSetLed(CommandHandler handler, const char* label = "LED");
    bool enableReportingInterval(
        uint32_t defaultSeconds = 5,
        const char* preferencesNamespace = "deviceops",
        const char* preferencesKey = "report_s",
        const char* label = "Reporting interval"
    );
    bool onDiagnostics(
        CommandHandler handler,
        const char* label = "Request diagnostics"
    );

    bool begin();
    void loop();
    void end();

    bool syncClock(uint32_t timeoutMs = 15000);
    bool publishTelemetry(JsonObjectConst metrics);
    bool publishCapabilities();

    bool connected();
    uint32_t reportingIntervalSeconds() const;
    const char* sessionId() const;

    static bool runAuthenticationSelfTest();

private:
    static constexpr size_t TOPIC_BUFFER_SIZE = 128;
    static constexpr size_t MQTT_BUFFER_SIZE = 3072;
    static constexpr uint32_t MIN_REPORTING_INTERVAL_S = 1;
    static constexpr uint32_t MAX_REPORTING_INTERVAL_S = 60;

    bool addMetric(
        const char* key,
        const char* label,
        const char* type,
        const char* unit
    );
    bool addCommandCapability(
        const char* command,
        const char* label
    );
    bool initializeIdentity();
    bool buildTopic(char* output, size_t outputSize, const char* suffix) const;
    bool getUtcTimestamp(char* buffer, size_t bufferSize) const;
    bool connectMqtt();
    void handleCommand(String& topic, String& payload);
    bool publishAuthenticated(
        const char* topic,
        const String& body,
        bool retained,
        int qos
    );
    bool publishAcknowledgement(
        const char* commandId,
        const char* status,
        JsonObjectConst result
    );
    void publishFailure(const char* commandId, const char* message);
    bool loadReportingInterval(uint32_t defaultSeconds);
    bool persistReportingInterval(uint32_t intervalSeconds);

    String deviceId_;
    String deviceSecret_;
    DeviceOpsTransport transport_;
    WiFiClient plaintextNetwork_;
    WiFiClientSecure secureNetwork_;
    MQTTClient mqttClient_;
    JsonDocument capabilities_;
    CommandHandler setLedHandler_;
    CommandHandler diagnosticsHandler_;
    String preferencesNamespace_;
    String preferencesKey_;
    char statusTopic_[TOPIC_BUFFER_SIZE];
    char telemetryTopic_[TOPIC_BUFFER_SIZE];
    char commandTopic_[TOPIC_BUFFER_SIZE];
    char commandAckTopic_[TOPIC_BUFFER_SIZE];
    char capabilitiesTopic_[TOPIC_BUFFER_SIZE];
    char bootSessionId_[33];
    uint8_t signingKey_[32];
    char brokerPassword_[65];
    String offlineEnvelope_;
    uint32_t reportingIntervalSeconds_;
    uint32_t telemetrySequence_;
    unsigned long lastReconnectAttemptMs_;
    bool reportingIntervalEnabled_;
    bool initialized_;
};

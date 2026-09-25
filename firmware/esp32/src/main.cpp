#include <Arduino.h>
#include <Adafruit_BME280.h>
#include <Adafruit_NeoPixel.h>
#include <Adafruit_Sensor.h>
#include <ArduinoJson.h>
#include <DeviceOpsClient.h>
#include <WiFi.h>
#include <Wire.h>

#include "secrets.h"


#if defined(DEVICEOPS_LOCAL_MQTT) && !defined(DEVICEOPS_LOCAL_MQTT_BROKER)
#error "DEVICEOPS_LOCAL_MQTT_BROKER is required in local mode"
#endif


namespace {

constexpr uint8_t I2C_SDA = 8;
constexpr uint8_t I2C_SCL = 9;
constexpr uint8_t BME280_I2C_ADDRESS = 0x76;
constexpr uint8_t RGB_LED_PIN = 48;
constexpr uint32_t DEFAULT_REPORTING_INTERVAL_S = 5;

Adafruit_BME280 bme;
Adafruit_NeoPixel rgbLed(1, RGB_LED_PIN, NEO_GRB + NEO_KHZ800);

#if defined(DEVICEOPS_LOCAL_MQTT)
DeviceOpsClient device(
    DEVICE_ID,
    DEVICE_SECRET,
    DeviceOpsTransport::local(DEVICEOPS_LOCAL_MQTT_BROKER)
);
#else
DeviceOpsClient device(DEVICE_ID, DEVICE_SECRET);
#endif

bool bmeReady = false;
bool ledOn = false;
unsigned long lastTelemetryPublish = 0;
uint32_t lastReportingIntervalSeconds = DEFAULT_REPORTING_INTERVAL_S;


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
    } else {
        rgbLed.clear();
    }
    rgbLed.show();

    Serial.print("Physical RGB LED -> ");
    Serial.println(on ? "ON" : "OFF");
}


void connectWiFi() {
    Serial.print("Connecting to Wi-Fi");
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }

    Serial.println();
    Serial.println("Wi-Fi connected.");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
    Serial.print("Signal strength: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
}


bool handleSetLed(
    JsonObjectConst arguments,
    JsonObject result,
    String& error
) {
    (void)error;
    setLed(arguments["on"].as<bool>());
    result["on"] = ledOn;
    return true;
}


bool handleDiagnostics(
    JsonObjectConst arguments,
    JsonObject result,
    String& error
) {
    (void)arguments;
    (void)error;

    result["led_on"] = ledOn;
    result["reporting_interval_s"] = device.reportingIntervalSeconds();
    result["uptime_s"] = millis() / 1000UL;
    result["rssi_dbm"] = WiFi.RSSI();
    result["bme280_ready"] = bmeReady;
    if (bmeReady) {
        result["temperature_c"] = bme.readTemperature();
        result["humidity_pct"] = bme.readHumidity();
        result["pressure_hpa"] = bme.readPressure() / 100.0F;
    }
    return true;
}


bool configureDeviceOps() {
    return
        device.addNumberMetric("temperature_c", "Temperature", "°C") &&
        device.addNumberMetric("humidity_pct", "Humidity", "%") &&
        device.addNumberMetric("pressure_hpa", "Pressure", "hPa") &&
        device.addIntegerMetric("rssi_dbm", "RSSI", "dBm") &&
        device.addIntegerMetric("uptime_s", "Uptime", "s") &&
        device.onSetLed(handleSetLed) &&
        device.enableReportingInterval(DEFAULT_REPORTING_INTERVAL_S) &&
        device.onDiagnostics(handleDiagnostics);
}


void publishTelemetry() {
    if (!bmeReady || !device.connected()) {
        return;
    }

    const float temperature = bme.readTemperature();
    const float humidity = bme.readHumidity();
    const float pressure = bme.readPressure() / 100.0F;
    const int rssi = WiFi.RSSI();
    const uint32_t uptimeSeconds = millis() / 1000UL;

    JsonDocument metricsDocument;
    JsonObject metrics = metricsDocument.to<JsonObject>();
    metrics["temperature_c"] = temperature;
    metrics["humidity_pct"] = humidity;
    metrics["pressure_hpa"] = pressure;
    metrics["rssi_dbm"] = rssi;
    metrics["uptime_s"] = uptimeSeconds;

    if (!device.publishTelemetry(metrics)) {
        return;
    }

    Serial.println();
    Serial.println("Published DeviceOps telemetry:");
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
    Serial.print(device.reportingIntervalSeconds());
    Serial.println(" s");
}

}  // namespace


void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println();
    Serial.println("DeviceOps ESP32 hardware integration");
    Serial.println();

    if (DeviceOpsClient::runAuthenticationSelfTest()) {
        Serial.println("MQTT auth self-test: PASS");
    } else {
        Serial.println("MQTT auth self-test: FAIL");
        haltStartup();
    }

    rgbLed.begin();
    rgbLed.clear();
    rgbLed.show();
    setLed(false);

    Wire.begin(I2C_SDA, I2C_SCL);
    Serial.println("Initializing BME280...");
    bmeReady = bme.begin(BME280_I2C_ADDRESS, &Wire);
    Serial.println(bmeReady ? "BME280 initialized." : "BME280 initialization FAILED.");

    if (!configureDeviceOps()) {
        Serial.println("DeviceOps capability or command setup failed.");
        haltStartup();
    }

    connectWiFi();
    if (!device.begin()) {
        haltStartup();
    }

    lastReportingIntervalSeconds = device.reportingIntervalSeconds();
    lastTelemetryPublish = millis();
    Serial.println();
}


void loop() {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("Wi-Fi disconnected. Reconnecting...");
        connectWiFi();
        if (!device.syncClock()) {
            Serial.println("UTC clock unavailable after Wi-Fi reconnect.");
        }
    }

    device.loop();
    delay(10);

    const uint32_t reportingIntervalSeconds =
        device.reportingIntervalSeconds();
    if (reportingIntervalSeconds != lastReportingIntervalSeconds) {
        lastReportingIntervalSeconds = reportingIntervalSeconds;
        lastTelemetryPublish = millis();
        Serial.print("Reporting interval -> ");
        Serial.print(reportingIntervalSeconds);
        Serial.println(" seconds");
    }

    const unsigned long intervalMs =
        static_cast<unsigned long>(reportingIntervalSeconds) * 1000UL;
    if (millis() - lastTelemetryPublish >= intervalMs) {
        lastTelemetryPublish = millis();
        publishTelemetry();
    }
}

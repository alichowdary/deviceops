#pragma once

// Copy this file to secrets.h and replace these placeholders locally.
// firmware/esp32/include/secrets.h is ignored by Git.
constexpr char WIFI_SSID[] = "YOUR_WIFI_SSID";
constexpr char WIFI_PASSWORD[] = "YOUR_WIFI_PASSWORD";
constexpr char MQTT_BROKER[] = "YOUR_MQTT_BROKER_HOST";
constexpr uint16_t MQTT_PORT = 1883;
constexpr bool MQTT_TLS_ENABLED = false;
constexpr char MQTT_USERNAME[] = "";
constexpr char MQTT_PASSWORD[] = "";
constexpr char DEVICE_ID[] = "YOUR_REGISTERED_DEVICE_ID";
constexpr char DEVICE_SECRET[] = "YOUR_ONE_TIME_DEVICE_SECRET";

#pragma once

// Copy this file to secrets.h and replace these placeholders locally.
// firmware/esp32/include/secrets.h is ignored by Git.
constexpr char WIFI_SSID[] = "YOUR_WIFI_SSID";
constexpr char WIFI_PASSWORD[] = "YOUR_WIFI_PASSWORD";
constexpr char DEVICE_ID[] = "YOUR_REGISTERED_DEVICE_ID";
constexpr char DEVICE_SECRET[] = "YOUR_ONE_TIME_DEVICE_SECRET";

// Hosted DeviceOps at mqtt.deviceops.net:443 with verified TLS is the default.
// For explicit anonymous local development, uncomment the mode switch and set
// the development computer's LAN address. Do not use localhost or 127.0.0.1.
// #define DEVICEOPS_LOCAL_MQTT
// #define DEVICEOPS_LOCAL_MQTT_BROKER "192.168.1.100"

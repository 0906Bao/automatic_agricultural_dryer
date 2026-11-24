#pragma once

// Optional machine-local settings. This file must not be committed.
#if __has_include("secrets.local.h")
#include "secrets.local.h"
#endif

#ifndef WIFI_SSID
#define WIFI_SSID "Wokwi-GUEST"
#endif
#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD ""
#endif
#ifndef WIFI_CHANNEL
#define WIFI_CHANNEL 0
#endif

// Local Docker broker through the Wokwi Private IoT Gateway.
#ifndef MQTT_HOST
#define MQTT_HOST "host.wokwi.internal"
#endif
#ifndef MQTT_PORT
#define MQTT_PORT 1883
#endif
#ifndef MQTT_USER
#define MQTT_USER ""
#endif
#ifndef MQTT_PASSWORD
#define MQTT_PASSWORD ""
#endif

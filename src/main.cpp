#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include "secrets.h"
#include <PubSubClient.h>
#include "DHTesp.h"
#include <BlynkSimpleEsp32.h>

// Existing Wokwi wiring
constexpr uint8_t RAIN_PIN = 34;
constexpr uint8_t LDR_PIN = 35;
constexpr uint8_t DHT_PIN = 15;
constexpr uint8_t LIMIT_COVERED_PIN = 18;
constexpr uint8_t LIMIT_OPEN_PIN = 19;
constexpr uint8_t STATUS_LED_PIN = 23;

constexpr int RAIN_WET_THRESHOLD = 2200;
constexpr int DARK_THRESHOLD = 2200;
constexpr int BRIGHT_THRESHOLD = 1800;
constexpr uint32_t SAMPLE_INTERVAL_MS = 250;
constexpr uint32_t SENSOR_CONFIRM_MS = 500;
constexpr uint32_t SAFE_TO_OPEN_MS = 30000;
constexpr uint32_t REPORT_INTERVAL_MS = 1000;
constexpr uint32_t DHT_INTERVAL_MS = 2500;
constexpr uint32_t MQTT_RECONNECT_INTERVAL_MS = 5000;
constexpr uint32_t BLYNK_RECONNECT_INTERVAL_MS = 5000;
constexpr uint8_t AVERAGE_SAMPLES = 8;

// Humidity thresholds (%RH)
constexpr float HUMIDITY_WARNING_THRESHOLD = 70.0f;
constexpr float HUMIDITY_DANGER_THRESHOLD = 80.0f;

// Thời gian xác nhận điều kiện nguy hiểm
constexpr uint32_t HUMIDITY_CONFIRM_MS = 500;

bool dhtValid = false;

// Lý do che bạt để gửi lên dashboard
const char* coverReason = "NORMAL";

// MQTT topics
constexpr char TOPIC_TELEMETRY[] = "dryer/telemetry";
constexpr char TOPIC_STATUS[] = "dryer/status";
constexpr char TOPIC_AVAILABILITY[] = "dryer/availability";

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
DHTesp dht;
BlynkTimer blynkTimer;

bool isDark = false;
bool coverRequested = false;
bool coverConditionTiming = false;
bool safeConditionTiming = false;
bool blynkConfigured = false;
uint32_t coverConditionSince = 0;
uint32_t safeConditionSince = 0;
uint32_t lastSampleAt = 0;
uint32_t lastReportAt = 0;
uint32_t lastDhtAt = 0;
uint32_t lastMqttReconnectAt = 0;
uint32_t lastBlynkReconnectAt = 0;
int rainRaw = 0;
int lightRaw = 0;
bool isRaining = false;
float temperatureC = NAN;
float humidityPct = NAN;

int readAverage(uint8_t pin) {
  uint32_t total = 0;
  for (uint8_t i = 0; i < AVERAGE_SAMPLES; ++i) {
    total += analogRead(pin);
    delay(2);
  }
  return static_cast<int>(total / AVERAGE_SAMPLES);
}

void updateSensors() {
  rainRaw = readAverage(RAIN_PIN);
  lightRaw = readAverage(LDR_PIN);
  isRaining = rainRaw >= RAIN_WET_THRESHOLD;

  if (!isDark && lightRaw >= DARK_THRESHOLD) {
    isDark = true;
  } else if (isDark && lightRaw <= BRIGHT_THRESHOLD) {
    isDark = false;
  }
}

void updateCoverDecision(uint32_t now) {
  const bool humidityDanger =
      dhtValid &&
      humidityPct > HUMIDITY_DANGER_THRESHOLD;

  const bool humidityWarning =
      dhtValid &&
      humidityPct >= HUMIDITY_WARNING_THRESHOLD &&
      humidityPct <= HUMIDITY_DANGER_THRESHOLD;

  // Ưu tiên bảo vệ nông sản:
  // Mưa, trời tối, độ ẩm nguy hiểm hoặc DHT22 lỗi.
  const bool shouldCover =
      isRaining ||
      isDark ||
      humidityDanger ||
      !dhtValid;

  // Xác định lý do yêu cầu che bạt.
  if (isRaining) {
    coverReason = "RAIN";
  } else if (isDark) {
    coverReason = "DARK";
  } else if (!dhtValid) {
    coverReason = "DHT_ERROR";
  } else if (humidityDanger) {
    coverReason = "HUMIDITY_DANGER";
  } else if (humidityWarning) {
    coverReason = "HUMIDITY_WARNING";
  } else {
    coverReason = "NORMAL";
  }

  // Có điều kiện nguy hiểm: hủy bộ đếm mở bạt.
  if (shouldCover) {
    safeConditionTiming = false;

    if (!coverConditionTiming) {
      coverConditionTiming = true;
      coverConditionSince = now;
    }

    // Độ ẩm trên 80% hoặc lỗi DHT:
    // xác nhận nhanh, không chờ 30 giây.
    const uint32_t confirmTime =
        (humidityDanger || !dhtValid)
            ? HUMIDITY_CONFIRM_MS
            : SENSOR_CONFIRM_MS;

    if (!coverRequested &&
        now - coverConditionSince >= confirmTime) {
      coverRequested = true;

      Serial.printf(
        "ACTION: CLOSE COVER | reason=%s\n",
        coverReason
      );
    }

    return;
  }

  // Không có điều kiện nguy hiểm.
  coverConditionTiming = false;

  // Chỉ mở khi khô, sáng và độ ẩm dưới 70%.
  const bool safeToOpen =
      !isRaining &&
      !isDark &&
      dhtValid &&
      humidityPct < HUMIDITY_WARNING_THRESHOLD;

  if (coverRequested && safeToOpen) {
    if (!safeConditionTiming) {
      safeConditionTiming = true;
      safeConditionSince = now;

      Serial.println(
        "INFO: Conditions safe; waiting 30 seconds before opening"
      );
    }

    if (now - safeConditionSince >= SAFE_TO_OPEN_MS) {
      coverRequested = false;
      safeConditionTiming = false;

      Serial.println(
        "ACTION: OPEN COVER (dry, bright, humidity below 70%)"
      );
    }
  } else {
    safeConditionTiming = false;
  }

  if (humidityWarning) {
    // Chỉ cảnh báo, không tự đóng bạt nếu trời vẫn sáng
    // và không có mưa.
    Serial.println(
      "WARNING: Humidity 70-80%; drying efficiency may decrease"
    );
  }
}

void readDht() {
  TempAndHumidity data = dht.getTempAndHumidity();

  if (dht.getStatus() != 0 ||
      isnan(data.temperature) ||
      isnan(data.humidity) ||
      data.humidity < 0.0f ||
      data.humidity > 100.0f) {

    dhtValid = false;

    Serial.printf(
      "[DHT22] Invalid reading: %s\n",
      dht.getStatusString()
    );
    return;
  }

  temperatureC = data.temperature;
  humidityPct = data.humidity;
  dhtValid = true;

  Serial.printf(
    "[DHT22] Temperature: %.2f C | Humidity: %.2f %%\n",
    temperatureC,
    humidityPct
  );
}

void publishTelemetry() {
  if (!mqtt.connected()) return;

  char payload[384];

  snprintf(
    payload,
    sizeof(payload),
    "{\"rain_adc\":%d,"
    "\"light_adc\":%d,"
    "\"rain\":%s,"
    "\"dark\":%s,"
    "\"temperature_c\":%.2f,"
    "\"humidity_pct\":%.2f,"
    "\"dht_valid\":%s,"
    "\"humidity_warning\":%s,"
    "\"humidity_danger\":%s,"
    "\"cover_request\":\"%s\","
    "\"cover_reason\":\"%s\","
    "\"limit_covered\":%s,"
    "\"limit_open\":%s}",
    rainRaw,
    lightRaw,
    isRaining ? "true" : "false",
    isDark ? "true" : "false",
    dhtValid ? temperatureC : -999.0f,
    dhtValid ? humidityPct : -999.0f,
    dhtValid ? "true" : "false",
    (dhtValid &&
     humidityPct >= HUMIDITY_WARNING_THRESHOLD)
        ? "true" : "false",
    (dhtValid &&
     humidityPct > HUMIDITY_DANGER_THRESHOLD)
        ? "true" : "false",
    coverRequested ? "CLOSE" : "OPEN",
    coverReason,
    digitalRead(LIMIT_COVERED_PIN) == LOW
        ? "true" : "false",
    digitalRead(LIMIT_OPEN_PIN) == LOW
        ? "true" : "false"
  );

  mqtt.publish(TOPIC_TELEMETRY, payload, false);
}

void publishBlynk() {
  if (!Blynk.connected()) return;
  if (!isnan(temperatureC)) Blynk.virtualWrite(V0, temperatureC);
  if (!isnan(humidityPct)) Blynk.virtualWrite(V1, humidityPct);
  Blynk.virtualWrite(V2, rainRaw);
  Blynk.virtualWrite(V3, lightRaw);
  Blynk.virtualWrite(V4, isRaining ? 1 : 0);
  Blynk.virtualWrite(V5, isDark ? 1 : 0);
  Blynk.virtualWrite(V6, coverRequested ? 1 : 0);
}

void ensureMqttConnected(uint32_t now) {
  if (mqtt.connected() || WiFi.status() != WL_CONNECTED) return;
  if (now - lastMqttReconnectAt < MQTT_RECONNECT_INTERVAL_MS) return;
  lastMqttReconnectAt = now;

  String clientId = "agri-dryer-" + String((uint32_t)ESP.getEfuseMac(), HEX);
  bool connected;
  if (strlen(MQTT_USER) > 0) {
    connected = mqtt.connect(clientId.c_str(), MQTT_USER, MQTT_PASSWORD,
                             TOPIC_AVAILABILITY, 1, true, "offline");
  } else {
    connected = mqtt.connect(clientId.c_str(), TOPIC_AVAILABILITY, 1, true, "offline");
  }

  if (connected) {
    mqtt.publish(TOPIC_AVAILABILITY, "online", true);
    mqtt.publish(TOPIC_STATUS, "connected", true);
    Serial.println("MQTT: connected to broker");
  } else {
    Serial.printf("MQTT: connect failed, state=%d\n", mqtt.state());
  }
}

void ensureBlynkConnected(uint32_t now) {
  if (Blynk.connected() || WiFi.status() != WL_CONNECTED) return;
  if (now - lastBlynkReconnectAt < BLYNK_RECONNECT_INTERVAL_MS) return;
  lastBlynkReconnectAt = now;
  if (!blynkConfigured) return;
  Serial.println("Blynk: attempting connection...");
  bool connected = Blynk.connect(3000);

  Serial.printf(
      "Blynk connection result: %s\n",
      connected ? "SUCCESS" : "FAILED"
  );
}

void reportStatus(uint32_t now) {
  if (now - lastReportAt < REPORT_INTERVAL_MS) return;
  lastReportAt = now;
  Serial.printf("rain_adc=%d rain=%s | light_adc=%d dark=%s | temp=%.1fC humidity=%.1f%% | ",
                rainRaw, isRaining ? "YES" : "NO", lightRaw, isDark ? "YES" : "NO",
                temperatureC, humidityPct);
  Serial.printf("cover_request=%s | limit_covered=%s limit_open=%s | MQTT=%s Blynk=%s\n",
                coverRequested ? "CLOSE" : "OPEN",
                digitalRead(LIMIT_COVERED_PIN) == LOW ? "ACTIVE" : "inactive",
                digitalRead(LIMIT_OPEN_PIN) == LOW ? "ACTIVE" : "inactive",
                mqtt.connected() ? "online" : "offline",
                Blynk.connected() ? "online" : "offline");
}

void setup() {
  Serial.begin(115200);
  delay(100);

  Serial.printf(
      "Blynk token configured: %s\n",
      (strlen(BLYNK_AUTH_TOKEN) > 0 &&
      String(BLYNK_AUTH_TOKEN) != "YOUR_BLYNK_DEVICE_AUTH_TOKEN")
          ? "YES" : "NO"
  );

  
  Serial.println("\nAUTOMATIC AGRICULTURAL DRYER - MQTT + BLYNK");
  Serial.println("FIRMWARE VERSION: DEBUG-BLYNK-DHT-02");

  pinMode(RAIN_PIN, INPUT);
  pinMode(LDR_PIN, INPUT);
  pinMode(LIMIT_COVERED_PIN, INPUT_PULLUP);
  pinMode(LIMIT_OPEN_PIN, INPUT_PULLUP);
  pinMode(STATUS_LED_PIN, OUTPUT);
  analogReadResolution(12);

  dht.setup(DHT_PIN, DHTesp::DHT22);
  delay(2000);
  Serial.println("DHT22 initialized");

  WiFi.mode(WIFI_STA);
  WiFi.begin("Wokwi-GUEST", "", 6);
  Serial.print("WiFi: connecting to Wokwi-GUEST");
  const uint32_t wifiStart = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - wifiStart < 15000) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WiFi connected, IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("WiFi not connected yet; will continue trying in loop.");
  }

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(384);
  mqtt.setKeepAlive(30);

  if (String(BLYNK_AUTH_TOKEN) != "YOUR_BLYNK_DEVICE_AUTH_TOKEN" &&
      String(BLYNK_AUTH_TOKEN) != "") {
    Blynk.config(BLYNK_AUTH_TOKEN);
    blynkConfigured = true;
  } else {
    Serial.println("Blynk skipped: add a real Device Auth Token in include/secrets.h");
  }

  digitalWrite(STATUS_LED_PIN, HIGH);
  delay(2000);
  digitalWrite(STATUS_LED_PIN, LOW);
  Serial.printf("Thresholds: rain >= %d, dark >= %d, bright <= %d\n",
                RAIN_WET_THRESHOLD, DARK_THRESHOLD, BRIGHT_THRESHOLD);
  Serial.printf("MQTT target: %s:%d (requires Wokwi Private IoT Gateway for local Docker broker)\n",
                MQTT_HOST, MQTT_PORT);
}

void loop() {
  const uint32_t now = millis();

  if (WiFi.status() != WL_CONNECTED) {
    static uint32_t lastWifiRetry = 0;
    if (now - lastWifiRetry >= 5000) {
      lastWifiRetry = now;
      WiFi.begin("Wokwi-GUEST", "", 6);
    }
  }

  if (now - lastSampleAt >= SAMPLE_INTERVAL_MS) {
    lastSampleAt = now;
    updateSensors();
    updateCoverDecision(now);
    digitalWrite(STATUS_LED_PIN, coverRequested ? HIGH : LOW);
  }

  if (now - lastDhtAt >= DHT_INTERVAL_MS) {
    lastDhtAt = now;
    readDht();
    publishBlynk();
    publishTelemetry();
  }

  ensureMqttConnected(now);
  ensureBlynkConnected(now);
  if (mqtt.connected()) mqtt.loop();
  if (Blynk.connected()) Blynk.run();
  reportStatus(now);
}

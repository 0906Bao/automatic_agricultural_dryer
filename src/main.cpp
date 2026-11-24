#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include "secrets.h"
#include "hardware.h"
#include "CoverController.h"
#include "WeatherPolicy.h"
#include "CommandGate.h"
#include <PubSubClient.h>
#include "DHTesp.h"

constexpr uint8_t RAIN_PIN = 34, LDR_PIN = 35, DHT_PIN = 15;
constexpr uint8_t LIMIT_COVERED_PIN = 18, LIMIT_OPEN_PIN = 19, STATUS_LED_PIN = 23;
constexpr int RAIN_WET_THRESHOLD = 2200, DARK_THRESHOLD = 2200, BRIGHT_THRESHOLD = 1800;
constexpr uint32_t TELEMETRY_INTERVAL_MS = 1000;
constexpr char TOPIC_TELEMETRY[] = "dryer/telemetry";
constexpr char TOPIC_COMMAND[] = "dryer/command";
constexpr char TOPIC_STATUS[] = "dryer/status";
constexpr char TOPIC_AVAILABILITY[] = "dryer/availability";

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
DHTesp dht;
dryer::WeatherPolicy weather;
dryer::CoverController controller(MOTOR_TRAVEL_TIMEOUT_MS);
dryer::CommandGate commandGate;
portMUX_TYPE motorMux = portMUX_INITIALIZER_UNLOCKED;
dryer::Inputs controlInputs;
bool motorTaskReady = false;
bool dhtValid = false, isDark = false, isRaining = false;
int rainRaw = 0, lightRaw = 0;
float temperatureC = NAN, humidityPct = NAN;
uint32_t lastDhtAt = 0, lastSampleAt = 0, lastReportAt = 0;
uint32_t lastMqttReconnectAt = 0, lastWifiRetry = 0;
uint32_t decisionUpdatedAt = 0;
char sessionId[9];
const char* commandResult = "BOOT_STOPPED";
const char* lastMqttCommandResult = "NONE";

// Called only inside the short critical section. No network/Serial/delays here.
void readSafetyInputs(dryer::Inputs& in) {
  in.covered = digitalRead(LIMIT_COVERED_PIN) == LOW;
  in.open = digitalRead(LIMIT_OPEN_PIN) == LOW;
  in.emergency = digitalRead(ESTOP_PIN) == HIGH;
  in.driverFault = digitalRead(DRIVER_FAULT_PIN) == LOW;
}

void motorTask(void*) {
  dryer::Output previous;
  for (;;) {
    portENTER_CRITICAL(&motorMux);
    readSafetyInputs(controlInputs);
    if (uint32_t(millis() - decisionUpdatedAt) > 10000) {
      controlInputs.autoClose = true;
      controlInputs.safeToOpen = false;
      controlInputs.danger = true;
    }
    controller.tick(millis(), controlInputs);
    const auto out = controller.output;
    if (out.enable != previous.enable || out.in1 != previous.in1 || out.in2 != previous.in2) {
      digitalWrite(MOTOR_ENABLE_PIN, LOW);
      digitalWrite(MOTOR_IN1_PIN, MOTOR_OUTPUT_ENABLED && out.in1 ? HIGH : LOW);
      digitalWrite(MOTOR_IN2_PIN, MOTOR_OUTPUT_ENABLED && out.in2 ? HIGH : LOW);
      digitalWrite(MOTOR_ENABLE_PIN, MOTOR_OUTPUT_ENABLED && out.enable ? HIGH : LOW);
      previous = out;
    }
    portEXIT_CRITICAL(&motorMux);
    vTaskDelay(pdMS_TO_TICKS(5));
  }
}

dryer::CoverController snapshot(dryer::Inputs& in) {
  portENTER_CRITICAL(&motorMux);
  auto copy = controller;
  in = controlInputs;
  portEXIT_CRITICAL(&motorMux);
  return copy;
}

void runCommand(dryer::Command cmd) {
  if (!motorTaskReady) { commandResult = "REJECTED_TASK_UNAVAILABLE"; return; }
  portENTER_CRITICAL(&motorMux);
  readSafetyInputs(controlInputs);
  const bool ok = controller.command(cmd, controlInputs);
  commandResult = dryer::commandFeedback(ok, cmd, controller.fault);
  portEXIT_CRITICAL(&motorMux);
  Serial.printf("Command: %s\n", commandResult);
}

void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  if (strcmp(topic, TOPIC_COMMAND)) return;
  char envelope[48];
  if (!length || length >= sizeof(envelope) || memchr(payload, '\0', length)) {
    commandResult = "REJECTED_ENVELOPE"; return;
  }
  memcpy(envelope, payload, length);
  envelope[length] = '\0';
  const auto cmd = commandGate.accept(envelope, sessionId);
  if (cmd == dryer::Command::Invalid) commandResult = "REJECTED_SESSION_SEQUENCE_OR_COMMAND";
  else {
    runCommand(cmd);
    lastMqttCommandResult = commandResult;
  }
  mqtt.publish(TOPIC_STATUS, commandResult, false);
}

int readAverage(uint8_t pin) {
  uint32_t total = 0;
  for (int i = 0; i < 8; ++i) { total += analogRead(pin); delay(2); }
  return total / 8;
}

void readDht() {
  auto data = dht.getTempAndHumidity();
  dhtValid = dht.getStatus() == 0 && isfinite(data.temperature) &&
             isfinite(data.humidity) && data.humidity >= 0 && data.humidity <= 100;
  temperatureC = dhtValid ? data.temperature : NAN;
  humidityPct = dhtValid ? data.humidity : NAN;
}

void updateDecision() {
  weather.update(millis(), isRaining, isDark, dhtValid, humidityPct);
  portENTER_CRITICAL(&motorMux);
  controlInputs.autoClose = weather.close;
  controlInputs.safeToOpen = weather.safeToOpen;
  controlInputs.danger = weather.danger;
  decisionUpdatedAt = millis();
  portEXIT_CRITICAL(&motorMux);
  digitalWrite(STATUS_LED_PIN, weather.close ? HIGH : LOW);
}

void publishTelemetry() {
  dryer::Inputs in;
  auto state = snapshot(in);
  if (mqtt.connected()) {
    char payload[1024];
    const int size = snprintf(payload, sizeof(payload),
      "{\"session\":\"%s\",\"last_command_seq\":%llu,\"rain_adc\":%d,\"light_adc\":%d,"
      "\"rain\":%s,\"dark\":%s,\"temperature_c\":%.2f,\"humidity_pct\":%.2f,"
      "\"dht_valid\":%s,\"safe_to_open\":%s,\"humidity_warning\":%s,\"humidity_danger\":%s,"
      "\"cover_request\":\"%s\",\"cover_reason\":\"%s\","
      "\"limit_covered\":%s,\"limit_open\":%s,\"estop\":%s,\"driver_fault\":%s,"
      "\"mode\":\"%s\",\"motion\":\"%s\",\"fault\":\"%s\","
      "\"motor_output_enabled\":%s,\"motor_active\":%s,\"command_result\":\"%s\","
      "\"last_command_result\":\"%s\"}",
      sessionId, (unsigned long long)commandGate.lastSequence, rainRaw, lightRaw,
      isRaining ? "true" : "false", isDark ? "true" : "false",
      dhtValid ? temperatureC : -999.0f, dhtValid ? humidityPct : -999.0f,
      dhtValid ? "true" : "false", in.safeToOpen ? "true" : "false",
      dhtValid && humidityPct >= 70 ? "true" : "false",
      dhtValid && humidityPct > 80 ? "true" : "false", weather.close ? "CLOSE" : "OPEN",
      weather.reason, in.covered ? "true" : "false", in.open ? "true" : "false",
      in.emergency ? "true" : "false", in.driverFault ? "true" : "false",
      dryer::name(state.mode), dryer::name(state.motion), dryer::name(state.fault),
      MOTOR_OUTPUT_ENABLED ? "true" : "false",
      MOTOR_OUTPUT_ENABLED && state.output.enable ? "true" : "false", commandResult, lastMqttCommandResult);
    if (size > 0 && size < int(sizeof(payload))) {
      if (!mqtt.publish(TOPIC_TELEMETRY, payload, false)) Serial.println("MQTT publish failed");
    } else Serial.println("Telemetry overflow");
  }
  Serial.printf("mode=%s motion=%s fault=%s request=%s reason=%s outputs=%s\n",
    dryer::name(state.mode), dryer::name(state.motion), dryer::name(state.fault),
    weather.close ? "CLOSE" : "OPEN", weather.reason, MOTOR_OUTPUT_ENABLED ? "ENABLED" : "LOCKED");
}

void serviceConnections() {
  uint32_t now = millis();
  if (WiFi.status() != WL_CONNECTED) {
    if (uint32_t(now - lastWifiRetry) >= 10000) {
      lastWifiRetry = now;
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD, WIFI_CHANNEL);
    }
    return;
  }
  // Avoid long reconnection work while the actuator is moving.
  dryer::Inputs in;
  const auto state = snapshot(in);
  if (MOTOR_OUTPUT_ENABLED &&
      (state.output.enable || state.motion == dryer::Motion::Waiting)) return;
  if (!mqtt.connected() && uint32_t(now - lastMqttReconnectAt) >= 5000) {
    lastMqttReconnectAt = now;
    String client = "agri-dryer-" + String((uint32_t)ESP.getEfuseMac(), HEX);
    bool ok = strlen(MQTT_USER) ? mqtt.connect(client.c_str(), MQTT_USER, MQTT_PASSWORD,
      TOPIC_AVAILABILITY, 1, true, "offline") :
      mqtt.connect(client.c_str(), TOPIC_AVAILABILITY, 1, true, "offline");
    if (ok) {
      mqtt.publish(TOPIC_AVAILABILITY, "online", true);
      mqtt.subscribe(TOPIC_COMMAND, 1);
      mqtt.publish(TOPIC_STATUS, "connected", false);
      publishTelemetry();
    }
  }
}

void setup() {
  // Add a hardware pull-down on EN to keep the driver off during reset.
  digitalWrite(MOTOR_ENABLE_PIN, LOW); pinMode(MOTOR_ENABLE_PIN, OUTPUT);
  digitalWrite(MOTOR_IN1_PIN, LOW); pinMode(MOTOR_IN1_PIN, OUTPUT);
  digitalWrite(MOTOR_IN2_PIN, LOW); pinMode(MOTOR_IN2_PIN, OUTPUT);
  pinMode(LIMIT_COVERED_PIN, INPUT_PULLUP); pinMode(LIMIT_OPEN_PIN, INPUT_PULLUP);
  pinMode(ESTOP_PIN, INPUT_PULLUP); pinMode(DRIVER_FAULT_PIN, INPUT_PULLUP);
  pinMode(STATUS_LED_PIN, OUTPUT); pinMode(RAIN_PIN, INPUT); pinMode(LDR_PIN, INPUT);
  Serial.begin(115200);
  snprintf(sessionId, sizeof(sessionId), "%08lx", (unsigned long)esp_random());
  motorTaskReady = xTaskCreatePinnedToCore(motorTask, "cover-safety", 4096, nullptr,
                                         3, nullptr, 1) == pdPASS;
  if (!motorTaskReady) Serial.println("ERROR: motor task unavailable; outputs locked");
  analogReadResolution(12);
  dht.setup(DHT_PIN, DHTesp::DHT22);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD, WIFI_CHANNEL);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);
  mqtt.setBufferSize(1280); mqtt.setSocketTimeout(1); mqtt.setKeepAlive(30);
  wifiClient.setTimeout(1000);
  digitalWrite(STATUS_LED_PIN, HIGH);
  delay(2000); // safety task already runs; controller boots STOPPED
  digitalWrite(STATUS_LED_PIN, LOW);
  Serial.println("DRYER v3 - boot STOPPED; RESET after fault, then explicit AUTO/OPEN/CLOSE");
}

void loop() {
  uint32_t now = millis();
  if (uint32_t(now - lastDhtAt) >= 2500) { lastDhtAt = now; readDht(); updateDecision(); }
  if (uint32_t(now - lastSampleAt) >= 250) {
    lastSampleAt = now;
    rainRaw = readAverage(RAIN_PIN); lightRaw = readAverage(LDR_PIN);
    isRaining = rainRaw >= RAIN_WET_THRESHOLD;
    if (lightRaw >= DARK_THRESHOLD) isDark = true;
    else if (lightRaw <= BRIGHT_THRESHOLD) isDark = false;
    updateDecision();
  }
  if (mqtt.connected()) mqtt.loop();
  serviceConnections();
  if (uint32_t(millis() - lastReportAt) >= TELEMETRY_INTERVAL_MS) {
    lastReportAt = millis(); publishTelemetry();
  }
  delay(1);
}

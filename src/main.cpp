#include <Arduino.h>

// Wokwi wiring: rain potentiometer -> GPIO34, LDR AO -> GPIO35.
// GPIO34/35 are ADC1 input pins, so they remain usable with Wi-Fi later.
constexpr uint8_t RAIN_PIN = 34;
constexpr uint8_t LDR_PIN = 35;
constexpr uint8_t LIMIT_COVERED_PIN = 18;
constexpr uint8_t LIMIT_OPEN_PIN = 19;
// Use GPIO23 for the external status LED (GPIO2 is a boot-strapping pin).
constexpr uint8_t STATUS_LED_PIN = 23;

// Starting points only. Read the Serial output and calibrate these on your
// actual sensor. Wokwi rain potentiometer is treated as: higher = wetter.
constexpr int RAIN_WET_THRESHOLD = 2200;
// Wokwi LDR AO is higher in darkness; hysteresis avoids threshold chatter.
constexpr int DARK_THRESHOLD = 2200;
constexpr int BRIGHT_THRESHOLD = 1800;

constexpr uint32_t SAMPLE_INTERVAL_MS = 250;
constexpr uint32_t SENSOR_CONFIRM_MS = 500;
constexpr uint32_t SAFE_TO_OPEN_MS = 30000;
constexpr uint32_t REPORT_INTERVAL_MS = 1000;
constexpr uint8_t AVERAGE_SAMPLES = 8;

bool isDark = false;
bool coverRequested = false;
bool coverConditionTiming = false;
bool safeConditionTiming = false;
uint32_t coverConditionSince = 0;
uint32_t safeConditionSince = 0;
uint32_t lastSampleAt = 0;
uint32_t lastReportAt = 0;
int rainRaw = 0;
int lightRaw = 0;
bool isRaining = false;

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

  // Separate dark/bright thresholds provide hysteresis.
  if (!isDark && lightRaw >= DARK_THRESHOLD) {
    isDark = true;
  } else if (isDark && lightRaw <= BRIGHT_THRESHOLD) {
    isDark = false;
  }
}

void updateCoverDecision(uint32_t now) {
  const bool shouldCover = isRaining || isDark;

  if (shouldCover) {
    safeConditionTiming = false;
    if (!coverConditionTiming) {
      coverConditionTiming = true;
      coverConditionSince = now;
    }
    if (!coverRequested && now - coverConditionSince >= SENSOR_CONFIRM_MS) {
      coverRequested = true;
      Serial.println("ACTION: CLOSE COVER (rain or darkness)");
    }
    return;
  }

  coverConditionTiming = false;
  if (coverRequested) {
    if (!safeConditionTiming) {
      safeConditionTiming = true;
      safeConditionSince = now;
    }
    if (now - safeConditionSince >= SAFE_TO_OPEN_MS) {
      coverRequested = false;
      safeConditionTiming = false;
      Serial.println("ACTION: OPEN COVER (dry and bright for 30 seconds)");
    }
  }
}

void reportStatus(uint32_t now) {
  if (now - lastReportAt < REPORT_INTERVAL_MS) return;
  lastReportAt = now;

  Serial.printf("rain_adc=%d rain=%s | light_adc=%d dark=%s | ", rainRaw,
                isRaining ? "YES" : "NO", lightRaw, isDark ? "YES" : "NO");
  Serial.printf("cover_request=%s | limit_covered=%s limit_open=%s\n",
                coverRequested ? "CLOSE" : "OPEN",
                digitalRead(LIMIT_COVERED_PIN) == LOW ? "ACTIVE" : "inactive",
                digitalRead(LIMIT_OPEN_PIN) == LOW ? "ACTIVE" : "inactive");
}

void setup() {
  // Start UART0 before the LED self-test so the serial monitor can show output
  // from the beginning of the simulation.
  Serial.begin(115200);
  delay(100);
  Serial.println("BOOT: serial output active");

  pinMode(RAIN_PIN, INPUT);
  pinMode(LDR_PIN, INPUT);
  pinMode(LIMIT_COVERED_PIN, INPUT_PULLUP);
  pinMode(LIMIT_OPEN_PIN, INPUT_PULLUP);
  pinMode(STATUS_LED_PIN, OUTPUT);
  analogReadResolution(12); // ESP32 ADC readings are 0..4095.

  // Visible boot self-test: confirms the application reached setup() even
  // when the serial monitor/forwarding path is unavailable.
  digitalWrite(STATUS_LED_PIN, HIGH);
  delay(3000);
  digitalWrite(STATUS_LED_PIN, LOW);

  Serial.println();
  Serial.println("AUTOMATIC AGRICULTURAL DRYER - SENSOR / DECISION TEST");
  Serial.println("Cover rule: rain OR dark => request close; dry AND bright for 30s => request open");
  Serial.printf("Thresholds: rain >= %d, dark >= %d, bright <= %d (ADC 0..4095)\n",
                RAIN_WET_THRESHOLD, DARK_THRESHOLD, BRIGHT_THRESHOLD);
}

void loop() {
  const uint32_t now = millis();
  if (now - lastSampleAt >= SAMPLE_INTERVAL_MS) {
    lastSampleAt = now;
    updateSensors();
    updateCoverDecision(now);
    // During this phase the LED means "cover requested", not "cover reached".
    digitalWrite(STATUS_LED_PIN, coverRequested ? HIGH : LOW);
  }
  reportStatus(now);
}

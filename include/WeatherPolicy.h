#pragma once
#include <stdint.h>
namespace dryer {
class WeatherPolicy {
 public:
  bool close = true; // no unverified opening at boot
  bool danger = true, safeToOpen = false;
  const char* reason = "DHT_ERROR";
  void update(uint32_t now, bool rain, bool dark, bool valid, float humidity) {
    danger = rain || dark || !valid || humidity > 80.0f;
    const bool conditionsSafe = !rain && !dark && valid && humidity < 70.0f;
    safeToOpen = false;
    reason = rain ? "RAIN" : dark ? "DARK" : !valid ? "DHT_ERROR" :
             humidity > 80.0f ? "HUMIDITY_DANGER" : humidity >= 70.0f ?
             "HUMIDITY_WARNING" : "NORMAL";
    if (danger) {
      safeTiming_ = false;
      if (!dangerTiming_) { dangerSince_ = now; dangerTiming_ = true; }
      if (uint32_t(now - dangerSince_) >= 500) close = true;
    } else {
      dangerTiming_ = false;
      if (conditionsSafe) {
        if (!safeTiming_) { safeSince_ = now; safeTiming_ = true; }
        if (uint32_t(now - safeSince_) >= 30000) {
          safeToOpen = true;
          close = false;
        }
      } else safeTiming_ = false;
    }
  }
 private:
  bool safeTiming_ = false, dangerTiming_ = false;
  uint32_t safeSince_ = 0, dangerSince_ = 0;
};
}

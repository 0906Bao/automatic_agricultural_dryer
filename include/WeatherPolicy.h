#pragma once
#include <stdint.h>
namespace dryer {
class WeatherPolicy {
 public:
  bool close = true; // no unverified opening at boot
  bool recommendClose = true; // advisory only; never used as the motor target
  bool danger = true, safeToOpen = false;
  // -1: conditions interrupted; 0: ready; 1..10: safe time still required.
  int openWaitRemainingSeconds = -1;
  const char* reason = "DHT_ERROR";
  void update(uint32_t now, bool rain, bool dark, bool valid, float humidity) {
    danger = rain || dark || !valid || humidity > 80.0f;
    const bool conditionsSafe = !rain && !dark && valid && humidity < 70.0f;
    safeToOpen = false;
    openWaitRemainingSeconds = -1;
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
        const uint32_t elapsed = uint32_t(now - safeSince_);
        openWaitRemainingSeconds = elapsed >= 10000 ? 0 : (10000 - elapsed + 999) / 1000;
        if (close && elapsed < 10000) reason = "WAITING_SAFE";
        if (elapsed >= 10000) {
          safeToOpen = true;
          close = false;
        }
      } else safeTiming_ = false;
    }
    recommendClose = close || danger || (valid && humidity >= 70.0f);
  }
 private:
  bool safeTiming_ = false, dangerTiming_ = false;
  uint32_t safeSince_ = 0, dangerSince_ = 0;
};
}

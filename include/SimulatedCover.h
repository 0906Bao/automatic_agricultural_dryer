#pragma once
#include "CoverController.h"

namespace dryer {
// Wokwi's LEDs do not move the end-stop switches. Model a five-second
// full stroke, retaining position during STOP, faults and reversal dead time.
// Only instantiated by the explicitly selected simulation firmware.
class SimulatedCover {
 public:
  explicit SimulatedCover(uint32_t travelMs = 5000)
      : travelMs_(travelMs), position_(travelMs / 2) {}

  void update(uint32_t now, const Output& output, bool covered, bool open) {
    const uint32_t elapsed = initialized_ ? uint32_t(now - lastAt_) : 0;
    initialized_ = true;
    lastAt_ = now;
    if (output.enable && output.in1 != output.in2) {
      if (output.in1) {
        const uint32_t remaining = travelMs_ - position_;
        position_ += elapsed < remaining ? elapsed : remaining;
      } else {
        position_ -= elapsed < position_ ? elapsed : position_;
      }
    }
    // A manually asserted switch can still force an endpoint for testing.
    if (covered && !open) position_ = 0;
    if (open && !covered) position_ = travelMs_;
  }

  void applyLimits(Inputs& in) const {
    // Preserve a physical BOTH_LIMITS fault for diagnostic tests.
    if (in.covered || in.open) return;
    in.covered = position_ == 0;
    in.open = position_ == travelMs_;
  }

 private:
  uint32_t travelMs_, position_, lastAt_ = 0;
  bool initialized_ = false;
};
} // namespace dryer

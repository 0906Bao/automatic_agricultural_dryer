#pragma once
#include <stdint.h>
#include <string.h>

namespace dryer {
enum class Command { Stop, Auto, Open, Close, Reset, Invalid };
enum class Mode { Stopped, Auto, Open, Close };
enum class Motion { Idle, Opening, Closing, Waiting, Fault };
enum class Fault { None, Emergency, Limits, Timeout, Driver };
inline Command parseCommand(const char* text) {
  if (!strcmp(text, "STOP")) return Command::Stop;
  if (!strcmp(text, "AUTO")) return Command::Auto;
  if (!strcmp(text, "OPEN")) return Command::Open;
  if (!strcmp(text, "CLOSE")) return Command::Close;
  if (!strcmp(text, "RESET")) return Command::Reset;
  return Command::Invalid;
}
struct Inputs {
  bool covered = false, open = false, emergency = false, driverFault = false;
  bool autoClose = true, safeToOpen = false, danger = true;
};
struct Output { bool enable = false, in1 = false, in2 = false; };
class CoverController {
 public:
  explicit CoverController(uint32_t timeout = 20000, uint32_t deadtime = 300)
      : timeout_(timeout), deadtime_(deadtime) {}
  Mode mode = Mode::Stopped;
  Motion motion = Motion::Idle;
  Fault fault = Fault::None;
  Output output;

  bool command(Command cmd, const Inputs& in) {
    // Commands never bypass a physical safety input, even between timer ticks.
    checkFault(in);
    if (cmd == Command::Invalid) return false;
    if (cmd == Command::Stop) { mode = Mode::Stopped; stop(); return true; }
    if (cmd == Command::Reset) {
      if (in.emergency || in.driverFault || (in.covered && in.open)) return false;
      fault = Fault::None;
      mode = Mode::Stopped;
      reached_ = 0;
      stop();
      return true;
    }
    if (fault != Fault::None) return false;
    if (cmd == Command::Open && !in.safeToOpen) return false;
    // Duplicate commands must not restart the timeout or bypass reversal delay.
    Mode next = cmd == Command::Auto ? Mode::Auto :
                cmd == Command::Open ? Mode::Open : Mode::Close;
    if (next != mode) reached_ = 0;
    mode = next;
    return true;
  }

  void tick(uint32_t now, const Inputs& in) {
    checkFault(in);
    if (fault != Fault::None) { stop(); motion = Motion::Fault; return; }
    if (mode == Mode::Stopped) { stop(); return; }
    // A manual open cannot override rain/darkness/DHT failure/high humidity.
    if (mode == Mode::Open && in.danger) mode = Mode::Close;
    int target = mode == Mode::Auto ? (in.autoClose ? -1 : 1) :
                 mode == Mode::Close ? -1 : 1;
    if (target != lastTarget_) { reached_ = 0; lastTarget_ = target; }
    if ((target == -1 && in.covered) || (target == 1 && in.open)) {
      reached_ = target;
      stop();
      return;
    }
    // Do not restart against an end stop when a mechanical contact bounces.
    if (reached_ == target) { stop(); return; }
    if (direction_ != 0 && direction_ != target) {
      stop();
      return; // starts the full dead time from the first stopped tick below
    }
    if (direction_ == 0) {
      if (!offTiming_) { offSince_ = now; offTiming_ = true; }
      if (uint32_t(now - offSince_) < deadtime_) { motion = Motion::Waiting; return; }
      direction_ = target;
      started_ = now;
      offTiming_ = false;
    }
    if (uint32_t(now - started_) >= timeout_) {
      fault = Fault::Timeout;
      mode = Mode::Stopped;
      stop(); motion = Motion::Fault;
      return;
    }
    output.enable = true;
    output.in1 = target == 1;
    output.in2 = target == -1;
    motion = target == 1 ? Motion::Opening : Motion::Closing;
  }
 private:
  uint32_t timeout_, deadtime_, started_ = 0, offSince_ = 0;
  int direction_ = 0, lastTarget_ = 0, reached_ = 0;
  bool offTiming_ = false;
  void stop() {
    output = Output{};
    if (direction_ != 0) offTiming_ = false;
    direction_ = 0;
    motion = fault == Fault::None ? Motion::Idle : Motion::Fault;
  }
  void checkFault(const Inputs& in) {
    if (in.emergency) fault = Fault::Emergency;
    else if (in.covered && in.open) fault = Fault::Limits;
    else if (in.driverFault) fault = Fault::Driver;
    if (fault != Fault::None) { mode = Mode::Stopped; stop(); }
  }
};
inline const char* name(Mode x) {
  switch (x) { case Mode::Auto: return "AUTO"; case Mode::Open: return "MANUAL_OPEN";
    case Mode::Close: return "MANUAL_CLOSE"; default: return "STOPPED"; }
}
inline const char* name(Motion x) {
  switch (x) { case Motion::Opening: return "OPENING"; case Motion::Closing: return "CLOSING";
    case Motion::Waiting: return "REVERSAL_WAIT"; case Motion::Fault: return "FAULT";
    default: return "IDLE"; }
}
inline const char* name(Fault x) {
  switch (x) { case Fault::Emergency: return "ESTOP"; case Fault::Limits: return "BOTH_LIMITS";
    case Fault::Timeout: return "MOTION_TIMEOUT"; case Fault::Driver: return "DRIVER_FAULT";
    default: return "NONE"; }
}
inline const char* commandFeedback(bool accepted, Command cmd, Fault fault) {
  if (accepted) return "ACCEPTED";
  if (cmd == Command::Invalid) return "REJECTED_COMMAND";
  switch (fault) {
    case Fault::Timeout: return "REJECTED_MOTION_TIMEOUT";
    case Fault::Emergency: return "REJECTED_ESTOP";
    case Fault::Limits: return "REJECTED_BOTH_LIMITS";
    case Fault::Driver: return "REJECTED_DRIVER_FAULT";
    default: return "REJECTED_OPEN_UNSAFE";
  }
}
} // namespace dryer

#pragma once
#include "CoverController.h"
#include <stdio.h>
#include <stdlib.h>
namespace dryer {
// Per-boot session + increasing sequence rejects retained commands from a prior
// boot and duplicates delivered on MQTT reconnect. Reset only on device reboot.
class CommandGate {
 public:
  uint64_t lastSequence = 0;
  static constexpr uint64_t MaxSequence = 4294967295ULL;
  static constexpr uint64_t MaxJump = 64;
  bool rotationRequired() const { return lastSequence >= MaxSequence - MaxJump; }
  Command accept(const char* envelope, const char* session) {
    char received[9] = {}, digits[17] = {}, text[6] = {}, extra;
    if (sscanf(envelope, "%8[0-9a-f] %16[0-9] %5[A-Z]%c",
               received, digits, text, &extra) != 3) return Command::Invalid;
    if (strcmp(received, session)) return Command::Invalid;
    uint64_t sequence = strtoull(digits, nullptr, 10);
    Command cmd = parseCommand(text);
    if (sequence <= lastSequence || sequence > MaxSequence ||
        sequence - lastSequence > MaxJump ||
        cmd == Command::Invalid) return Command::Invalid;
    lastSequence = sequence; // rejected physical commands cannot be replayed later
    return cmd;
  }
};
}

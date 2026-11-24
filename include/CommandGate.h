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
  Command accept(const char* envelope, const char* session) {
    char received[9] = {}, digits[17] = {}, text[6] = {}, extra;
    if (sscanf(envelope, "%8[0-9a-f] %16[0-9] %5[A-Z]%c",
               received, digits, text, &extra) != 3) return Command::Invalid;
    if (strcmp(received, session)) return Command::Invalid;
    uint64_t sequence = strtoull(digits, nullptr, 10);
    Command cmd = parseCommand(text);
    if (sequence <= lastSequence || sequence > 9007199254740991ULL ||
        cmd == Command::Invalid) return Command::Invalid;
    lastSequence = sequence; // rejected physical commands cannot be replayed later
    return cmd;
  }
};
}

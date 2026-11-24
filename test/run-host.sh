#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p .pio/host-tests
c++ -std=c++14 -Wall -Wextra -Werror -Iinclude test/host/test_controller.cpp -o .pio/host-tests/test_controller
.pio/host-tests/test_controller
node --test test/node-red.test.cjs test/home-assistant.test.cjs test/ha-status-card.test.cjs

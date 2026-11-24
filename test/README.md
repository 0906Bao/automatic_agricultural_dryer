# Automated checks

Run `powershell -NoProfile -ExecutionPolicy Bypass -File test/run-host.ps1` on Windows
with Visual Studio C++ tools and Node.js, or `sh test/run-host.sh` on Linux/macOS
with a C++ compiler and Node.js.

`host/test_controller.cpp` executes the production firmware headers on the host:
travel limits, reversal delay, STOP, latching faults, emergency stop, timeout,
manual safety overrides, weather thresholds, timer rollover and MQTT replay guards.

`node-red.test.cjs` checks command routing, freshness, sequencing, the exported
flow and dashboard behavior with simulated HTTP responses. It needs no npm packages.

`home-assistant.test.cjs` checks normalized telemetry, position from limit inputs,
HA request timestamps, throttling, acknowledgements, stale states and restarts.
`tools/test-ha-runtime.py` is an optional live test against a running HAOS/MQTT/
Node-RED stack using isolated topics, a temporary package and a telemetry/ACK
emulator. It never sends commands to the real dryer topic. It restarts HA Core,
so run during maintenance; requires paho-mqtt, PyYAML and a local setup account.

These checks do not use a real motor, ESP32 or MQTT broker.
`security.test.cjs` checks mandatory authentication, preservation of credential encryption,
audit logging and suppression/redaction of device rejection events.
The current TLS/ACL runtime is verified with `python tools/harden-tls.py verify` and
the stationary STOP-only sequence check `python tools/harden-tls.py verify_commands`.
Legacy namespaced runtime smoke tests require an isolated test broker/account;
do not broaden production ACLs to run them.
`ha-status-card.test.cjs` checks icon/colour changes, stale-data handling,
fault and waiting states, and countdown formatting in the Home Assistant card.
See `docs/CONTROL_VI.md` for hardware acceptance scenarios.

Run `python test/test_notifications.py` with PyYAML and Jinja2 installed to
check proposal/safety transitions, suppression of repeated timer-only updates,
and the advisory-only notification at 70–80% humidity. CI runs this check.

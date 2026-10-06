# Automatic agricultural dryer: hardware and sensor phase

## Mechanical and electrical design decision

- Use a DC winch that can turn in both directions: one direction pulls the cover closed, the other opens it.
- Use two normally-open limit switches wired from ESP32 GPIO18/GPIO19 to GND. With `INPUT_PULLUP`, a pressed switch reads LOW. GPIO18 is the fully-covered limit; GPIO19 is the fully-open limit.
- The firmware in this phase does **not** drive a motor. GPIO2 is only a status indicator for the requested cover direction. Do not connect a winch or motor to GPIO2 or an ESP32 pin.
- Select the H-bridge/driver only after measuring the motor's rated voltage, normal current, and stall/start current. The driver must support the motor's voltage and stall current, and the motor needs its own supply. Join the motor-supply ground and ESP32 ground. Add suitable fuse, emergency stop, and mechanical limit switches in the motor power/control path.
- The L298N should not be assumed suitable for a high-power winch; its IC datasheet specifies up to 2 A per bridge under stated conditions. Check the actual module's thermal and current limits and use a higher-current driver if required.

## Sensor mapping and automatic decision

| Signal | ESP32 pin | Current Wokwi part | Decision |
| --- | ---: | --- | --- |
| Rain analog | GPIO34 / ADC1 | Potentiometer | At/above threshold means rain (simulation convention) |
| Light analog | GPIO35 / ADC1 | Photoresistor AO | At/above dark threshold means dark; lower than bright threshold means bright |
| Covered limit | GPIO18 | Green pushbutton to GND | LOW when pressed |
| Open limit | GPIO19 | Red pushbutton to GND | LOW when pressed |
| Status LED | GPIO2 | LED/resistor | On means close is requested, not that the cover has reached its limit |

The cover decision is `rain OR dark -> request close`. It requests opening only after the sensors indicate `dry AND bright` continuously for 30 seconds. Sensor readings are averaged and the dark/bright thresholds use hysteresis. Rain is confirmed for 500 ms to reject spikes; adjust this if the application must react faster or the sensor chatters. On boot, the status LED stays on for 3 seconds as a self-test before it starts showing the cover request.

Thresholds in `src/main.cpp` are initial calibration values, not universal values. Use Serial Monitor at 115200 baud to watch `rain_adc` and `light_adc`, test dry/wet and bright/dark conditions, then edit `RAIN_WET_THRESHOLD`, `DARK_THRESHOLD`, and `BRIGHT_THRESHOLD`. If a physical rain board's analog output falls when wet, invert the rain comparison in `updateSensors()`.

## Try the current sensor/logic simulation

1. Build and run the Wokwi simulation with `diagram.json` and `wokwi.toml`.
2. Open Serial Monitor. Move the potentiometer and change the photoresistor's lux control; verify the raw values and `rain`/`dark` flags.
3. Cause rain or darkness and confirm `cover_request=CLOSE` and the status LED turns on.
4. Restore dry and bright conditions and wait 30 seconds; confirm the request returns to OPEN and the LED turns off.
5. Press each limit button and confirm its corresponding `limit_covered`/`limit_open` indicator becomes ACTIVE.

The limit inputs are present for the next motor-control phase. This phase reports them but does not yet use them to stop a motor. Before connecting the real winch, implement a motion state machine that stops at the relevant limit, handles both limits active as a fault, times out a stalled movement, and supports an emergency stop.

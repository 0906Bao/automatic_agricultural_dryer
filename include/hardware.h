#pragma once
// Keep disabled until driver polarity, motor rating and travel time are verified.
#ifndef MOTOR_OUTPUT_ENABLED
#define MOTOR_OUTPUT_ENABLED 0
#endif
// Explicit simulation environment overrides even a locked local configuration.
#if defined(DRYER_WOKWI_SIMULATION) && DRYER_WOKWI_SIMULATION
#undef MOTOR_OUTPUT_ENABLED
#define MOTOR_OUTPUT_ENABLED 1
#endif
#ifndef MOTOR_TRAVEL_TIMEOUT_MS
#define MOTOR_TRAVEL_TIMEOUT_MS 20000UL
#endif
static_assert(MOTOR_OUTPUT_ENABLED == 0 || MOTOR_OUTPUT_ENABLED == 1, "Motor output flag must be 0 or 1");
static_assert(MOTOR_TRAVEL_TIMEOUT_MS >= 100 && MOTOR_TRAVEL_TIMEOUT_MS < 0x80000000UL,
              "Travel timeout must be positive and rollover-safe");
constexpr int MOTOR_IN1_PIN = 25;
constexpr int MOTOR_IN2_PIN = 26;
constexpr int MOTOR_ENABLE_PIN = 27;
// NC emergency contact to GND: healthy LOW, pressed/disconnected HIGH.
constexpr int ESTOP_PIN = 21;
// Optional active-low driver fault output; pull-up leaves unused input healthy.
constexpr int DRIVER_FAULT_PIN = 22;

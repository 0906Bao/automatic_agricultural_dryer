#include "CoverController.h"
#include "WeatherPolicy.h"
#include "CommandGate.h"
#include "SimulatedCover.h"
#include <stdio.h>
#include <stdlib.h>
#include <limits.h>
using namespace dryer;
static int checks = 0;
#define CHECK(expr) do { ++checks; if (!(expr)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #expr); exit(1); } } while (0)
static Inputs healthy() { Inputs in; in.safeToOpen = true; in.danger = false; return in; }
static void start(CoverController& c, Inputs& in, Command cmd, uint32_t now = 0) {
  CHECK(c.command(cmd, in)); c.tick(now, in); c.tick(now + 300, in);
}
int main() {
  {
    WeatherPolicy p; CoverController c; auto in=healthy();
    p.update(0,false,false,true,60); p.update(30000,false,false,true,60);
    in.open=true; in.autoClose=p.close; in.safeToOpen=p.safeToOpen; in.danger=p.danger;
    CHECK(c.command(Command::Auto,in)); c.tick(30000,in);
    const float levels[]={70,75,80};
    for (int i=0;i<3;++i) {
      p.update(31000+i*1000,false,false,true,levels[i]);
      CHECK(p.recommendClose && !p.close && !p.danger && !p.safeToOpen);
      CHECK(!strcmp(p.reason,"HUMIDITY_WARNING"));
      in.autoClose=p.close; in.safeToOpen=p.safeToOpen; in.danger=p.danger;
      c.tick(31000+i*1000,in); CHECK(!c.output.enable && c.mode==Mode::Auto);
    }
    // Danger still requests automatic closing after its normal debounce.
    p.update(34000,false,false,true,81); CHECK(p.recommendClose && p.danger);
    p.update(34500,false,false,true,81); CHECK(p.close);
    in.autoClose=p.close; in.danger=p.danger;
    c.tick(34500,in); c.tick(34800,in); CHECK(c.output.enable && c.output.in2);
    // Returning below 70% requires a fresh full safe period before reopening.
    p.update(35000,false,false,true,60); CHECK(p.recommendClose);
    p.update(44999,false,false,true,60); CHECK(!p.safeToOpen);
    p.update(45000,false,false,true,60); CHECK(!p.recommendClose && !p.close && p.safeToOpen);
  }
  {
    WeatherPolicy p;
    CHECK(p.openWaitRemainingSeconds == -1);
    p.update(0, false, false, true, 60); CHECK(p.openWaitRemainingSeconds == 10);
    CHECK(p.close && !strcmp(p.reason, "WAITING_SAFE"));
    p.update(999, false, false, true, 60); CHECK(p.openWaitRemainingSeconds == 10);
    p.update(1000, false, false, true, 60); CHECK(p.openWaitRemainingSeconds == 9);
    p.update(9999, false, false, true, 60); CHECK(p.openWaitRemainingSeconds == 1 && !p.safeToOpen);
    p.update(10000, false, false, true, 60); CHECK(p.openWaitRemainingSeconds == 0 && p.safeToOpen);
    CHECK(!p.close && !strcmp(p.reason, "NORMAL"));
    p.update(30001, true, false, true, 60); CHECK(p.openWaitRemainingSeconds == -1);
    CHECK(!strcmp(p.reason, "RAIN"));
    p.update(31000, false, false, true, 60); CHECK(p.openWaitRemainingSeconds == 10);
    p.update(32000, false, true, true, 60); CHECK(p.openWaitRemainingSeconds == -1);
    p.update(33000, false, false, true, 70); CHECK(p.openWaitRemainingSeconds == -1);
    p.update(34000, false, false, false, 0); CHECK(p.openWaitRemainingSeconds == -1);
    const uint32_t t = UINT32_MAX - 500;
    p.update(t, false, false, true, 60);
    p.update(t + 1000, false, false, true, 60); CHECK(p.openWaitRemainingSeconds == 9);
    p.update(t + 10000, false, false, true, 60); CHECK(p.openWaitRemainingSeconds == 0);
  }
  {
    // End-to-end AUTO cycle without manually pressing Wokwi end stops.
    WeatherPolicy weather; CoverController c; SimulatedCover cover;
    auto in = healthy();
    CHECK(c.command(Command::Auto, in));
    for (uint32_t now = 0; now <= 90000; now += 5) {
      const bool rain = now >= 40000 && now < 50000;
      weather.update(now, rain, false, true, 60);
      cover.update(now, c.output, false, false);
      in.covered = in.open = false;
      cover.applyLimits(in);
      in.autoClose = weather.close;
      in.safeToOpen = weather.safeToOpen;
      in.danger = weather.danger;
      c.tick(now, in);
      CHECK(c.mode == Mode::Auto && c.fault == Fault::None);
      if (now == 9000 || now == 46000) CHECK(in.covered && !c.output.enable);
      if (now == 16000 || now == 66000) CHECK(in.open && !c.output.enable);
      if (now == 41000) CHECK(c.output.enable && c.output.in2);
    }
  }
  {
    SimulatedCover cover(1000); Inputs in;
    Output opening; opening.enable = opening.in1 = true;
    const uint32_t startAt = UINT32_MAX - 200;
    cover.update(startAt, opening, false, false);
    cover.update(startAt + 250, opening, false, false);
    cover.update(startAt + 10000, Output{}, false, false);
    cover.applyLimits(in); CHECK(!in.covered && !in.open); // STOP keeps partial position
    Output closing; closing.enable = closing.in2 = true;
    cover.update(startAt + 10749, closing, false, false);
    cover.applyLimits(in); CHECK(!in.covered && !in.open);
    cover.update(startAt + 10750, closing, false, false);
    cover.applyLimits(in); CHECK(in.covered && !in.open);
    in = Inputs{};
    cover.update(startAt + 10751, Output{}, false, true);
    cover.applyLimits(in); CHECK(in.open && !in.covered); // manual endpoint
    in.covered = in.open = true;
    cover.applyLimits(in); CHECK(in.covered && in.open); // preserve fault injection
  }
  {
    CoverController c(1000); auto in = healthy();
    start(c, in, Command::Auto); c.tick(1300, in);
    CHECK(c.fault == Fault::Timeout && c.mode == Mode::Stopped);
    CHECK(!strcmp(commandFeedback(c.command(Command::Open, in), Command::Open, c.fault), "REJECTED_MOTION_TIMEOUT"));
    CHECK(!strcmp(commandFeedback(c.command(Command::Close, in), Command::Close, c.fault), "REJECTED_MOTION_TIMEOUT"));
    CHECK(c.command(Command::Reset, in));
    in.safeToOpen = false;
    CHECK(!strcmp(commandFeedback(c.command(Command::Open, in), Command::Open, c.fault), "REJECTED_OPEN_UNSAFE"));
    CHECK(!strcmp(commandFeedback(c.command(Command::Close, in), Command::Close, c.fault), "ACCEPTED"));
  }
  {
    CoverController c; auto in = healthy(); c.tick(10000, in);
    CHECK(!c.output.enable); CHECK(c.mode == Mode::Stopped);
    start(c, in, Command::Close);
    CHECK(c.output.enable && !c.output.in1 && c.output.in2);
    in.covered = true; c.tick(301, in); CHECK(!c.output.enable);
    in.covered = false; c.tick(302, in); CHECK(!c.output.enable); // contact bounce
    CHECK(c.command(Command::Open, in)); c.tick(303, in); c.tick(603, in);
    CHECK(c.output.enable && c.output.in1 && !c.output.in2);
    in.open = true; c.tick(604, in); CHECK(!c.output.enable);
  }
  {
    CoverController c; auto in = healthy(); start(c, in, Command::Close);
    CHECK(c.command(Command::Open, in)); c.tick(301, in);
    CHECK(!c.output.enable); c.tick(302, in); c.tick(601, in);
    CHECK(!c.output.enable); c.tick(602, in); CHECK(c.output.in1 && c.output.enable);
    CHECK(c.command(Command::Stop, in)); CHECK(!c.output.enable);
    c.tick(100000, in); CHECK(!c.output.enable && c.mode == Mode::Stopped);
  }
  {
    CoverController c(1000); auto in = healthy(); start(c, in, Command::Open);
    CHECK(c.command(Command::Open, in)); c.tick(1299, in); CHECK(c.output.enable);
    c.tick(1300, in); CHECK(c.fault == Fault::Timeout && !c.output.enable);
    CHECK(!c.command(Command::Close, in)); CHECK(c.command(Command::Reset, in));
    c.tick(2000, in); CHECK(!c.output.enable && c.mode == Mode::Stopped);
  }
  {
    CoverController c; auto in = healthy(); start(c, in, Command::Open);
    in.emergency = true; c.tick(301, in); CHECK(!c.output.enable && c.fault == Fault::Emergency);
    CHECK(!c.command(Command::Reset, in)); in.emergency = false; c.tick(302, in);
    CHECK(c.fault == Fault::Emergency); CHECK(!c.command(Command::Auto, in));
    CHECK(c.command(Command::Reset, in)); CHECK(c.fault == Fault::None && c.mode == Mode::Stopped);
    in.covered = in.open = true; c.tick(303, in); CHECK(c.fault == Fault::Limits);
    CHECK(!c.command(Command::Reset, in)); in.open = false; CHECK(c.command(Command::Reset, in));
    in.driverFault = true; CHECK(!c.command(Command::Close, in)); CHECK(c.fault == Fault::Driver);
  }
  {
    CoverController c; auto in = healthy(); in.safeToOpen = false;
    CHECK(!c.command(Command::Open, in)); in.safeToOpen = true;
    start(c, in, Command::Open); in.danger = true; in.safeToOpen = false;
    c.tick(301, in); CHECK(!c.output.enable && c.mode == Mode::Close);
    c.tick(302, in); c.tick(602, in); CHECK(c.output.in2 && c.output.enable);
  }
  {
    CoverController c(1000); auto in = healthy();
    const uint32_t t = UINT32_MAX - 500; start(c, in, Command::Auto, t);
    CHECK(c.output.in2); c.tick(t + 1300, in); CHECK(c.fault == Fault::Timeout);
  }
  {
    WeatherPolicy p; CHECK(p.close);
    p.update(0, false, false, true, 60); p.update(9999, false, false, true, 60); CHECK(p.close);
    p.update(10000, false, false, true, 60); CHECK(!p.close);
    p.update(30001, true, false, true, 60); p.update(30500, true, false, true, 60); CHECK(!p.close);
    p.update(30501, true, false, true, 60); CHECK(p.close);
    p.update(31000, false, false, true, 60); p.update(50000, false, false, true, 75);
    p.update(60000, false, false, true, 60); p.update(69999, false, false, true, 60); CHECK(p.close);
    p.update(70000, false, false, true, 60); CHECK(!p.close);
    p.update(90001, false, false, true, 80); CHECK(!p.danger && !p.safeToOpen);
    p.update(90002, false, false, true, 81); CHECK(p.danger);
    p.update(90502, false, false, true, 81); CHECK(p.close);
    p.update(90503, false, false, false, 0); CHECK(p.danger && !p.safeToOpen);
    WeatherPolicy wrap; uint32_t t = UINT32_MAX - 100;
    wrap.update(t, false, false, true, 60); wrap.update(t + 10000, false, false, true, 60);
    CHECK(!wrap.close);
  }
  {
    WeatherPolicy p; CoverController c; auto in=healthy();
    p.update(100, false, false, true, 60); in.safeToOpen=p.safeToOpen;
    CHECK(!c.command(Command::Open,in));
    p.update(10099, false, false, true, 60); CHECK(!p.safeToOpen);
    p.update(10100, false, false, true, 60); in.safeToOpen=p.safeToOpen;
    CHECK(p.safeToOpen); CHECK(c.command(Command::Open,in));
    p.update(30101,true,false,true,60); CHECK(!p.safeToOpen);
    p.update(30102,false,false,true,60); CHECK(!p.safeToOpen);
    p.update(40101,false,false,true,60); CHECK(!p.safeToOpen);
    p.update(40102,false,false,true,60); CHECK(p.safeToOpen);
    p.update(60103,false,false,false,0); CHECK(!p.safeToOpen);
    p.update(60104,false,false,true,75); CHECK(!p.safeToOpen);
    p.update(60105,false,true,true,60); CHECK(!p.safeToOpen);
    p.update(60106,false,false,true,85); CHECK(!p.safeToOpen && p.danger);
  }
  {
    CommandGate gate;
    CHECK(gate.accept("deadbeef 1 AUTO", "deadbeef") == Command::Auto);
    CHECK(gate.accept("deadbeef 1 CLOSE", "deadbeef") == Command::Invalid);
    CHECK(gate.accept("abcd1234 2 OPEN", "deadbeef") == Command::Invalid);
    CHECK(gate.accept("deadbeef -2 OPEN", "deadbeef") == Command::Invalid);
    CHECK(gate.accept("deadbeef 2 OPEN junk", "deadbeef") == Command::Invalid);
    CHECK(gate.accept("deadbeef 2 INVALID", "deadbeef") == Command::Invalid);
    CHECK(gate.accept("deadbeef 9999999999999999 STOP", "deadbeef") == Command::Invalid);
    CHECK(gate.accept("deadbeef 2 STOP", "deadbeef") == Command::Stop);
    CHECK(gate.accept("deadbeef 3 RESET", "deadbeef") == Command::Reset);
  }
  // Long mixed input stream checks electrical invariants across faults/reversals.
  {
    CoverController c(1000); auto in = healthy(); uint32_t seed = 17;
    for (uint32_t t = 0; t < 100000; t += 5) {
      seed = seed * 1664525u + 1013904223u;
      in.covered = (seed & 255) == 0; in.open = (seed & 255) == 1;
      in.emergency = (seed & 1023) == 2; in.driverFault = (seed & 1023) == 3;
      if (t % 100 == 0) c.command(static_cast<Command>((seed >> 24) % 5), in);
      c.tick(t, in);
      CHECK(!(c.output.in1 && c.output.in2));
      CHECK(!c.output.enable || c.fault == Fault::None);
      CHECK(!in.emergency || !c.output.enable);
      CHECK(!c.output.enable || !(c.output.in1 && in.open) );
      CHECK(!c.output.enable || !(c.output.in2 && in.covered));
    }
  }
  printf("PASS: %d checks (controller, weather, commands, rollover, mixed safety inputs)\n", checks);
}

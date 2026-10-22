/*
  Micrometer controller: continuous FAST / SLOW serial control.

  New commands (115200 baud; terminate each command with CR or LF):
    FAST [+|-]    Continuous fast travel, default direction +
    SLOW [+|-]    Continuous slow travel, default direction +
    VFAST 800     Set fast preset in STEP pulses/second (stationary only)
    VSLOW 200     Set slow preset in STEP pulses/second (stationary only)
    SPEEDS        Show presets
    STOP          Controlled deceleration; NOT an emergency power cut

  FAST/SLOW are latched: send once, then STOP to stop. They also stop at
  the configured travel boundary. Stop and wait before changing direction,
  changing preset, or starting another move. Cruise speed is the requested
  pulse rate; acceleration, deceleration and limited remaining travel can
  make the instantaneous commanded rate lower.

  Positions/rates are OPEN-LOOP command estimates, not encoder feedback.
  Soft limits require correct configuration and calibration; they are NOT
  physical limit switches. A serial disconnect does not issue STOP.
  No changes to TMC2209 current settings, EN wiring, or EEPROM data layout.
*/

#include <Arduino.h>
#include <AccelStepper.h>
#include <EEPROM.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <math.h>

// ======================================================
// Hardware configuration
// ======================================================

const uint8_t DIR_PIN = 5;
const uint8_t STEP_PIN = 6;

const uint16_t MOTOR_FULL_STEPS = 200;

// Must match the actual TMC2209 hardware configuration.
// Adafruit TMC2209 default = 1/8 microstepping.
const uint8_t MICROSTEPS = 8;

// Conservative initial speed settings, in driver pulses.
// Increase only after verifying stable operation.
const float MAX_SPEED = 1600.0f;
const float ACCELERATION = 800.0f; // STEP pulses/second^2

// Continuous-motion presets. These are STEP INPUT pulses/second, not
// full motor steps/second. With 200 full steps and 1/8 microstepping,
// 1600 STEP pulses = one motor revolution.
const float DEFAULT_FAST_SPEED = 800.0f;
const float DEFAULT_SLOW_SPEED = 200.0f;
const float MIN_CONTINUOUS_SPEED = 1.0f;
const unsigned long CONTINUOUS_WATCHDOG_MS = 350UL;
// FAST/SLOW require a recurring HB heartbeat while active.

const uint32_t CONFIG_MAGIC = 0x4D433031UL;

// ======================================================
// Micrometer configuration
// ======================================================

struct MicrometerConfig {
  uint32_t magic;

  float minMM;
  float maxMM;
  float divisionMM;

  // Axial displacement per micrometer spindle revolution
  float pitchMM;

  // Motor revolutions per micrometer spindle revolution
  // Direct coupling = 1.0
  float gearRatio;

  float jogMM;

  // 0 = normal, 1 = reverse positive direction
  uint8_t reverseDirection;
};

MicrometerConfig defaults();
bool validConfig(const MicrometerConfig &c);

MicrometerConfig cfg;
MicrometerConfig draft;

AccelStepper motor(
  AccelStepper::DRIVER,
  STEP_PIN,
  DIR_PIN
);

// ======================================================
// Runtime state
// ======================================================

bool configReady = false;
bool calibrated = false;
bool wizardActive = false;
bool motionActive = false;
bool stopRequested = false;
bool continuousActive = false;
unsigned long lastHeartbeatMs = 0;

// RAM-only presets; reboot restores the defaults above.
float fastSpeed = DEFAULT_FAST_SPEED;
float slowSpeed = DEFAULT_SLOW_SPEED;

uint8_t wizardField = 0;

// Absolute micrometer reading corresponding to
// motor.currentPosition() == 0 after calibration.
float originMM = 0.0f;

char inputBuffer[64];
uint8_t inputLength = 0;
bool discardLine = false;
bool lastWasCR = false;

// Service motion during serial processing/output too. Avoid long gaps
// between run() calls when a response exceeds the hardware TX buffer.
// This is cooperative scheduling, NOT a hardware-timed pulse generator.
void serviceMotion() {
  if (motionActive) motor.run();
}

class MotionAwarePrint : public Print {
public:
  using Print::write;

  size_t write(uint8_t value) override {
    serviceMotion();
    while (Serial.availableForWrite() <= 0) {
      serviceMotion();
    }
    size_t written = Serial.write(value);
    serviceMotion();
    return written;
  }
};

MotionAwarePrint reply;

// ======================================================
// Default parameters
// ======================================================

MicrometerConfig defaults() {
  MicrometerConfig c;

  c.magic = CONFIG_MAGIC;

  c.minMM = 0.000f;
  c.maxMM = 25.000f;

  c.divisionMM = 0.001f;
  c.pitchMM = 0.500f;  // Measured spindle advance; EEPROM may override.
  c.gearRatio = 1.0f;

  c.jogMM = 0.010f;
  c.reverseDirection = 0;

  return c;
}

// ======================================================
// Validation and conversion
// ======================================================

bool validConfig(const MicrometerConfig &c) {
  if (c.magic != CONFIG_MAGIC) return false;

  if (!(c.minMM > -1000.0f &&
        c.minMM < 1000.0f)) return false;

  if (!(c.maxMM > c.minMM &&
        c.maxMM < 1000.0f)) return false;

  if (!(c.divisionMM > 0.0f &&
        c.divisionMM <= 1.0f)) return false;

  if (!(c.pitchMM > 0.0f &&
        c.pitchMM <= 10.0f)) return false;

  if (!(c.gearRatio >= 0.01f &&
        c.gearRatio <= 1000.0f)) return false;

  if (!(c.jogMM > 0.0f &&
        c.jogMM <= c.maxMM - c.minMM)) return false;

  if (c.reverseDirection > 1) return false;

  float requiredPulses =
    (c.maxMM - c.minMM) *
    MOTOR_FULL_STEPS *
    MICROSTEPS *
    c.gearRatio /
    c.pitchMM;

  // Keep positions safely within a signed 32-bit counter.
  if (!(requiredPulses > 0.0f &&
        requiredPulses < 1000000000.0f)) {
    return false;
  }

  return true;
}

float mmPerPulse() {
  return cfg.pitchMM /
    (MOTOR_FULL_STEPS * MICROSTEPS * cfg.gearRatio);
}

float currentMM() {
  return originMM +
    motor.currentPosition() * mmPerPulse();
}

// Inward rounding ensures targets stay inside the configured travel
// envelope at the pulse resolution. No artificial LONG_MAX target is used.
bool getStepLimits(long &minimum, long &maximum) {
  if (!configReady || !calibrated) return false;

  const double pulseMM = (double)mmPerPulse();
  const double low = ((double)cfg.minMM - (double)originMM) / pulseMM;
  const double high = ((double)cfg.maxMM - (double)originMM) / pulseMM;

  if (!(low > -1000000000.0 && high < 1000000000.0 && low <= high)) {
    return false;
  }

  minimum = (long)ceil(low);
  maximum = (long)floor(high);
  return minimum <= maximum;
}

uint8_t displayDigits() {
  float v = cfg.divisionMM;

  for (uint8_t d = 0; d <= 6; d++) {
    if (fabs(v - round(v)) < 0.0001f) {
      return d;
    }
    v *= 10.0f;
  }

  return 6;
}

bool parseNumber(const char *s, float &out) {
  if (s == NULL || *s == '\0') return false;

  char *endPtr;
  double value = strtod(s, &endPtr);

  if (endPtr == s) return false;

  while (*endPtr == ' ' || *endPtr == '\t') {
    endPtr++;
  }

  if (*endPtr != '\0') return false;

  // Also rejects NaN and infinity.
  if (!(value > -1000000.0 &&
        value < 1000000.0)) return false;

  out = (float)value;
  return true;
}

// ======================================================
// Display
// ======================================================

void showPosition() {
  if (!calibrated) {
    reply.println(F("Position unknown. Use C <reading>."));
    return;
  }

  reply.print(F("Estimated position: "));
  reply.print(currentMM(), displayDigits());
  reply.println(F(" mm"));

  if (motionActive) {
    if (stopRequested) {
      reply.println(F("State: STOPPING"));
    } else if (continuousActive) {
      reply.println(F("State: CONTINUOUS"));
    } else {
      reply.println(F("State: MOVING TO TARGET"));
    }
    reply.print(F("Planner speed (not measured): "));
    reply.print(motor.speed(), 1);
    reply.println(F(" STEP pulses/s"));
  } else {
    reply.println(F("State: HOLDING"));
  }
}

// Machine-readable EEPROM configuration for the desktop application.
// The values below are the effective settings, not merely source defaults.
void showConfig() {
  if (!configReady) {
    reply.println(F("CONFIG ERROR NOT_READY"));
    return;
  }
  reply.print(F("CONFIG MIN_MM ")); reply.println(cfg.minMM, 6);
  reply.print(F("CONFIG MAX_MM ")); reply.println(cfg.maxMM, 6);
  reply.print(F("CONFIG DIVISION_MM ")); reply.println(cfg.divisionMM, 6);
  reply.print(F("CONFIG PITCH_MM ")); reply.println(cfg.pitchMM, 6);
  reply.print(F("CONFIG GEAR_RATIO ")); reply.println(cfg.gearRatio, 6);
  reply.print(F("CONFIG JOG_MM ")); reply.println(cfg.jogMM, 6);
  reply.print(F("CONFIG REVERSE_DIRECTION ")); reply.println(cfg.reverseDirection);
  reply.println(F("CONFIG END"));
}

void showHelp() {
  reply.println();
  reply.println(F("=== MICROMETER CONTROLLER ==="));
  reply.println(F("Distances: mm. Speeds: STEP input pulses/s."));
  reply.println(F("FAST +     Continuous fast positive"));
  reply.println(F("FAST -     Continuous fast negative"));
  reply.println(F("SLOW +     Continuous slow positive"));
  reply.println(F("SLOW -     Continuous slow negative"));
  reply.println(F("FAST/SLOW without direction default to +."));
  reply.println(F("VFAST 800  Set fast speed, stopped only"));
  reply.println(F("VSLOW 200  Set slow speed, stopped only"));
  reply.println(F("SPEEDS     Show speed presets"));
  reply.println(F("HB         Refresh FAST/SLOW watchdog every 100 ms."));
  reply.println(F("FAST/SLOW auto-decelerate if HB is absent for 350 ms."));
  reply.println(F("Continuous motion stops at software travel limits."));
  reply.println(F("STOP and wait before changing speed/direction."));
  reply.println(F("G 1.250   Absolute target"));
  reply.println(F("M 0.050   Move +0.050 mm"));
  reply.println(F("M -0.020  Move -0.020 mm"));
  reply.println(F("+          Jog positive"));
  reply.println(F("-          Jog negative"));
  reply.println(F("J 0.005   Set jog distance"));
  reply.println(F("C 1.248   Calibrate actual reading"));
  reply.println(F("P          Show estimated position"));
  reply.println(F("STOP       Decelerate and stop"));
  reply.println(F("SETUP      Configure micrometer"));
  reply.println(F("CONFIG     Read effective EEPROM configuration"));
  reply.println(F("HELP       Show commands"));
  reply.println();
}

// ======================================================
// Configuration wizard
// ======================================================

void showWizardPrompt() {
  reply.println();

  switch (wizardField) {
    case 0:
      reply.print(F("1/7 Minimum reading (mm) ["));
      reply.print(draft.minMM, 3);
      break;

    case 1:
      reply.print(F("2/7 Maximum reading (mm) ["));
      reply.print(draft.maxMM, 3);
      break;

    case 2:
      reply.print(F("3/7 Graduation (mm) ["));
      reply.print(draft.divisionMM, 6);
      break;

    case 3:
      reply.print(F("4/7 Spindle advance (mm/rev) ["));
      reply.print(draft.pitchMM, 6);
      break;

    case 4:
      reply.print(F("5/7 Motor/spindle ratio ["));
      reply.print(draft.gearRatio, 3);
      break;

    case 5:
      reply.print(F("6/7 Default jog (mm) ["));
      reply.print(draft.jogMM, 6);
      break;

    case 6:
      reply.print(F("7/7 Reverse direction (0/1) ["));
      reply.print(draft.reverseDirection);
      break;
  }

  reply.println(F("]:"));
  reply.println(F("Enter value, or Enter to keep default."));
}

void startWizard() {
  if (motionActive) {
    reply.println(F("Stop motion before SETUP."));
    return;
  }

  draft = configReady ? cfg : defaults();

  wizardActive = true;
  wizardField = 0;

  reply.println();
  reply.println(F("=== MICROMETER SETUP ==="));
  reply.println(F("Enter parameters in order."));
  showWizardPrompt();
}

void acceptWizardInput(char *text) {
  if (*text != '\0') {
    float v;

    if (!parseNumber(text, v)) {
      reply.println(F("Invalid number. Try again."));
      return;
    }

    switch (wizardField) {
      case 0: draft.minMM = v; break;
      case 1: draft.maxMM = v; break;
      case 2: draft.divisionMM = v; break;
      case 3: draft.pitchMM = v; break;
      case 4: draft.gearRatio = v; break;
      case 5: draft.jogMM = v; break;

      case 6:
        if (!(v == 0.0f || v == 1.0f)) {
          reply.println(F("Direction must be 0 or 1."));
          return;
        }
        draft.reverseDirection = (uint8_t)v;
        break;
    }
  }

  wizardField++;

  if (wizardField < 7) {
    showWizardPrompt();
    return;
  }

  draft.magic = CONFIG_MAGIC;

  if (!validConfig(draft)) {
    reply.println(F("Invalid parameter combination."));
    reply.println(F("Please re-enter the setup."));
    wizardField = 0;
    showWizardPrompt();
    return;
  }

  cfg = draft;
  EEPROM.put(0, cfg);

  motor.setPinsInverted(
    cfg.reverseDirection != 0,
    false,
    false
  );

  motor.setCurrentPosition(0);

  originMM = 0.0f;
  calibrated = false;
  configReady = true;
  wizardActive = false;

  reply.println();
  reply.println(F("Configuration saved to EEPROM."));
  reply.println(F("Now use C <actual reading> to calibrate."));
  showHelp();
}

// ======================================================
// Motion control
// ======================================================

void showSpeeds() {
  reply.print(F("FAST = "));
  reply.print(fastSpeed, 1);
  reply.print(F("; SLOW = "));
  reply.print(slowSpeed, 1);
  reply.print(F("; ceiling = "));
  reply.print(MAX_SPEED, 1);
  reply.println(F(" STEP pulses/s"));
  reply.println(F("Presets are RAM-only; reboot restores defaults."));
}

void setContinuousPreset(bool fast, float pulsesPerSecond) {
  if (motionActive) {
    reply.println(F("ERROR: STOP and wait before changing speed."));
    return;
  }

  if (!(pulsesPerSecond >= MIN_CONTINUOUS_SPEED &&
        pulsesPerSecond <= MAX_SPEED)) {
    reply.print(F("ERROR: Speed must be "));
    reply.print(MIN_CONTINUOUS_SPEED, 1);
    reply.print(F(" to "));
    reply.print(MAX_SPEED, 1);
    reply.println(F(" STEP pulses/s."));
    return;
  }

  if ((fast && pulsesPerSecond < slowSpeed) ||
      (!fast && pulsesPerSecond > fastSpeed)) {
    reply.println(F("ERROR: Require SLOW <= FAST."));
    return;
  }

  if (fast) fastSpeed = pulsesPerSecond;
  else slowSpeed = pulsesPerSecond;
  showSpeeds();
}

void startContinuous(bool fast, int8_t direction) {
  if (!configReady || !calibrated) {
    reply.println(F("ERROR: Complete SETUP and calibrate with C first."));
    return;
  }
  if (motionActive) {
    reply.println(F("ERROR: Already moving. STOP and wait first."));
    return;
  }
  if (direction != 1 && direction != -1) {
    reply.println(F("ERROR: Direction must be + or -."));
    return;
  }

  long minimum, maximum;
  if (!getStepLimits(minimum, maximum)) {
    reply.println(F("ERROR: Invalid software travel limits."));
    return;
  }

  const long here = motor.currentPosition();
  if (here < minimum || here > maximum) {
    reply.println(F("ERROR: Estimated position outside range. Recalibrate."));
    return;
  }

  const long boundary = direction > 0 ? maximum : minimum;
  if (boundary == here) {
    reply.println(F("Already at the software limit in that direction."));
    return;
  }

  const float requestedSpeed = fast ? fastSpeed : slowSpeed;
  if (!(requestedSpeed >= MIN_CONTINUOUS_SPEED &&
        requestedSpeed <= MAX_SPEED)) {
    reply.println(F("ERROR: Invalid preset. Check default speed constants."));
    return;
  }

  // Moving toward the REAL configured travel endpoint gives a constant
  // cruise segment plus acceleration/deceleration and safe soft-limit
  // stopping. It does not require the operator to enter a target position.
  motor.setMaxSpeed(requestedSpeed);
  motor.setAcceleration(ACCELERATION);
  motor.moveTo(boundary);
  continuousActive = true;
  lastHeartbeatMs = millis();
  stopRequested = false;
  motionActive = true;

  reply.print(fast ? F("FAST ") : F("SLOW "));
  reply.print(direction > 0 ? F("+ ") : F("- "));
  reply.print(requestedSpeed, 1);
  reply.println(F(" STEP pulses/s cruise requested."));
  reply.println(F("Running until STOP or software travel limit."));
}

void gotoMM(float targetMM) {
  if (!calibrated) {
    reply.println(F("ERROR: Calibrate first with C."));
    return;
  }

  if (motionActive) {
    reply.println(F("ERROR: Already moving. Use STOP."));
    return;
  }

  if (targetMM < cfg.minMM || targetMM > cfg.maxMM) {
    reply.println(F("ERROR: Target outside configured range."));
    return;
  }

  float desiredPulses =
    (targetMM - originMM) / mmPerPulse();

  if (!(desiredPulses > -1000000000.0f &&
        desiredPulses < 1000000000.0f)) {
    reply.println(F("ERROR: Position counter overflow."));
    return;
  }

  long targetSteps = lroundf(desiredPulses);
  long minimum, maximum;
  if (!getStepLimits(minimum, maximum)) {
    reply.println(F("ERROR: Invalid software travel limits."));
    return;
  }
  if (targetSteps < minimum) targetSteps = minimum;
  if (targetSteps > maximum) targetSteps = maximum;

  if (targetSteps == motor.currentPosition()) {
    reply.println(F("Already at nearest motor position."));
    showPosition();
    return;
  }

  // A previous SLOW/FAST move must not alter normal positioning speed.
  motor.setMaxSpeed(MAX_SPEED);
  motor.setAcceleration(ACCELERATION);
  motor.moveTo(targetSteps);

  continuousActive = false;
  motionActive = true;
  stopRequested = false;

  reply.print(F("Moving to "));
  reply.print(targetMM, displayDigits());
  reply.println(F(" mm"));
}

void moveRelativeMM(float deltaMM) {
  if (!calibrated) {
    reply.println(F("Calibrate first with C."));
    return;
  }

  gotoMM(currentMM() + deltaMM);
}

void calibrateMM(float actualMM) {
  if (motionActive) {
    reply.println(F("Stop and wait before calibration."));
    return;
  }

  if (actualMM < cfg.minMM || actualMM > cfg.maxMM) {
    reply.println(F("ERROR: Calibration outside range."));
    return;
  }

  // No motor movement here.
  // The observed mechanical position becomes our reference.
  motor.setCurrentPosition(0);
  originMM = actualMM;
  calibrated = true;

  reply.println(F("Calibration accepted."));
  showPosition();
}

void requestStop() {
  if (!motionActive) {
    reply.println(F("Motor is already stationary."));
    return;
  }

  if (stopRequested) {
    reply.println(F("Already stopping. Wait for Motion stopped."));
    return;
  }

  // Controlled deceleration. NOT an emergency power cut.
  // stop() replaces the target and rounds its stopping distance upward.
  // Never let that new target extend beyond the already-planned endpoint,
  // particularly if STOP arrives while approaching a software limit.
  const long oldTarget = motor.targetPosition();
  const float velocity = motor.speed();
  motor.stop();
  if ((velocity > 0.0f && motor.targetPosition() > oldTarget) ||
      (velocity < 0.0f && motor.targetPosition() < oldTarget)) {
    motor.moveTo(oldTarget);
  }
  stopRequested = true;

  reply.println(F("Decelerating to stop..."));
}

// ======================================================
// Command parser
// ======================================================

void handleCommand(char *line) {
  // Trim leading whitespace.
  while (*line == ' ' || *line == '\t') {
    line++;
  }

  // Trim trailing whitespace.
  size_t n = strlen(line);
  while (n > 0 &&
         (line[n - 1] == ' ' || line[n - 1] == '\t')) {
    line[--n] = '\0';
  }

  if (wizardActive) {
    acceptWizardInput(line);
    return;
  }

  if (*line == '\0') return;

  char *cmd = strtok(line, " \t");
  char *arg = strtok(NULL, " \t");
  char *extra = strtok(NULL, " \t");

  if (extra != NULL) {
    reply.println(F("ERROR: Too many arguments."));
    return;
  }

  for (char *p = cmd; *p; p++) {
    *p = (char)toupper((unsigned char)*p);
  }

  if (strcmp(cmd, "HB") == 0) {
    if (arg != NULL) {
      reply.println(F("ERROR: HB takes no arguments."));
      return;
    }
    if (continuousActive && motionActive && !stopRequested) {
      lastHeartbeatMs = millis();
    }
    return;
  }

  if (strcmp(cmd, "STOP") == 0) {
    requestStop();
    return;
  }

  if (strcmp(cmd, "HELP") == 0) {
    showHelp();
    return;
  }

  if (strcmp(cmd, "CONFIG") == 0) {
    if (arg != NULL) {
      reply.println(F("ERROR: CONFIG takes no arguments."));
    } else {
      showConfig();
    }
    return;
  }

  if (strcmp(cmd, "SETUP") == 0) {
    startWizard();
    return;
  }

  if (!configReady) {
    reply.println(F("Complete SETUP first."));
    return;
  }

  if (strcmp(cmd, "SPEEDS") == 0) {
    if (arg != NULL) {
      reply.println(F("ERROR: SPEEDS takes no arguments."));
      return;
    }
    showSpeeds();
    return;
  }

  if (strcmp(cmd, "FAST") == 0 || strcmp(cmd, "SLOW") == 0) {
    int8_t direction = 1;
    if (arg != NULL) {
      if (strcmp(arg, "+") == 0 || strcmp(arg, "+1") == 0 ||
          strcmp(arg, "1") == 0) {
        direction = 1;
      } else if (strcmp(arg, "-") == 0 || strcmp(arg, "-1") == 0) {
        direction = -1;
      } else {
        reply.println(F("ERROR: Use FAST +/- or SLOW +/-."));
        return;
      }
    }
    startContinuous(strcmp(cmd, "FAST") == 0, direction);
    return;
  }

  if (strcmp(cmd, "VFAST") == 0 || strcmp(cmd, "VSLOW") == 0) {
    float speedValue;
    if (!parseNumber(arg, speedValue)) {
      reply.println(F("ERROR: Supply speed in STEP pulses/s."));
      return;
    }
    setContinuousPreset(strcmp(cmd, "VFAST") == 0, speedValue);
    return;
  }

  if (strcmp(cmd, "P") == 0) {
    showPosition();
    return;
  }

  if (strcmp(cmd, "+") == 0) {
    moveRelativeMM(cfg.jogMM);
    return;
  }

  if (strcmp(cmd, "-") == 0) {
    moveRelativeMM(-cfg.jogMM);
    return;
  }

  float value;

  if (!parseNumber(arg, value)) {
    reply.println(F("ERROR: Missing or invalid mm value."));
    return;
  }

  if (strcmp(cmd, "C") == 0) {
    calibrateMM(value);
  }

  else if (strcmp(cmd, "G") == 0) {
    gotoMM(value);
  }

  else if (strcmp(cmd, "M") == 0) {
    moveRelativeMM(value);
  }

  else if (strcmp(cmd, "J") == 0) {
    if (motionActive) {
      reply.println(F("Change jog after motion stops."));
      return;
    }

    if (!(value > 0.0f &&
          value <= cfg.maxMM - cfg.minMM)) {
      reply.println(F("ERROR: Invalid jog distance."));
      return;
    }

    cfg.jogMM = value;
    EEPROM.put(0, cfg);

    reply.print(F("Jog distance = "));
    reply.print(cfg.jogMM, 6);
    reply.println(F(" mm"));
  }

  else {
    reply.println(F("Unknown command. Type HELP."));
  }
}

// ======================================================
// Non-blocking serial input
// ======================================================

void pollSerial() {
  // Bound receive work per loop; also service motion for each byte.
  uint8_t budget = 16;
  while (budget-- > 0 && Serial.available() > 0) {
    serviceMotion();
    const char c = (char)Serial.read();

    if (c == '\n' || c == '\r') {
      // Treat CRLF as ONE newline. A genuinely empty line advances the
      // setup wizard and keeps the default, as the original prompt says.
      if (c == '\n' && lastWasCR) {
        lastWasCR = false;
        continue;
      }
      lastWasCR = (c == '\r');

      if (!discardLine && (inputLength > 0 || wizardActive)) {
        inputBuffer[inputLength] = '\0';
        handleCommand(inputBuffer);
      }
      inputLength = 0;
      discardLine = false;
    } else {
      lastWasCR = false;
      if (!discardLine) {
        if (inputLength < sizeof(inputBuffer) - 1) {
          inputBuffer[inputLength++] = c;
        } else {
          inputLength = 0;
          discardLine = true;
          reply.println(F("ERROR: Input line too long."));
        }
      }
    }
    serviceMotion();
  }
}

// ======================================================
// Arduino setup and loop
// ======================================================

void setup() {
  Serial.begin(115200);

  motor.setMaxSpeed(MAX_SPEED);
  motor.setAcceleration(ACCELERATION);
  motor.setMinPulseWidth(5);

  EEPROM.get(0, cfg);

  reply.println();
  reply.println(F("MICROMETER CONTROLLER STARTED"));

  if (validConfig(cfg)) {
    configReady = true;

    motor.setPinsInverted(
      cfg.reverseDirection != 0,
      false,
      false
    );

    reply.println(F("Saved configuration loaded."));
    reply.println(F("Actual position not yet calibrated."));

    showHelp();
    reply.println(F("Use C <actual reading> before movement."));
  }

  else {
    configReady = false;
    // Do not enter the interactive wizard automatically: doing so would
    // interpret the GUI's CONFIG request as a wizard answer at startup.
    // The desktop application can read CONFIG ERROR NOT_READY and explicitly
    // launch SETUP when the operator confirms the hardware parameters.
    reply.println(F("No valid saved configuration. Use SETUP."));
  }
}

void loop() {
  serviceMotion();
  pollSerial();
  serviceMotion();

  // A lost USB connection, frozen GUI, or stalled input stream must not
  // leave a FAST/SLOW move latched indefinitely. This is a soft stop only.
  if (continuousActive && motionActive && !stopRequested &&
      (unsigned long)(millis() - lastHeartbeatMs) > CONTINUOUS_WATCHDOG_MS) {
    requestStop();
    reply.println(F("Continuous jog watchdog timeout."));
  }

  // isRunning() checks both target distance and planner speed.
  if (motionActive && !motor.isRunning()) {
    const bool wasContinuous = continuousActive;
    const bool wasStopped = stopRequested;
    motionActive = false;
    continuousActive = false;
    stopRequested = false;
    motor.setMaxSpeed(MAX_SPEED);

    if (wasStopped) {
      reply.println(F("Motion stopped."));
    } else if (wasContinuous) {
      reply.println(F("Continuous motion stopped at software travel limit."));
    } else {
      reply.println(F("Target command completed."));
    }

    // Driver enable/current settings are unchanged. Position is open-loop.
    showPosition();
  }
}

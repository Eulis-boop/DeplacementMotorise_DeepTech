# DeepTech — Motorized Micrometric Stage (FAST/SLOW gamepad build)

This version uses the **teammate's `Micrometer_Continuous_Control.ino` as the firmware base**, retaining its positional and preset-speed commands. Python no longer sends `V`: sticks select `FAST +/-` or `SLOW +/-`, and the PC transmits `HB` every 100 ms while jogging. Arduino requests a controlled stop when `HB` is absent for more than 350 ms.

## Control mapping (BEITONG over USB, verified axes)

| Control | Action | Serial command |
|---|---|---|
| Left stick right/left (axis 0) | Continuous fast forward/backward | `FAST +` / `FAST -` |
| Right stick right/left (axis 2) | Continuous slow forward/backward | `SLOW +` / `SLOW -` |
| Release sticks | Controlled deceleration | `STOP` |
| B (button 1) | STOP; release sticks to neutral to rearm | `STOP` |
| LT (axis 4) | One negative increment | `M -distance` |
| RT (axis 5) | One positive increment | `M distance` |

Fine stick takes priority if both sticks are moved. The sticks select **fixed presets**, not proportional analog speed. Transitioning between modes requires a STOP and confirmation `State: HOLDING` before the next command. The firmware speed presets are 800 STEP pulses/s (FAST) and 200 STEP pulses/s (SLOW); they can be changed while stationary with `VFAST <steps/s>` and `VSLOW <steps/s>`.

## Serial commands

All commands are newline-delimited ASCII at 115200 baud. `C`, `G`, `M`, `P`, `STOP`, `FAST +/-`, `SLOW +/-`, `VFAST`, `VSLOW`, `SPEEDS`, `SETUP` and `HELP` are retained. `HB` is a new one-way watchdog refresh (no serial reply). An isolated `FAST +/-` or `SLOW +/-` command without recurring `HB` **must stop automatically** after ~350 ms + deceleration time.

## Running

On macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

On Windows (PowerShell):

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

The firmware is built and uploaded **separately** using Arduino IDE and AccelStepper. Run only one serial client at a time. On Uno opening USB serial generally resets the MCU and requires new calibration.

## Safety and commissioning

- **Experimental; not yet compiled on an Arduino Uno or verified physically.** Compile/upload the integrated `.ino` in Arduino IDE and verify `HELP` lists `HB` before testing sticks.
- Turn off motor power when changing motor wiring or couplings. First test command recognition with motor power disconnected.
- Verify saved EEPROM values via SETUP; `pitchMM` *source default* was corrected from `0.050` to measured `0.500 mm/rev`, but stored EEPROM parameters override it.
- `MAX_POSITION_MM = 25.1` in Python versus default `maxMM = 25.0` in firmware. Confirm physical safe limits and align both configurations before motion.
- Micros​tepping 1/8 is an assumption until physically verified; commanded position is not measured position. Missed steps invalidate position estimates.
- The firmware `HB` watchdog does not provide a hardware emergency stop; stopping occurs through AccelStepper deceleration and may overshoot physical constraints. Provide accessible physical power isolation and preferably limit switches.
- The watchdog covers continuous FAST/SLOW **only**, not G/M moves. In the event of a USB disconnect or app crash during any movement, independently isolate power if necessary and recalibrate.
- The GUI does not simulate continuous sticks in Simulation mode; test Pygame axis mapping separately using `diagnostic_sticks.py`.

## Files

- `main.py`: Qt GUI and serialized motion state management
- `gamepad_controller.py`: Pygame axes/buttons and stick mode selection
- `arduino_protocol.py`: human-readable reply parser
- `serial_manager.py`: Qt serial communication
- `motor_controller.py` / `motor_config.py`: nominal software simulation
- `Micrometer_Continuous_Control.ino`: teammate-based firmware with HB watchdog
- `tests/test_protocol.py`: hardware-free protocol checks


## Configuration de la platine (EEPROM)

The **Configurer la platine…** window is available in *Arduino USB* mode only
when the stage is idle. It first reads the seven actual EEPROM parameters with
`CONFIG` (new firmware extension). The values are minimum/maximum readings,
micrometer graduation, spindle advance per revolution, motor-to-spindle ratio,
default jog increment, and reverse-direction flag.

After physically confirming the values, the user can launch `SETUP`. The GUI
sends each number **only after** Arduino prints the matching numbered wizard
prompt. After `Configuration saved to EEPROM.` the GUI re-reads `CONFIG`,
updates the allowable range, and requires **new physical calibration** using C.
All real motion is blocked until configuration has been read, checked, and the
position manually initialized. Never infer the actual travel from software.

`CONFIG` responses are `CONFIG MIN_MM ...`, `CONFIG MAX_MM ...`,
`CONFIG DIVISION_MM ...`, `CONFIG PITCH_MM ...`, `CONFIG GEAR_RATIO ...`,
`CONFIG JOG_MM ...`, `CONFIG REVERSE_DIRECTION ...`, and `CONFIG END`.
A valid empty EEPROM responds `CONFIG ERROR NOT_READY`; the editor can
then start the wizard using measured mechanical values.

If SETUP hangs or its prompts mismatch, power down the motor and reconnect the
Arduino serial port to clear its interactive wizard; do **not** resume motion
until `CONFIG` and a fresh calibration are confirmed. Editing a configuration
is not a physical safety interlock. Changing driver microstepping or motor
hardware still requires independent inspection.

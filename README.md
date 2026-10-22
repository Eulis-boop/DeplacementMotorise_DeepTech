# DeepTech — Motorized Micrometric Translation Stage

**Course:** Développement des produits technologiques "DeepTech"  
**Project:** Déplacement motorisé  

## Overview

This project replaces manual adjustment of a single-axis micrometric translation stage with stepper-motor positioning. A Python desktop application provides manual position initialization, incremental motion, absolute positioning, visualized estimated position, serial-device connection, event logging, and optional gamepad control. An Arduino Uno R3 generates STEP/DIR pulses through a TMC2209 driver to move a bipolar NEMA 17 motor.

The software is deliberately split between a **hardware-independent simulator** and **Arduino USB mode**. The Arduino owns real-motion execution and step counting. Neither mode measures physical position with a dedicated encoder.

## System architecture

```text
    PySide6 GUI                  Gamepad (pygame)
       |                               |
       +----------- requests ----------+
                       |
             GUI motion validation
                       |
             +---------+---------+
             |                   |
       Simulation model      QtSerialPort USB
                                 |
                         Arduino Uno R3
                         AccelStepper firmware
                                 |
                            STEP / DIR
                                 |
                        TMC2209 → NEMA 17
                                 |
                       Micrometer → 1-axis stage
```

## Hardware and nominal specifications

| Item | Specification / status |
|---|---|
| Microcontroller | Arduino Uno R3 |
| Stepper driver | TMC2209, STEP/DIR, external microstep setting to verify |
| Motor | Bipolar NEMA 17; 200 full steps/revolution; nominal 12 V, 350 mA/phase, 20 N·cm holding torque (provided motor specification) |
| Micrometer spindle pitch | **0.500 mm/revolution**, experimentally checked with one full turn |
| Motor/spindle ratio | Assumed direct coupling 1:1; verify physically |
| Simulated range | 0.0–25.1 mm (observed, **not a safety-rated limit**) |
| Firmware source defaults | 0.0–25.0 mm, `divisionMM=0.001`, `pitchMM=0.500` — check against actual engraved scale and EEPROM |
| Target command increment | 0.01 mm; physical absolute accuracy **not yet established** |
| Serial baud rate | 115200, newline-delimited ASCII |

For 200 full steps/revolution, 1/8 microstepping, 1:1 coupling, and 0.500 mm/revolution:

```text
STEP pulses/mm = (200 × 8 × 1) / 0.500 = 3200
STEP pulses for 0.01 mm = 32
Nominal commanded increment per pulse = 0.0003125 mm
```

**Resolution is not accuracy:** backlash, missed steps, load, mechanical compliance, and microstep nonlinearity can cause physical positioning error. A target such as ±0.01 mm positioning accuracy requires independent measurement and repeatability tests.

### Critical firmware configuration

The Arduino firmware stores parameters in **EEPROM**. Updating defaults in `.ino` does **not** overwrite a valid stored configuration. Before powered motion, verify the saved min/max readings, graduation, spindle pitch, gear ratio, jog increment, direction, driver current/microstep setting and mechanical clearance with the team. Use `SETUP` through a serial terminal with the GUI disconnected when correction is needed. Do not assume the 25.1-mm observed reading is a safe fully usable travel range.

## Repository files

```text
main.py                     PySide6 GUI and state management
motor_controller.py         Integer-pulse position simulator
motor_config.py             Nominal simulator parameters
serial_manager.py           Non-blocking Qt serial connection
arduino_protocol.py         Human-readable Arduino message parsing
gamepad_controller.py       Optional pygame controller events
Micrometer_Continuous_Control.ino  Arduino firmware (integrated team source)
requirements.txt            Runtime Python dependencies
requirements-build.txt      Build-time dependencies
.github/workflows/build.yml Build artifacts on three OS runners
tests/                      Hardware-free unit tests
```

## User interface guide

1. **Connexion et mode:** choose *Simulation* (no hardware) or *Arduino USB*; refresh available ports, select the USB serial port, and connect. Opening a Uno serial port typically resets it.
2. **Configuration confirmation:** only in Arduino mode, verify the *physical* system configuration and check the confirmation box before calibration or motion. This checkbox is not a sensor or safety interlock.
3. **Initialisation:** enter the observed micrometer reading in millimeters, with a period or comma (`5.00` or `5,00`), then select *Initialiser*. In Arduino mode this sends `C 5.00` and **does not physically move** the stage.
4. **Position estimée:** monitor the step-estimated position and relative displacement from initialization. Without an external sensor, this is not the independently measured actual position.
5. **Déplacement relatif:** select a 0.01, 0.10, 0.50 or 1.00 mm increment and press *Avancer* or *Reculer*; Arduino receives `M ±distance`.
6. **Déplacement absolu:** enter a desired micrometer reading and press *Aller à la position*; Arduino receives `G target`.
7. **Arrêt:** STOP asks Arduino to decelerate. Wait for confirmation and the subsequent position/idle report; it is **not a hardware emergency stop**.
8. **Journal des événements:** inspect sent commands, Arduino replies and connection errors. Do not issue a second motion while the current request is pending.

### Gamepad (optional)

Click *Détecter la manette*. The tested BEITONG controller was identified on macOS as an Xbox 360 Controller with **no hats**. The current mapping is:

| Input | Action | Tested mapping (not guaranteed on another OS/connection mode) |
|---|---|---|
| LT | One incremental backward request | Axis 4 |
| RT | One incremental forward request | Axis 5 |
| B | STOP request | Button 1 |
| Left stick (horizontal) | Continuous analog jog, max 0.30 mm/s | Axis 0 |
| Right stick (horizontal) | Continuous fine jog, max 0.03 mm/s | Axis 2 |

Trigger press is detected at an axis value >= 0.5 and rearmed when the axis returns <= -0.2. These thresholds **assume a rest value near -1**. A trigger held down does not produce continuous movement. The mapping can vary across controller modes, operating systems, and SDL versions. Verify without motor power first. The connection instability of the wireless USB receiver has **not** been resolved; a data-capable USB connection is recommended for diagnosis. The controller event dispatcher does not bypass GUI motion guards.

## Run from source (Windows, Linux, macOS)

Prerequisites: Python 3.11–3.13 recommended for this prototype, a compatible USB serial driver, and the Arduino firmware uploaded separately.

**Windows PowerShell:**

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

**macOS / Linux shell:**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

Linux may require serial-port group permissions (for example membership of `dialout`) followed by logout/login; permission names differ by distribution. Close Arduino IDE Serial Monitor before opening the same port from the GUI. USB device paths vary by platform and must be chosen from the detected list.

## Build desktop applications

PyInstaller creates platform-specific artifacts and **does not cross-compile**. Build Windows executables on Windows, macOS apps on macOS, and Linux binaries on Linux. Artifacts may still need platform-specific signing, drivers, and testing.

```bash
python -m pip install -r requirements.txt -r requirements-build.txt
python -m PyInstaller --noconfirm --clean --windowed --onedir --name DeepTechController main.py
```

Outputs are in `dist/`; on macOS, the `.app` bundle is generated by the macOS builder. Windows creates a `.exe` inside its distributable folder; Linux produces a binary and bundled libraries. Distribute the **whole `dist/DeepTechController/` directory**, or the `.app` bundle on macOS, not just individual library files.

If present in the repository, `.github/workflows/build.yml` provides separate `windows-latest`, `ubuntu-latest`, and `macos-latest` build jobs. Artifacts are uploaded to the workflow run. CI packaging only verifies that a build completes; it does not test the physical driver/motor or wireless gamepad. macOS apps may display Gatekeeper warnings without code signing/notarization, and Windows executables may trigger reputation warnings.

## Serial protocol (existing firmware)

115200 baud, UTF-8/ASCII compatible, one command per newline. Commands use **millimeters**, not STEP pulse counts.

| Sent command | Meaning |
|---|---|
| `C 5.00` | Calibrate observed reading (no motion) |
| `M 0.10` / `M -0.10` | Signed relative motion |
| `G 7.88` | Absolute target reading |
| `P` | Report estimated reading and state |
| `+`, `-`, `J 0.01` | Firmware-side jog and jog increment |
| `STOP` | Controlled deceleration |
| `V 0.030` / `V -0.030` | Continuously refreshed signed velocity in mm/s for analog sticks |
| `V 0` | Decelerate and stop analog jog |
| `FAST +/-`, `SLOW +/-` | Latched preset continuous commands; **no watchdog** |
| `VFAST 800`, `VSLOW 200` | Configure preset speeds in STEP pulses/s |
| `SETUP` | Interactive configuration wizard (perform separately in serial terminal) |
| `HELP` | Print firmware help |

Common firmware responses include `Calibration accepted.`, `Moving to ...`, `Target command completed.`, `Motion stopped.`, `Motor is already stationary.`, `Estimated position: ... mm`, `State: HOLDING` and `ERROR: ...`. The GUI uses a text parser rather than sequence-numbered acknowledgements. Future work should make acknowledgements machine-readable and match them to command IDs to improve recovery from reordered/missing messages.

## Safety and limitations

- The displayed position is estimated from commanded/recorded steps, **not measured by an encoder**.
- The **V analog jog** has a 250 ms firmware command watchdog that requests controlled deceleration if velocity updates stop. However, legacy FAST/SLOW commands remain latched without a watchdog. A blocked GUI event loop may still create unexpected motion; a hardware emergency stop and physical limit switches are recommended.
- The `STOP` instruction performs gradual deceleration; a suitable physical means of isolating motor power must remain accessible during testing. Do not connect or disconnect motor wires while the driver is powered.
- Motor driver current must be set for the **350 mA/phase nominal motor** and the specific TMC2209 module, observing RMS/peak distinctions.
- Verify direction, microstepping, saved EEPROM parameters, clearances, and min/max travel prior to any physical test; begin with small movements away from end stops.
- Arduino and Python may lose synchronization if the motor stalls, is manually moved, or reconnects during motion. Re-establish a physical reference when uncertain.
- GUI software limits and the confirmation checkbox are not a hardware-rated safety interlock.

## Authors
- **Team 5:** 

        - CASTILLO TURRUBIARTES Eunice Saraí

        - LIU Binhao

        - WANG Qia

        - LEI Yumian

  École Centrale de Lille
- **M. Simon BOUVEL**

  École Centrale de Lille



## Integrated firmware notes (October 2026)

The integrated firmware preserves the teammate's FAST/SLOW preset controller and additionally accepts `V <signed mm/s>` from Python. `V` uses a 250 ms watchdog and restricts speeds to ±0.30 mm/s; reversing requires a completed stop. The driver accelerates/decelerates under AccelStepper and uses configured software position limits. **These are not hardware interlocks.** The firmware's default micrometer pitch was corrected from `0.050` to `0.500 mm/rev`, but existing EEPROM overrides defaults: confirm with `SETUP` before mechanical tests.

**Validation status:** Python syntax and static compatibility can be checked without hardware; Arduino compilation, actual velocity behavior, USB disconnect, limit braking, and STOP reliability require physical/IDE validation before connecting to the micrometer.

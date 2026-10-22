# DeepTech — Déplacement Motorisé

**Course:** Développement des produits technologiques DeepTech  
**Project:** Déplacement motorisé  
**Institution:** École Centrale de Lille

## Overview

This project motorizes the positioning of a single-axis micrometric translation stage. A desktop application controls a NEMA 17 stepper motor through an Arduino Uno R3 and a TMC2209 STEP/DIR driver. It supports manual position initialization, incremental movements, absolute positioning, and optional continuous motion through a gamepad.

The application offers **Simulation** and **Arduino USB** modes. In either mode, displayed positions are **estimates based on step counts**, not measurements obtained from a position sensor. Positioning accuracy must be established experimentally.

## System architecture

```text
             PySide6 desktop application
                  |           |
          GUI controls     BEITONG gamepad
                  \           /
                  Motion requests
                         |
               +---------+---------+
               |                   |
          Simulation             USB serial
          step model             115200 baud
                                   |
                             Arduino Uno R3
                             AccelStepper
                                   |
                              STEP / DIR
                                   |
                          TMC2209 driver
                                   |
                           NEMA 17 motor
                                   |
                        Micrometer / stage
```

### Repository structure

| File | Purpose |
|---|---|
| `main.py` | PySide6 interface and motion state management |
| `plate_config_dialog.py` | Editor for the stage's mechanical parameters |
| `gamepad_controller.py` | Pygame input: analog sticks, LT/RT, STOP |
| `serial_manager.py` | Nonblocking communication over USB serial |
| `arduino_protocol.py` | Interpretation of firmware responses |
| `motor_controller.py` | Hardware-free movement simulator |
| `motor_config.py` | Nominal simulator parameters |
| `Micrometer_Continuous_Control.ino` | Arduino firmware, position control, preset-speed jogging, configuration |
| `requirements.txt` | Python runtime dependencies |
| `.github/workflows/build-desktop.yml` | Builds downloadable desktop apps for several operating systems |

## Hardware and mechanical parameters

The current prototype uses an **Arduino Uno R3**, **TMC2209**, and a **NEMA 17** motor (200 full steps per revolution). The reference micrometer was observed to advance **0.500 mm per revolution**, with a direct 1:1 motor-to-spindle coupling assumed. The driver microstep mode is assumed to be **1/8 until physically verified**.

For those nominal conditions:

```text
STEP pulses per mm = (200 full steps/rev × 8 microsteps/full step) / 0.500 mm/rev
                   = 3200 pulses/mm
0.01 mm             = 32 STEP pulses
```

The current micrometer's observed usable reading range is approximately 0–25 mm. **Physical limits and the effective EEPROM configuration must be verified on the actual assembly**; neither an observed graduation nor a software limit is a safety-rated travel stop. The simulator's parameters and the Arduino's stored parameters can differ.

### Positioning performance

The UI accepts targets in increments of **0.01 mm**. This is a *command resolution*, not a guarantee of ±0.01 mm mechanical accuracy. Backlash, friction, missed steps, microstep nonlinearity and measurement uncertainty affect accuracy and repeatability. If the motor stalls or steps are lost, recalibrate using the real micrometer reading.

## Desktop application — user guide

The interface is in French.

1. **Connexion et mode:** choose `Simulation` or `Arduino USB`. In USB mode, choose the serial port and click `Connecter`.
2. **Configurer la platine…:** read the active mechanical parameters with `Lire Arduino` or edit the parameters and save them to the Arduino using `Enregistrer dans Arduino`.
3. **Initialisation:** enter the reading physically shown on the micrometer and click `Initialiser`. This sets a reference; calibration is **not** a homing movement.
4. **Position estimée:** inspect the estimated position and the displacement relative to the initial reading.
5. **Déplacement relatif:** choose an increment (0.01, 0.10, 0.50 or 1.00 mm), then `Avancer` or `Reculer`.
6. **Déplacement absolu:** enter a target reading in mm, then click `Aller à la position`.
7. **STOP:** requests a controlled deceleration. It is **not** a hardware emergency stop.
8. **Journal des événements:** displays Arduino messages and application events for diagnostics.

### Configuring another micrometer stage

`Configurer la platine…` provides seven parameters managed by the firmware's `SETUP` configuration wizard: minimum reading, maximum reading, scale graduation, spindle advance per revolution, motor/spindle ratio, default jog increment and reversed direction.

The GUI reads the effective EEPROM settings using `CONFIG`. After changing values, Arduino saves them in EEPROM. **A new manual position initialization is required** before further real motion. Before using a different mechanical stage, verify its physical travel, coupling, limits, driving current and microstepping. Changing these values does not make arbitrary hardware automatically safe or compatible.

### Gamepad controls

The BEITONG controller was tested over a wired USB connection on macOS. Input mappings may change on other operating systems and controller modes.

| Input | Function | Serial request |
|---|---|---|
| Left stick right/left (axis 0) | Continuous fast forward/backward | `FAST +` / `FAST -` |
| Right stick right/left (axis 2) | Continuous slow forward/backward | `SLOW +` / `SLOW -` |
| Release sticks | Request controlled stop | `STOP` |
| B (button 1) | Request STOP | `STOP` |
| LT (axis 4) | One negative incremental movement | `M -distance` |
| RT (axis 5) | One positive incremental movement | `M distance` |

The sticks select preset speeds, rather than continuously scaling speed with deflection. The intended heartbeat (`HB`) refreshes continuous motion while the stick is held; verify the matching firmware is actually uploaded and that watchdog/STOP work before using this control with the stage. Continuous stick motion is not supported in simulation mode.

## Arduino firmware

Open `Micrometer_Continuous_Control.ino` with **Arduino IDE**, install **AccelStepper** (Mike McCauley), select the **Arduino Uno R3** and its serial port, then compile and upload the sketch. Disconnect motor power while changing the firmware and wiring. The desktop application and Arduino Serial Monitor cannot use the same port simultaneously.

The firmware communicates at **115200 baud**, with newline-delimited ASCII commands.

| Command | Meaning |
|---|---|
| `C 5.00` | Calibrate using the observed 5.00 mm reading (no movement) |
| `M 0.10` / `M -0.10` | Relative displacement in mm |
| `G 7.88` | Absolute target position in mm |
| `P` | Request estimated position / state |
| `FAST +` / `FAST -` | Start fast continuous movement |
| `SLOW +` / `SLOW -` | Start slow continuous movement |
| `STOP` | Request deceleration and stop |
| `HB` | Refresh continuous-jog watchdog (matching firmware required) |
| `VFAST`, `VSLOW`, `SPEEDS` | Configure or report speed presets |
| `CONFIG` | Read effective EEPROM configuration |
| `SETUP` | Interactive seven-parameter configuration wizard |
| `HELP` | Show supported firmware commands |

Upload the firmware *before* relying on newly added commands. Updating the `.ino` in GitHub does not update the physical Arduino. Parameter changes to C++ defaults do not automatically overwrite valid EEPROM values.

## Running from source

Prerequisites: Python 3.12 recommended, compatible serial USB access, and the required driver permissions.

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

**Windows PowerShell:**

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

When diagnosing USB issues on Linux, check serial-device permissions. Drivers, device names, and gamepad mappings can differ across platforms.

## Downloadable applications

GitHub Actions uses PyInstaller to build separate packages. Users **do not need to install Python** to run those packages, but still need the correct platform, system dependencies/permissions and a correctly programmed Arduino.

| Package | Hardware / OS | Content |
|---|---|---|
| `windows-x64` | Windows on Intel/AMD x64 | One `.exe` file |
| `linux-x64` | Linux on Intel/AMD x86-64 | One ELF executable |
| `linux-arm64` | Linux on ARM64 / `aarch64` | One ARM64 ELF executable |
| `macos-intel` | macOS on Intel | One visible `.app` bundle |
| `macos-apple-silicon` | macOS on Apple Silicon | One visible `.app` bundle |

The `.app` is internally a directory bundle, but appears as one application in Finder. On Windows and Linux, the single executable may be slower to launch because bundled libraries are unpacked temporarily. These are **portable application bundles**, not installers.

### Build locally

```bash
python -m pip install -r requirements.txt pyinstaller
# Windows / Linux — one executable
python -m PyInstaller --noconfirm --clean --windowed --onefile --name Deplacement_Motorise_DeepTech --collect-all pygame main.py
```

For macOS, use `--onedir --windowed` instead of `--onefile --windowed` to produce a `.app` bundle.

## Safety and validation

- The project is **open-loop**: the estimated position is not independently measured by an encoder.
- STOP is a firmware-controlled deceleration, **not an electrical emergency stop**. Keep a means of isolating motor power accessible.
- Firmware software limits, the EEPROM configuration and any heartbeat watchdog are **not safety-rated limit switches**. Check the behavior on actual hardware.
- Verify current limits on the specific TMC2209 module for the motor before operating under load.
- Do not connect or disconnect stepper motor coils while the driver is energized.
- Begin with the motor uncoupled and small movements away from physical limits. Test STOP, releasing sticks and disconnecting the controller/USB before trusting continuous movement.
- Verify configuration/calibration and redo calibration after any stall, lost steps or uncertain movement.
- Validation should include end-to-end GUI/Arduino integration, position error and repeatability measurements, and runtime checks on each packaged OS/architecture. The build workflow checks packaging, **not physical positioning accuracy**.

## Project team

- **Team 5 :** 

        - Eunice Saraí CASTILLO TURRUBIARTES
        - Binhao LIU
        - Qia WANG
        - Yumian LEI

  École Centrale de Lille
- M. Simon BOUVEL
  
  École Centrale de Lille

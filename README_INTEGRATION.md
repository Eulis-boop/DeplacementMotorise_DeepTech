# DeepTech — interface Arduino + gamepad (prototype)

The provided main.py replaces your existing one. Keep the original firmware .ino in your repository.

## Run (Mac)

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

## Protocol matched to the existing firmware

115200 baud; newline-delimited ASCII:
- `C 5.00` calibrate the observed reading, **without moving**
- `M 0.10` move forward relative
- `M -0.10` move backward relative
- `G 7.88` move to absolute target
- `P` position; `STOP` gradual deceleration

The UI updates after Arduino reports completion and its estimated position. It does not measure true physical position.

## VERY IMPORTANT — before physical movement

The provided firmware defaults to `pitchMM=0.050`, but the user measured `0.500 mm/rev` on their hardware. The firmware saves configuration in EEPROM: **changing the compiled defaults does not overwrite EEPROM**. Use the Arduino Serial Monitor and `SETUP` with your teammate, and verify all seven parameters (including pitch, permitted range, direction and motor ratio). The effective driver STEP/DIR microstep mode must also be checked. Arduino serial monitor must be closed before the GUI opens the port.

The GUI requires a manual confirmation checkbox before calibrating or commanding movement. Its software limits (0..25.1) are *not* a replacement for verified hardware limits and physical protection. The current firmware has no communication-loss watchdog. `STOP` is deceleration, not a physical emergency cutoff. Test small moves far from travel ends, with immediate access to motor power isolation.

Connecting to a Uno may cause a reset; calibrate again from the actual micrometer reading. If USB is lost during motion, the estimated position is no longer trustworthy.

## Gamepad

Click 'Détecter la manette'. One D-pad horizontal press requests one relative move using the increment selected in the GUI; button index 1 requests STOP (mapping MUST be verified for the actual controller). Continuous analog jog is not included.

## Test status

Files are syntax-checked, and the protocol parser has been unit-tested without hardware. Qt GUI and physical motion could not be exercised in this environment.

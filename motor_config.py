"""Nominal mechanical settings for the software motion simulator.

These values do not verify the TMC2209 hardware configuration or the
EEPROM settings used by the Arduino firmware. Physical limits must be
validated on the assembled stage before enabling real motion.
"""

MOTOR_STEPS_PER_REV = 200  # NEMA 17 full steps per revolution
MICROSTEPPING = 8  # Assumed external STEP/DIR resolution; verify on driver
SCREW_PITCH_MM = 0.5  # Experimentally observed spindle travel per revolution
MIN_POSITION_MM = 0.0  # Simulated lower reading
MAX_POSITION_MM = 25.1  # Observed range, not a safety-rated limit

# Nominal pulses per millimeter for a direct 1:1 coupling.
STEPS_PER_MM = MOTOR_STEPS_PER_REV * MICROSTEPPING / SCREW_PITCH_MM

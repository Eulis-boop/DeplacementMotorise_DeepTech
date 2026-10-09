MOTOR_STEPS_PER_REV = 200

# configuration verification by the driver TMC2209
MICROSTEPPING = 8

# déplacement du micrometre par tour
SCREW_PITCH_MM = 0.5

# limits used by the simulation
MIN_POSITION_MM = 0.0
MAX_POSITION_MM = 25.1

# conversion of the milimeters into impulsions STEP
STEPS_PER_MM = (
    MOTOR_STEPS_PER_REV * MICROSTEPPING / SCREW_PITCH_MM
)
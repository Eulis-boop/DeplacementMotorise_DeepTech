"""Step-quantized motion model used ONLY in simulation mode.

Real position tracking is handled by the Arduino firmware and its responses;
this class cannot measure the true physical stage position.
"""

from motor_config import (
    STEPS_PER_MM,
    MIN_POSITION_MM,
    MAX_POSITION_MM,
)

class MotionController:
    """Track a simulated position as an integer count of STEP pulses."""
    def __init__(self):
        """Create a simulator with no position reference yet."""
        self.initial_position = None
        self.current_steps = 0

    @property
    def is_initialized(self):
        return self.initial_position is not None

    @property
    def current_position(self):
        if not self.is_initialized:
            return None

        return (
            self.initial_position + self.current_steps / STEPS_PER_MM
        )

    def initialize(self, position_mm: float) -> None:
        """Set a manually observed reference without executing movement."""
        if not MIN_POSITION_MM <= position_mm <= MAX_POSITION_MM:
            raise ValueError("Initial position out of limits.")

        self.initial_position = position_mm
        self.current_steps = 0

    def move_relative(self, distance_mm: float) -> int:
        """Simulate a signed movement in millimeters and return pulse count."""
        if not self.is_initialized:
            raise ValueError("Initialise the position.")

        steps = round(distance_mm * STEPS_PER_MM)
        new_steps = self.current_steps + steps

        new_position = (
            self.initial_position + new_steps / STEPS_PER_MM
        )

        if not MIN_POSITION_MM <= new_position <= MAX_POSITION_MM:
            raise ValueError("Mouvement out of limits.")

        self.current_steps = new_steps
        return steps

    def move_absolute(self, target_mm: float) -> int:
        """Simulate a target reading, returning signed pulses executed."""
        if not self.is_initialized:
            raise ValueError("Initialise the position.")

        if not MIN_POSITION_MM <= target_mm <= MAX_POSITION_MM:
            raise ValueError("Out-of-limits target position.")

        # Quantize the target relative to the initial reference to avoid
        # accumulating independent floating-point rounding errors.
        target_steps = round(
            (target_mm - self.initial_position) * STEPS_PER_MM
        )

        steps_to_move = target_steps - self.current_steps

        new_position = (
            self.initial_position + target_steps / STEPS_PER_MM
        )

        if not MIN_POSITION_MM <= new_position <= MAX_POSITION_MM:
            raise ValueError("Position out of limits.")

        self.current_steps = target_steps
        return steps_to_move
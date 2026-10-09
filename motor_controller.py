from motor_config import (
    STEPS_PER_MM,
    MIN_POSITION_MM,
    MAX_POSITION_MM,
)

class MotionController:
    def __init__(self):
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

    def initialize(self, position_mm):
        if not MIN_POSITION_MM <= position_mm <= MAX_POSITION_MM:
            raise ValueError("Initial position out of limits.")

        self.initial_position = position_mm
        self.current_steps = 0

    def move_relative(self, distance_mm):
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

    def move_absolute(self, target_mm):
        if not self.is_initialized:
            raise ValueError("Initialise the position.")

        if not MIN_POSITION_MM <= target_mm <= MAX_POSITION_MM:
            raise ValueError("Out-of-limits target position.")

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
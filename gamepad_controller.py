"""BEITONG gamepad adapter for discrete, safety-checked movement requests.

Axis indices are connection-mode/platform dependent. Verify mapping using
pygame in simulation mode before commanding the physical stage.
"""

import pygame
from PySide6.QtCore import QObject, QTimer, Signal


class GamepadController(QObject):
    """Emit direction/step requests without talking directly to Arduino.

    Sticks select a continuous FAST/SLOW mode. The GUI sends an HB watchdog
    heartbeat while moving; the firmware stops if heartbeats cease.
    """

    move_requested = Signal(int)  # Triggers: respect GUI increment selection.
    step_requested = Signal(float)  # Legacy discrete steps (kept for compatibility).
    jog_requested = Signal(str)  # FAST +, FAST -, SLOW +, SLOW -, or empty for neutral.
    stop_requested = Signal()
    status_changed = Signal(str)

    # Observed BEITONG mapping, with physical LT/RT corrected after testing.
    LT_AXIS = 4
    RT_AXIS = 5
    LEFT_X_AXIS = 0
    RIGHT_X_AXIS = 2
    STOP_BUTTON = 1

    DEADZONE = 0.18
    TRIGGER_PRESS_THRESHOLD = 0.50
    TRIGGER_RELEASE_THRESHOLD = -0.20

    def __init__(self, parent=None):
        super().__init__(parent)
        pygame.init()
        pygame.joystick.init()
        self.joystick = None
        self.trigger_pressed = {self.LT_AXIS: False, self.RT_AXIS: False}
        self._last_jog = ""
        self._stop_latched = True  # Require neutral before accepting movement.
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_gamepad)
        self.timer.start(50)

    def _reset_latches(self):
        self.trigger_pressed = {self.LT_AXIS: False, self.RT_AXIS: False}
        self._last_jog = ""
        self._stop_latched = False

    def connect_gamepad(self):
        """Detect the first joystick and reset its per-input press state."""
        pygame.event.pump()
        if pygame.joystick.get_count() == 0:
            self.status_changed.emit("Aucune manette détectée")
            return
        self.joystick = pygame.joystick.Joystick(0)
        self.joystick.init()
        self._reset_latches()
        self.status_changed.emit(f"Manette : {self.joystick.get_name()}")

    def process_trigger(self, axis: int, value: float):
        """Emit one request per trigger press using separate release threshold.

        Assumes triggers rest near -1 and move towards +1 when squeezed.
        """
        if axis not in self.trigger_pressed:
            return
        if value >= self.TRIGGER_PRESS_THRESHOLD and not self.trigger_pressed[axis]:
            self.trigger_pressed[axis] = True
            self.move_requested.emit(-1 if axis == self.LT_AXIS else 1)
        elif value <= self.TRIGGER_RELEASE_THRESHOLD:
            self.trigger_pressed[axis] = False

    def _jog_from_sticks(self) -> str:
        """Map horizontal stick deflection onto the firmware's presets.

        The right (fine) stick takes priority if both are moved. Returning an
        empty string requests a controlled stop. These are fixed-speed modes;
        the amount of deflection does not modulate velocity.
        """
        if self.joystick is None or not self.joystick.get_init():
            return ""
        axes = self.joystick.get_numaxes()
        for axis, prefix in ((self.RIGHT_X_AXIS, "SLOW"),
                             (self.LEFT_X_AXIS, "FAST")):
            if axis < axes:
                x = self.joystick.get_axis(axis)
                if abs(x) > self.DEADZONE:
                    return prefix + (" +" if x > 0 else " -")
        return ""

    def poll_gamepad(self):
        """Handle pygame input events without blocking the Qt UI thread."""
        for event in pygame.event.get():
            if event.type == pygame.JOYDEVICEREMOVED:
                if self.joystick is not None and event.instance_id == self.joystick.get_instance_id():
                    self.joystick = None
                    self._reset_latches()
                    self.status_changed.emit("Manette déconnectée")
                    # Best effort only: a software STOP is not an emergency cutoff.
                    self.jog_requested.emit("")
                    self.stop_requested.emit()
                continue
            if self.joystick is None or not self.joystick.get_init():
                continue
            if getattr(event, "instance_id", self.joystick.get_instance_id()) != self.joystick.get_instance_id():
                continue
            if event.type == pygame.JOYBUTTONDOWN and event.button == self.STOP_BUTTON:
                self._stop_latched = True
                self._last_jog = ""
                self.jog_requested.emit("")
                self.stop_requested.emit()
            elif event.type == pygame.JOYAXISMOTION:
                self.process_trigger(event.axis, event.value)


        if self.joystick is not None and self.joystick.get_init():
            command = self._jog_from_sticks()
            # After B/STOP, require sticks to return to neutral before arming.
            if self._stop_latched:
                if not command:
                    self._stop_latched = False
                return
            if command != self._last_jog:
                self._last_jog = command
                self.jog_requested.emit(command)

    def close(self):
        """Stop polling and release pygame resources."""
        self.timer.stop()
        self.jog_requested.emit("")
        pygame.quit()

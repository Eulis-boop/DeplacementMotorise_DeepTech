"""Optional BEITONG gamepad input, converted to incremental GUI requests.

The observed Xbox 360 mapping on macOS uses LT axis 5, RT axis 4 and
B button 1. Mappings and neutral trigger values can vary by connection
mode and operating system; verify them in simulation before real motion.
"""

import pygame
from PySide6.QtCore import QObject, QTimer, Signal


class GamepadController(QObject):
    """Emit movement/stop requests; never communicate directly with Arduino."""

    move_requested = Signal(int)  # -1 backwards, +1 forwards
    stop_requested = Signal()
    status_changed = Signal(str)

    LT_AXIS = 5
    RT_AXIS = 4
    STOP_BUTTON = 1
    PRESS_THRESHOLD = 0.5
    RELEASE_THRESHOLD = -0.2

    def __init__(self, parent=None):
        super().__init__(parent)
        pygame.init()
        pygame.joystick.init()
        self.joystick = None
        self.lt_pressed = False
        self.rt_pressed = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_gamepad)
        self.timer.start(50)

    def connect_gamepad(self):
        """Connect to the first detected gamepad; reset input latches."""
        pygame.event.pump()
        if pygame.joystick.get_count() == 0:
            self.status_changed.emit("Aucune manette détectée")
            return
        self.joystick = pygame.joystick.Joystick(0)
        self.joystick.init()
        self.lt_pressed = False
        self.rt_pressed = False
        self.status_changed.emit(f"Manette : {self.joystick.get_name()}")

    def process_trigger(self, axis: int, value: float):
        """Emit only one step per trigger press, using hysteresis.

        These thresholds assume an axis which rests near -1 and increases
        toward +1 when pressed. Recalibrate if the mapping is different.
        """
        if axis == self.LT_AXIS:
            if value >= self.PRESS_THRESHOLD and not self.lt_pressed:
                self.lt_pressed = True
                self.move_requested.emit(-1)
            elif value <= self.RELEASE_THRESHOLD:
                self.lt_pressed = False
        elif axis == self.RT_AXIS:
            if value >= self.PRESS_THRESHOLD and not self.rt_pressed:
                self.rt_pressed = True
                self.move_requested.emit(1)
            elif value <= self.RELEASE_THRESHOLD:
                self.rt_pressed = False

    def poll_gamepad(self):
        """Handle pending pygame events on the Qt event loop."""
        for event in pygame.event.get():
            if event.type == pygame.JOYDEVICEREMOVED:
                if self.joystick is not None and event.instance_id == self.joystick.get_instance_id():
                    self.joystick = None
                    self.lt_pressed = self.rt_pressed = False
                    self.status_changed.emit("Manette déconnectée")
                    # A software stop is best-effort, not a hardware fail-safe.
                    self.stop_requested.emit()
                continue

            if self.joystick is None or not self.joystick.get_init():
                continue
            if getattr(event, "instance_id", self.joystick.get_instance_id()) != self.joystick.get_instance_id():
                continue
            if event.type == pygame.JOYBUTTONDOWN and event.button == self.STOP_BUTTON:
                self.stop_requested.emit()
            elif event.type == pygame.JOYAXISMOTION:
                self.process_trigger(event.axis, event.value)

    def close(self):
        """Release pygame resources before quitting the Qt application."""
        self.timer.stop()
        pygame.quit()

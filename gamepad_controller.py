"""Optional incremental gamepad input. Commands always pass through the GUI checks."""
import pygame
from PySide6.QtCore import QObject, Signal, QTimer


class GamepadController(QObject):
    move_requested = Signal(int)
    stop_requested = Signal()
    status_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        pygame.init()
        pygame.joystick.init()
        self.joystick = None
        self.last_direction = 0
        self.last_stop = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_gamepad)
        self.timer.start(50)

    def connect_gamepad(self):
        pygame.event.pump()
        if pygame.joystick.get_count() == 0:
            self.status_changed.emit("Aucune manette détectée")
            return
        self.joystick = pygame.joystick.Joystick(0)
        self.joystick.init()
        self.last_direction = 0
        self.last_stop = False
        self.status_changed.emit(f"Manette : {self.joystick.get_name()}")

    def poll_gamepad(self):
        for event in pygame.event.get():
            if event.type == pygame.JOYDEVICEREMOVED and self.joystick is not None:
                self.joystick = None
                self.last_direction = 0
                self.status_changed.emit("Manette déconnectée")
                self.stop_requested.emit()
                return
        if self.joystick is None or not self.joystick.get_init():
            return
        # Typical first hat = horizontal D-pad. Not all controllers have hats.
        direction = self.joystick.get_hat(0)[0] if self.joystick.get_numhats() else 0
        if direction != 0 and self.last_direction == 0:
            self.move_requested.emit(direction)
        self.last_direction = direction
        # Button indices differ by controller: test mapping before using this as STOP.
        if self.joystick.get_numbuttons() > 1:
            pressed = bool(self.joystick.get_button(1))
            if pressed and not self.last_stop:
                self.stop_requested.emit()
            self.last_stop = pressed

    def close(self):
        self.timer.stop()
        pygame.quit()

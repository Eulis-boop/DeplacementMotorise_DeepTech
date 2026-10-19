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

            if event.type == pygame.JOYDEVICEREMOVED:
                self.joystick = None
                self.last_direction = 0
                self.status_changed.emit("Manette déconnectée")
                self.stop_requested.emit()
                return

            if self.joystick is None:
                continue

            if event.type == pygame.JOYBUTTONDOWN:

                # LB : Reculer
                if event.button == 9:
                    self.move_requested.emit(-1)

                # RB : Avancer
                elif event.button == 10:
                    self.move_requested.emit(1)

                # IMPORTANT :
                # Le bouton STOP reste géré
                # par le code existant.

    def close(self):
        self.timer.stop()
        pygame.quit()

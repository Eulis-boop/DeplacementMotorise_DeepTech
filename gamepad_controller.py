import pygame

from PySide6.QtCore import QObject, Signal, QTimer


class GamepadController(QObject):

    move_requested = Signal(int)
    stop_requested = Signal()
    status_changed = Signal(str)

    def __init__(self):
        super().__init__()

        pygame.init()
        pygame.joystick.init()

        self.joystick = None
        self.last_direction = 0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_gamepad)
        self.timer.start(50)

    def connect_gamepad(self):
        pygame.event.pump()

        if pygame.joystick.get_count() == 0:
            self.status_changed.emit(
                "Aucune manette détectée"
            )
            return

        self.joystick = pygame.joystick.Joystick(0)
        self.joystick.init()

        self.last_direction = 0

        self.status_changed.emit(
            f"Manette : {self.joystick.get_name()}"
        )

    def poll_gamepad(self):
        for event in pygame.event.get():
            if event.type == pygame.JOYDEVICEREMOVED:
                self.joystick = None
                self.last_direction = 0
                self.status_changed.emit(
                    "Manette déconnectée"
                )
                self.stop_requested.emit()
                return

        if self.joystick is None:
            return

        if not self.joystick.get_init():
            return

        if self.joystick.get_numhats() == 0:
            return

        direction = self.joystick.get_hat(0)[0]

        # Une seule commande lors de l'appui
        if direction != 0 and self.last_direction == 0:
            self.move_requested.emit(direction)

        self.last_direction = direction

    def close(self):
        self.timer.stop()
        pygame.quit()
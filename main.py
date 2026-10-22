"""PySide6 interface for simulated and Arduino-controlled stage positioning.

All displayed Arduino positions are step-based estimates rather than
independent sensor measurements. The GUI cannot serve as an emergency stop.
"""

import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QCheckBox,
    QLineEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from motor_config import MAX_POSITION_MM, MIN_POSITION_MM
from motor_controller import MotionController
from serial_manager import SerialManager
from arduino_protocol import parse_message
from gamepad_controller import GamepadController


STYLE = """
QWidget {
    color: #203047;
    font-family: 'Arial';
    font-size: 13px;
}
QWidget#page { background: #f5f7fb; }
QLabel { background: transparent; border: none; }
QFrame#header {
    background: #172b4d;
    border-radius: 16px;
}
QLabel#courseTitle { background: transparent; color: #bcd4ff; font-size: 13px; font-weight: 600; }
QLabel#projectTitle { background: transparent; color: #ffffff; font-size: 23px; font-weight: 700; }
QLabel#projectSubtitle { background: transparent; color: #d1e1ff; font-size: 12px; }
QLabel#modeBadge {
    color: #e2f0ff;
    background: #294b79;
    border-radius: 9px;
    padding: 5px 10px;
    font-weight: 600;
}
QFrame#card {
    background: white;
    border: 1px solid #e0e7f1;
    border-radius: 14px;
}
QLabel#sectionTitle { background: transparent; font-size: 15px; font-weight: 700; color: #1b2d49; }
QLabel#hint { background: transparent; color: #697a91; font-size: 12px; }
QLabel#positionValue { background: transparent; color: #1764ae; font-size: 35px; font-weight: 700; }
QLabel#statusLabel { background: transparent; font-weight: 600; color: #945b13; }
QLineEdit, QComboBox {
    background: #fff;
    color: #203047;
    border: 1px solid #cdd8e7;
    border-radius: 8px;
    padding: 8px 10px;
    min-height: 20px;
}
QLineEdit:focus, QComboBox:focus { border: 2px solid #3b82c4; }
QPushButton {
    background: #eaf1f9;
    border: 1px solid #cfdaea;
    border-radius: 8px;
    color: #234263;
    padding: 10px 14px;
    font-weight: 600;
    min-height: 18px;
}
QPushButton:hover { background: #d9e9f8; }
QPushButton:disabled { background: #edf0f4; color: #a5afbc; border-color: #e2e6ed; }
QPushButton#primary { background: #1764ae; color: white; border-color: #1764ae; }
QPushButton#primary:hover { background: #10518f; }
QPushButton#primary:disabled { background: #a8c3df; border-color: #a8c3df; }
QProgressBar {
    background: #e7edf5;
    border: none;
    border-radius: 5px;
    height: 10px;
    text-align: center;
}
QProgressBar::chunk { background: #2680c2; border-radius: 5px; }
QTextEdit {
    background: #f9fbfe;
    border: 1px solid #e0e7f1;
    border-radius: 8px;
    padding: 6px;
    color: #354b66;
    font-family: 'Menlo', 'Consolas', monospace;
    font-size: 11px;
}
QScrollArea { border: none; background: #f5f7fb; }
"""


def make_card(title: str):
    """Create a consistently styled control section."""
    card = QFrame()
    card.setObjectName("card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 17, 20, 18)
    layout.setSpacing(12)
    heading = QLabel(title)
    heading.setObjectName("sectionTitle")
    layout.addWidget(heading)
    return card, layout


class MainWindow(QMainWindow):
    """Coordinate GUI actions, simulator, USB protocol, and gamepad input."""
    def __init__(self):
        super().__init__()
        self.motor = MotionController()
        self.serial_manager = SerialManager(self)
        self.serial_manager.message_received.connect(self.on_serial_message)
        self.serial_manager.disconnected.connect(self.on_serial_disconnected)
        self.serial_manager.error_occurred.connect(self.on_serial_error)
        self.serial_manager.connected.connect(lambda: self.log.append("USB connecté. Attente du démarrage Arduino."))
        self.arduino_initialized = False
        self.arduino_position = None
        self.arduino_origin = None
        self.motion_busy = False
        self.pending = None
        self.gamepad = None
        self.desired_jog = ""
        self.active_jog = ""
        self.jog_stopping = False
        self.jog_timer = QTimer(self)
        self.jog_timer.setInterval(100)
        self.jog_timer.timeout.connect(self._send_jog_heartbeat)
        self.setWindowTitle("DeepTech | Déplacement motorisé")
        self.resize(750, 790)
        self.setMinimumSize(570, 590)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.setCentralWidget(scroll)
        page = QWidget()
        page.setObjectName("page")
        scroll.setWidget(page)
        body = QVBoxLayout(page)
        body.setContentsMargins(22, 22, 22, 22)
        body.setSpacing(16)

        header = QFrame()
        header.setObjectName("header")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 22, 24, 22)
        header_layout.setSpacing(5)
        course = QLabel("Développement des produits technologiques DeepTech")
        course.setObjectName("courseTitle")
        project = QLabel("Déplacement motorisé")
        project.setObjectName("projectTitle")
        subtitle = QLabel("Contrôle de la platine micrométrique · Axe X")
        subtitle.setObjectName("projectSubtitle")
        self.badge = QLabel("MODE SIMULATION")
        badge = self.badge
        badge.setObjectName("modeBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(course)
        header_layout.addWidget(project)
        header_layout.addWidget(subtitle)
        header_layout.addSpacing(8)
        header_layout.addWidget(badge, alignment=Qt.AlignmentFlag.AlignLeft)
        body.addWidget(header)

        # USB connection: no motion until checked and manually calibrated
        usb_card, usb_layout = make_card("00   Connexion et mode")
        usb_row = QHBoxLayout()
        self.mode_selector = QComboBox()
        self.mode_selector.addItems(["Simulation", "Arduino USB"])
        self.mode_selector.currentIndexChanged.connect(self.change_mode)
        usb_row.addWidget(self.mode_selector)
        self.port_selector = QComboBox()
        usb_row.addWidget(self.port_selector, 2)
        self.refresh_button = QPushButton("Actualiser")
        self.refresh_button.clicked.connect(self.refresh_ports)
        usb_row.addWidget(self.refresh_button)
        self.connection_button = QPushButton("Connecter")
        self.connection_button.clicked.connect(self.toggle_connection)
        usb_row.addWidget(self.connection_button)
        usb_layout.addLayout(usb_row)
        self.hardware_check = QCheckBox(
            "Configuration Arduino vérifiée (pitch 0,5 mm/tour, course sûre, micro-pas et sens)"
        )
        self.hardware_check.setChecked(False)
        self.hardware_check.stateChanged.connect(self.update_position)
        usb_layout.addWidget(self.hardware_check)
        self.usb_status = QLabel("Mode simulation. Aucun moteur réel commandé.")
        self.usb_status.setObjectName("hint")
        usb_layout.addWidget(self.usb_status)
        body.addWidget(usb_card)
        self.refresh_ports()

        # Initial position
        init_card, init_layout = make_card("01   Initialisation")
        note = QLabel("Saisissez la lecture initiale affichée sur le micromètre.")
        note.setObjectName("hint")
        init_layout.addWidget(note)
        init_row = QHBoxLayout()
        self.initial_input = QLineEdit()
        self.initial_input.setPlaceholderText("Ex. 5.00 mm")
        self.initial_input.setText("0.00")
        self.initial_input.setToolTip("Saisir manuellement la lecture du micromètre, en mm")
        self.init_button = QPushButton("Initialiser")
        self.init_button.setObjectName("primary")
        self.init_button.clicked.connect(self.initialize_motor)
        init_row.addWidget(self.initial_input, stretch=2)
        init_row.addWidget(self.init_button, stretch=1)
        init_layout.addLayout(init_row)
        self.status_label = QLabel("●  En attente d'initialisation")
        self.status_label.setObjectName("statusLabel")
        init_layout.addWidget(self.status_label)
        body.addWidget(init_card)

        # Position display
        position_card, position_layout = make_card("02   Position estimée")
        self.position_label = QLabel("— mm")
        self.position_label.setObjectName("positionValue")
        self.position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        position_layout.addWidget(self.position_label)
        self.displacement_label = QLabel("Déplacement depuis l'initialisation : —")
        self.displacement_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.displacement_label.setObjectName("hint")
        position_layout.addWidget(self.displacement_label)
        self.position_bar = QProgressBar()
        self.position_bar.setRange(0, 1000)
        self.position_bar.setTextVisible(False)
        position_layout.addWidget(self.position_bar)
        extent = QHBoxLayout()
        low = QLabel(f"{MIN_POSITION_MM:.1f} mm")
        high = QLabel(f"{MAX_POSITION_MM:.1f} mm")
        low.setObjectName("hint")
        high.setObjectName("hint")
        extent.addWidget(low)
        extent.addStretch()
        extent.addWidget(high)
        position_layout.addLayout(extent)
        body.addWidget(position_card)

        # Motion controls
        controls_grid = QGridLayout()
        controls_grid.setSpacing(16)

        relative_card, relative_layout = make_card("03   Déplacement relatif")
        relative_hint = QLabel("Choisissez un incrément, puis avancez ou reculez.")
        relative_hint.setObjectName("hint")
        relative_hint.setWordWrap(True)
        relative_layout.addWidget(relative_hint)
        self.step_selector = QComboBox()
        self.step_selector.addItems(["0.01", "0.10", "0.50", "1.00"])
        self.step_selector.setCurrentText("0.10")
        relative_layout.addWidget(self.step_selector)
        relative_buttons = QHBoxLayout()
        self.backward_button = QPushButton("← Reculer")
        self.forward_button = QPushButton("Avancer →")
        self.forward_button.setObjectName("primary")
        self.backward_button.clicked.connect(lambda: self.move_relative(-1))
        self.forward_button.clicked.connect(lambda: self.move_relative(1))
        relative_buttons.addWidget(self.backward_button)
        relative_buttons.addWidget(self.forward_button)
        relative_layout.addLayout(relative_buttons)
        controls_grid.addWidget(relative_card, 0, 0)

        absolute_card, absolute_layout = make_card("04   Déplacement absolu")
        absolute_hint = QLabel("Indiquez la position finale souhaitée en mm.")
        absolute_hint.setObjectName("hint")
        absolute_hint.setWordWrap(True)
        absolute_layout.addWidget(absolute_hint)
        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText("Ex. 7.88 mm")
        self.target_input.setText("0.00")
        self.target_input.setToolTip("Saisir manuellement la position cible en mm")
        absolute_layout.addWidget(self.target_input)
        self.move_button = QPushButton("Aller à la position →")
        self.move_button.setObjectName("primary")
        self.move_button.clicked.connect(self.move_absolute)
        absolute_layout.addWidget(self.move_button)
        controls_grid.addWidget(absolute_card, 0, 1)
        body.addLayout(controls_grid)

        safety_card, safety_layout = make_card("05   Arrêt et manette")
        safety_row = QHBoxLayout()
        self.stop_button = QPushButton("STOP — Décélérer et arrêter")
        self.stop_button.setStyleSheet("background:#fce8e8; color:#9c2431; border:1px solid #eab5b8;")
        self.stop_button.clicked.connect(self.stop_motion)
        safety_row.addWidget(self.stop_button)
        self.gamepad_button = QPushButton("Détecter la manette")
        self.gamepad_button.clicked.connect(self.connect_gamepad)
        safety_row.addWidget(self.gamepad_button)
        safety_layout.addLayout(safety_row)
        self.gamepad_status = QLabel("Manette inactive. LT/RT : pas relatifs ; stick G : FAST ; stick D : SLOW ; B : STOP.")
        self.gamepad_status.setObjectName("hint")
        self.gamepad_status.setWordWrap(True)
        safety_layout.addWidget(self.gamepad_status)
        body.addWidget(safety_card)

        log_card, log_layout = make_card("06   Journal des événements")
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(115)
        self.log.append("Simulation prête. Aucun Arduino connecté.")
        log_layout.addWidget(self.log)
        body.addWidget(log_card)

        footer = QLabel(
            "Prototype logiciel · La position est calculée à partir des pas simulés, "
            "pas mesurée par un capteur."
        )
        footer.setObjectName("hint")
        footer.setWordWrap(True)
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.addWidget(footer)
        self.update_position()

    def parse_position(self, field):
        """Parse comma/dot decimals, reject out-of-range or sub-0.01 mm inputs."""
        raw = field.text().strip().replace(",", ".")
        try:
            value = float(raw)
        except ValueError:
            raise ValueError("Veuillez saisir une position numérique en mm (ex. 7.88).")
        import math
        if not math.isfinite(value):
            raise ValueError("La position doit être un nombre fini.")
        if not MIN_POSITION_MM <= value <= MAX_POSITION_MM:
            raise ValueError(
                f"La position doit être comprise entre {MIN_POSITION_MM:.2f} "
                f"et {MAX_POSITION_MM:.2f} mm."
            )
        if abs(value * 100 - round(value * 100)) > 1e-7:
            raise ValueError("Saisissez la position au centième de millimètre (0.01 mm).")
        return round(value, 2)

    @property
    def real_mode(self):
        return self.mode_selector.currentIndex() == 1

    def refresh_ports(self):
        self.port_selector.clear()
        for name, desc in self.serial_manager.available_ports():
            self.port_selector.addItem(f"{name} — {desc}", name)

    def change_mode(self):
        # The mode selector is normally disabled during a pending command.
        if self.motion_busy or self.pending:
            self.mode_selector.blockSignals(True)
            self.mode_selector.setCurrentIndex(1 if self.serial_manager.is_connected else 0)
            self.mode_selector.blockSignals(False)
            return
        if self.serial_manager.is_connected:
            self.serial_manager.disconnect_port()
        self.clear_real_position("Changement de mode")
        self.hardware_check.setChecked(False)
        self.badge.setText("MODE ARDUINO" if self.real_mode else "MODE SIMULATION")
        self.update_position()

    def toggle_connection(self):
        if self.motion_busy or self.pending:
            QMessageBox.warning(self, "Mouvement actif", "Attendez l'arrêt avant de déconnecter.")
            return
        if self.serial_manager.is_connected:
            self.serial_manager.disconnect_port()
            return
        name = self.port_selector.currentData()
        if not name:
            QMessageBox.warning(self, "Port", "Aucun port série sélectionné.")
            return
        try:
            self.serial_manager.connect_port(name)
        except ConnectionError as error:
            QMessageBox.warning(self, "Connexion", str(error))
            return
        self.clear_real_position("Arduino connecté : initialisation requise")
        # USB opening generally resets Uno. Wait before requesting its position.
        QTimer.singleShot(2200, self.query_position)
        self.update_position()

    def clear_real_position(self, reason):
        self.arduino_initialized = False
        self.arduino_position = None
        self.arduino_origin = None
        self.motion_busy = False
        self.pending = None
        self.desired_jog = ""
        self.active_jog = ""
        self.jog_stopping = False
        self.jog_timer.stop()
        self.log.append(reason)

    def on_serial_disconnected(self):
        self.clear_real_position("USB déconnecté : position inconnue")
        self.update_position()

    def on_serial_error(self, reason):
        self.log.append("Erreur USB : " + reason)
        if self.motion_busy or self.pending:
            self.clear_real_position("Communication incertaine : vérifier physiquement le moteur et recalibrer")
        self.update_position()

    def query_position(self):
        if self.real_mode and self.serial_manager.is_connected and not self.pending:
            try:
                self.serial_manager.send_command("P")
            except ConnectionError as error:
                self.on_serial_error(str(error))

    def on_serial_message(self, line):
        """Synchronize motor state with the firmware's textual responses."""
        self.log.append("Arduino > " + line)
        kind, value = parse_message(line)
        if line == "Continuous motion stopped at software travel limit.":
            # Do not automatically restart into the same end stop.
            self.desired_jog = ""
            self.active_jog = ""
            self.jog_timer.stop()
            self.log.append("Software limit reached; return sticks to neutral.")
        if line == "Continuous jog watchdog timeout.":
            self.desired_jog = ""
            self.active_jog = ""
            self.jog_stopping = True
            self.jog_timer.stop()
            self.log.append("Watchdog: return sticks to neutral before restarting.")
        if kind == "restarted":
            self.clear_real_position("Arduino redémarré : calibrer avant déplacement")
        elif kind == "unknown":
            self.clear_real_position("Position inconnue : calibration requise")
        elif kind == "calibrated":
            if self.pending and self.pending[0] == "calibrate":
                self.arduino_initialized = True
                self.arduino_origin = self.pending[1]
                self.arduino_position = self.pending[1]
                self.pending = None
        elif kind == "moving":
            self.motion_busy = True
        elif kind == "stationary":
            prior = self.pending
            self.pending = None
            self.motion_busy = False
            self.active_jog = ""
            self.jog_stopping = False
            self.jog_timer.stop()
            if prior and prior[0] == "jog" and self.desired_jog:
                QTimer.singleShot(0, self._start_desired_jog)
        elif kind in ("completed", "stopped"):
            # Position and HOLDING follow completion of an actual movement.
            self.motion_busy = True
        elif kind == "position":
            if self.arduino_initialized:
                self.arduino_position = value
        elif kind == "idle":
            prior = self.pending
            self.pending = None
            self.motion_busy = False
            self.active_jog = ""
            self.jog_stopping = False
            self.jog_timer.stop()
            if prior and prior[0] == "jog" and self.desired_jog:
                QTimer.singleShot(0, self._start_desired_jog)
        elif kind == "error":
            self.pending = None
            self.motion_busy = False
            self.active_jog = ""
            self.desired_jog = ""
            self.jog_stopping = False
            self.jog_timer.stop()
            if "Calibrate" in value or "calibrat" in value.lower():
                self.arduino_initialized = False
                self.arduino_position = None
        self.update_position()

    def _issue_unconditional_stop(self, reason: str) -> None:
        """Send STOP even when the GUI incorrectly believes the motor is idle.

        Safety-critical requests must never be gated on cached UI state.
        The firmware remains the authority on whether motion is active.
        """
        self.jog_timer.stop()
        self.active_jog = ""
        self.jog_stopping = True
        if not (self.real_mode and self.serial_manager.is_connected):
            self.log.append("STOP impossible : Arduino USB déconnecté. Coupez l'alimentation moteur.")
            self.update_position()
            return
        try:
            self.serial_manager.send_command("STOP")
            self.log.append("PC > STOP (" + reason + ")")
            # Reconcile an uncertain GUI state with the actual controller.
            self.serial_manager.send_command("P")
        except ConnectionError as error:
            self.on_serial_error(str(error))
            self.log.append("STOP non confirmé : coupez l'alimentation moteur.")
            return
        self.motion_busy = True
        # Keep a pending marker until the firmware confirms stationary/holding.
        self.pending = ("jog_stop", None)
        self.update_position()

    def request_jog_command(self, command: str):
        """Start FAST/SLOW jogging, or ALWAYS ask Arduino to stop on neutral."""
        if command not in ("", "FAST +", "FAST -", "SLOW +", "SLOW -"):
            return
        if not self.real_mode:
            return
        previous = self.desired_jog
        self.desired_jog = command
        if not command:
            # Releasing a stick must not rely on self.pending/motion_busy.
            # Only send when the stick was previously requesting movement.
            if previous or self.active_jog or (self.pending and self.pending[0] == "jog"):
                self._issue_unconditional_stop("stick released")
            return
        if self.pending and self.pending[0] in ("jog", "jog_stop"):
            if command == self.active_jog and not self.jog_stopping:
                return
            if not self.jog_stopping:
                self._issue_unconditional_stop("change of direction or speed")
            return
        if self.motion_busy:
            return
        self._start_desired_jog()

    def _start_desired_jog(self):
        """Issue one FAST/SLOW command only after the stage becomes idle."""
        if not self.desired_jog or not self.is_ready_for_motion():
            return
        command = self.desired_jog
        self.jog_stopping = False
        if self.send_real(command, ("jog", command)):
            self.active_jog = command
            self.motion_busy = True
            self.jog_timer.start()
            self._send_jog_heartbeat()
            self.update_position()

    def _send_jog_heartbeat(self):
        """Refresh the firmware's independent FAST/SLOW watchdog at 10 Hz."""
        if not (self.real_mode and self.serial_manager.is_connected
                and self.pending and self.pending[0] == "jog"
                and self.active_jog and not self.jog_stopping):
            self.jog_timer.stop()
            return
        try:
            self.serial_manager.send_command("HB")
        except ConnectionError as error:
            self.jog_timer.stop()
            self.desired_jog = ""
            self.on_serial_error(str(error))

    def send_real(self, command, pending=None):
        try:
            self.serial_manager.send_command(command)
        except ConnectionError as error:
            self.on_serial_error(str(error))
            return False
        self.pending = pending
        self.log.append("PC > " + command)
        self.update_position()
        return True

    def initialize_motor(self):
        try:
            position = self.parse_position(self.initial_input)
        except ValueError as error:
            QMessageBox.warning(self, "Position invalide", str(error))
            return
        if self.real_mode:
            if not self.serial_manager.is_connected or not self.hardware_check.isChecked():
                QMessageBox.warning(self, "Sécurité", "Connectez Arduino et vérifiez sa configuration et les limites sûres.")
                return
            if self.pending or self.motion_busy:
                QMessageBox.warning(self, "Occupé", "Attendez la fin de la commande précédente.")
                return
            if self.arduino_initialized and QMessageBox.question(
                self, "Réinitialisation", "La lecture physique a-t-elle été vérifiée ? Remplacer la référence ?"
            ) != QMessageBox.StandardButton.Yes:
                return
            self.arduino_initialized = False
            self.send_real(f"C {position:.2f}", ("calibrate", position))
            return
        if self.motor.is_initialized and QMessageBox.question(
            self, "Réinitialisation", "Remplacer la position de référence actuelle ?"
        ) != QMessageBox.StandardButton.Yes:
            return
        self.motor.initialize(position)
        self.log.append(f"SIM > Initialisation : {position:.2f} mm")
        self.update_position()

    def move_relative(self, direction):
        """Request one signed increment from GUI buttons or the triggers."""
        distance = float(self.step_selector.currentText()) * direction
        self.request_relative_distance(distance)

    def request_relative_distance(self, distance):
        """Validate one signed displacement from buttons, triggers, or sticks."""
        if self.real_mode:
            if not self.is_ready_for_motion():
                return
            target = self.arduino_position + distance
            if not MIN_POSITION_MM <= target <= MAX_POSITION_MM:
                QMessageBox.warning(self, "Limites", "Mouvement hors de la plage configurée.")
                return
            self.send_real(f"M {distance:.2f}", ("move", target))
            return
        try:
            steps = self.motor.move_relative(distance)
        except ValueError as error:
            QMessageBox.warning(self, "Erreur", str(error))
            return
        self.log.append(f"SIM REL {distance:+.2f} mm | {steps:+d} impulsions")
        self.update_position()

    def move_absolute(self):
        try:
            target = self.parse_position(self.target_input)
        except ValueError as error:
            QMessageBox.warning(self, "Position invalide", str(error))
            return
        if self.real_mode:
            if not self.is_ready_for_motion():
                return
            self.send_real(f"G {target:.2f}", ("move", target))
            return
        try:
            steps = self.motor.move_absolute(target)
        except ValueError as error:
            QMessageBox.warning(self, "Erreur", str(error))
            return
        self.log.append(f"SIM ABS {target:.2f} mm | {steps:+d} impulsions")
        self.update_position()

    def is_ready_for_motion(self):
        if not (self.serial_manager.is_connected and self.hardware_check.isChecked()
                and self.arduino_initialized and self.arduino_position is not None
                and not self.motion_busy and not self.pending):
            self.log.append("Commande refusée : vérifier connexion, calibration et disponibilité.")
            return False
        return True

    def stop_motion(self):
        """STOP is always transmitted when USB is connected, even if GUI is idle."""
        self.desired_jog = ""
        self._issue_unconditional_stop("STOP button")

    def connect_gamepad(self):
        if self.gamepad is None:
            try:
                self.gamepad = GamepadController(self)
            except Exception as error:
                QMessageBox.warning(self, "Manette", str(error))
                return
            self.gamepad.move_requested.connect(self.move_relative)
            self.gamepad.step_requested.connect(self.request_relative_distance)
            self.gamepad.jog_requested.connect(self.request_jog_command)
            self.gamepad.stop_requested.connect(self.stop_motion)
            self.gamepad.status_changed.connect(self.gamepad_status.setText)
        self.gamepad.connect_gamepad()

    def update_position(self, *_):
        if self.real_mode:
            connected = self.serial_manager.is_connected
            ready = (connected and self.hardware_check.isChecked()
                     and self.arduino_initialized and self.arduino_position is not None)
            idle = ready and not self.motion_busy and not self.pending
            position = self.arduino_position if ready else None
            origin = self.arduino_origin
            self.port_selector.setEnabled(not connected)
            self.refresh_button.setEnabled(not connected)
            self.connection_button.setText("Déconnecter" if connected else "Connecter")
            self.usb_status.setText("USB connecté" if connected else "USB déconnecté")
            self.init_button.setEnabled(connected and self.hardware_check.isChecked()
                                        and not self.motion_busy and not self.pending)
            self.stop_button.setEnabled(connected)
        else:
            ready = self.motor.is_initialized
            idle = ready
            position = self.motor.current_position
            origin = self.motor.initial_position
            self.port_selector.setEnabled(False)
            self.refresh_button.setEnabled(False)
            self.connection_button.setEnabled(False)
            self.usb_status.setText("Simulation : aucun mouvement physique")
            self.init_button.setEnabled(True)
            self.stop_button.setEnabled(False)
        if self.real_mode:
            self.connection_button.setEnabled(True)
        self.mode_selector.setEnabled(not self.motion_busy and not self.pending)
        if self.real_mode:
            self.connection_button.setEnabled(not self.motion_busy and not self.pending)
        self.forward_button.setEnabled(idle)
        self.backward_button.setEnabled(idle)
        self.move_button.setEnabled(idle)
        if position is None:
            self.position_label.setText("— mm")
            self.displacement_label.setText("Déplacement depuis l'initialisation : —")
            self.position_bar.setValue(0)
        else:
            self.position_label.setText(f"{position:.4f} mm")
            self.displacement_label.setText(
                f"Déplacement depuis l'initialisation : {position-origin:+.4f} mm"
                if origin is not None else "Déplacement depuis l'initialisation : —"
            )
            fraction = (position - MIN_POSITION_MM) / (MAX_POSITION_MM - MIN_POSITION_MM)
            self.position_bar.setValue(max(0, min(1000, round(fraction * 1000))))
        label = ("●  Mouvement en cours" if self.motion_busy else
                 "●  Prêt à déplacer" if ready else "●  Initialisation requise")
        self.status_label.setText(label)
        self.status_label.setStyleSheet(
            "color: #18835e;" if ready and not self.motion_busy else "color: #945b13;"
        )

    def closeEvent(self, event):
        """Avoid closing during a known active motion and release resources."""
        if self.real_mode and self.serial_manager.is_connected and (self.motion_busy or self.pending):
            QMessageBox.warning(self, "Mouvement actif",
                                "Arrêtez le moteur et attendez sa confirmation avant de fermer.")
            event.ignore()
            return
        if self.gamepad is not None:
            self.gamepad.close()
        self.serial_manager.disconnect_port()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

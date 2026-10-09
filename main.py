import sys

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QDoubleSpinBox,
    QComboBox,
    QGroupBox,
    QTextEdit,
    QMessageBox,
)
from PySide6.QtCore import Qt

from motor_controller import MotionController
from motor_config import MIN_POSITION_MM, MAX_POSITION_MM

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.motor = MotionController()

        self.setWindowTitle("Déplacement Motorisé - DeepTech 2026")
        self.resize(550,620)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)

        title = QLabel("Contrôle de la platine micrométrique")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 20px; font-weight: bold;"
        )

        layout.addWidget(title)

        mode_label = QLabel("MODE SIMULATION")
        mode_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(mode_label)

        # Initialization
        init_group = QGroupBox("Initialisation")
        init_layout = QHBoxLayout()

        self.initial_input = QDoubleSpinBox()
        self.initial_input.setRange(MIN_POSITION_MM, MAX_POSITION_MM)
        self.initial_input.setDecimals(3)
        self.initial_input.setSuffix("mm")

        init_button = QPushButton("Initialiser")
        init_button.clicked.connect(self.initialize_motor)

        init_layout.addWidget(self.initial_input)
        init_layout.addWidget(init_button)

        init_group.setLayout(init_layout)
        layout.addWidget(init_group)

        # Current position
        position_group = QGroupBox("Position actuelle estimée")
        position_layout = QVBoxLayout()

        self.position_label = QLabel("-- mm")
        self.position_label.setAlignment(Qt.AlignCenter)

        self.position_label.setStyleSheet("font-size: 32px; font-weight: bold; color: #2878B5")

        position_layout.addWidget(self.position_label)

        position_group.setLayout(position_layout)
        layout.addWidget(position_group)

        # Relative movement
        relative_group = QGroupBox("Déplacement relatif")
        relative_layout = QVBoxLayout()

        self.step_selector = QComboBox()
        self.step_selector.addItems(
            ["0.010", "0.100", "0.500", "1.000"]
        )

        relative_layout.addWidget(QLabel("Incrément de déplacement (mm)"))

        relative_layout.addWidget(self.step_selector)
        movement_layout = QHBoxLayout()

        self.backward_button = QPushButton("Reculer")
        self.forward_button = QPushButton("Avancer")

        self.backward_button.clicked.connect(lambda: self.move_relative(-1))
        self.forward_button.clicked.connect(lambda: self.move_relative(1))

        movement_layout.addWidget(self.backward_button)
        movement_layout.addWidget(self.forward_button)

        relative_layout.addLayout(movement_layout)

        relative_group.setLayout(relative_layout)
        layout.addWidget(relative_group)

        # Absolute movement
        absolute_group = QGroupBox("Déplacement absolu")
        absolute_layout = QHBoxLayout()

        self.target_input = QDoubleSpinBox()
        self.target_input.setRange(MIN_POSITION_MM, MAX_POSITION_MM)
        self.target_input.setDecimals(3)
        self.target_input.setSingleStep(0.01)
        self.target_input.setSuffix(" mm")

        self.move_button = QPushButton("Aller à")
        self.move_button.clicked.connect(self.move_absolute)

        absolute_layout.addWidget(self.target_input)
        absolute_layout.addWidget(self.move_button)

        absolute_group.setLayout(absolute_layout)
        layout.addWidget(absolute_group)

        # Event journalism
        log_group = QGroupBox("Journal des événements")
        log_layout = QVBoxLayout()

        self.log = QTextEdit()
        self.log.setReadOnly(True)

        log_layout.addWidget(self.log)
        log_group.setLayout(log_layout)

        layout.addWidget(log_group)

        self.log.append("Simulation prête")

        self.update_position()

    def initialize_motor(self):
        position = self.initial_input.value()

        if self.motor.is_initialized:
            answer = QMessageBox.question(
                self,
                "Réinitialisation",
                "Remplacer la positon de référence ?"
            )
            if answer != QMessageBox.Yes:
                return

        self.motor.initialize(position)

        self.log.append(
            f"Initialization : {position:.3f} mm"
        )

        self.update_position()

    def move_relative(self, direction):
        distance = float(self.step_selector.currentText())
        distance *= direction

        try:
            steps = self.motor.move_relative(distance)

            self.log.append(
                f"Déplacement {distance:+.3f} mm "
                f"({steps:+d} impulsions)"
            )

        except ValueError as error:
            QMessageBox.warning(self, "Erreur", str(error))

        self.update_position()

    def move_absolute(self):
        target = self.target_input.value()

        try:
            steps = self.motor.move_absolute(target)

            self.log.append(
                f"Position cible : {target:.3f} mm "
                f"({steps:+d} impulsions)"
            )
        except ValueError as error:
            QMessageBox.warning(self, "Erreur", str(error))

        self.update_position()

    def update_position(self):
        ready = self.motor.is_initialized

        self.forward_button.setEnabled(ready)
        self.backward_button.setEnabled(ready)
        self.move_button.setEnabled(ready)

        if not ready:
            self.position_label.setText("-- mm")
        else:
            self.position_label.setText(
                f"{self.motor.current_position:.4f} mm"
            )

if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
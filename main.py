"""DeepTech — micrometric stage graphical interface (simulation)."""

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
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
    def __init__(self):
        super().__init__()
        self.motor = MotionController()
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
        badge = QLabel("MODE SIMULATION")
        badge.setObjectName("modeBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(course)
        header_layout.addWidget(project)
        header_layout.addWidget(subtitle)
        header_layout.addSpacing(8)
        header_layout.addWidget(badge, alignment=Qt.AlignmentFlag.AlignLeft)
        body.addWidget(header)

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

        log_card, log_layout = make_card("05   Journal des événements")
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
        """Accepte 7.88 ou 7,88 ; vérifie la plage et les centièmes."""
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

    def initialize_motor(self):
        try:
            position = self.parse_position(self.initial_input)
        except ValueError as error:
            QMessageBox.warning(self, "Position invalide", str(error))
            return
        if self.motor.is_initialized:
            choice = QMessageBox.question(
                self, "Réinitialisation", "Remplacer la position de référence actuelle?"
            )
            if choice != QMessageBox.StandardButton.Yes:
                return
        try:
            self.motor.initialize(position)
        except ValueError as error:
            QMessageBox.warning(self, "Erreur", str(error))
            return
        self.log.append(f"Initialisation : {position:.2f} mm")
        self.update_position()

    def move_relative(self, direction):
        distance = float(self.step_selector.currentText()) * direction
        try:
            steps = self.motor.move_relative(distance)
        except ValueError as error:
            QMessageBox.warning(self, "Erreur", str(error))
            return
        self.log.append(f"REL  {distance:+.2f} mm  |  {steps:+d} impulsions")
        self.update_position()

    def move_absolute(self):
        try:
            target = self.parse_position(self.target_input)
        except ValueError as error:
            QMessageBox.warning(self, "Position invalide", str(error))
            return
        try:
            steps = self.motor.move_absolute(target)
        except ValueError as error:
            QMessageBox.warning(self, "Erreur", str(error))
            return
        self.log.append(f"ABS  {target:.2f} mm  |  {steps:+d} impulsions")
        self.update_position()

    def update_position(self):
        ready = self.motor.is_initialized
        self.forward_button.setEnabled(ready)
        self.backward_button.setEnabled(ready)
        self.move_button.setEnabled(ready)
        if not ready:
            self.position_label.setText("— mm")
            self.displacement_label.setText("Déplacement depuis l'initialisation : —")
            self.status_label.setText("●  En attente d'initialisation")
            self.status_label.setStyleSheet("color: #945b13;")
            self.position_bar.setValue(0)
            return
        position = self.motor.current_position
        displacement = position - self.motor.initial_position
        self.position_label.setText(f"{position:.4f} mm")
        self.displacement_label.setText(
            f"Déplacement depuis l'initialisation : {displacement:+.4f} mm"
        )
        self.status_label.setText("●  Prêt à déplacer (simulation)")
        self.status_label.setStyleSheet("color: #18835e;")
        fraction = (position - MIN_POSITION_MM) / (MAX_POSITION_MM - MIN_POSITION_MM)
        self.position_bar.setValue(max(0, min(1000, round(fraction * 1000))))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

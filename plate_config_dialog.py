"""Modal editor for the seven mechanical parameters stored in Arduino EEPROM.

This dialog never speaks to the serial port directly. The main window performs
an acknowledgement-driven SETUP transaction to avoid racing the firmware.
"""

import math
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QVBoxLayout, QHBoxLayout, QLineEdit,
    QLabel, QPushButton, QCheckBox, QMessageBox,
)

FIELDS = (
    ("MIN_MM", "Lecture minimale (mm)", "0.000"),
    ("MAX_MM", "Lecture maximale (mm)", "25.000"),
    ("DIVISION_MM", "Graduation (mm)", "0.001"),
    ("PITCH_MM", "Avance par tour (mm/tr)", "0.500"),
    ("GEAR_RATIO", "Rapport moteur / vis", "1.000"),
    ("JOG_MM", "Pas de déplacement (mm)", "0.010"),
    ("REVERSE_DIRECTION", "Inverser le sens (0 ou 1)", "0"),
)


def validate_config(values):
    """Mirror the Arduino's constraints before starting an EEPROM update."""
    if len(values) != 7 or not all(math.isfinite(x) for x in values):
        raise ValueError("Les paramètres doivent être des nombres finis.")
    low, high, division, pitch, ratio, jog, reverse = values
    if not (-1000 < low < 1000 and low < high < 1000):
        raise ValueError("Plage de lecture invalide (minimum < maximum).")
    if not (0 < division <= 1):
        raise ValueError("La graduation doit être comprise entre 0 et 1 mm.")
    if not (0 < pitch <= 10):
        raise ValueError("L'avance doit être comprise entre 0 et 10 mm/tour.")
    if not (0.01 <= ratio <= 1000):
        raise ValueError("Le rapport moteur/vis doit être entre 0.01 et 1000.")
    if not (0 < jog <= high-low):
        raise ValueError("L'incrément doit rester inférieur à la course.")
    if reverse not in (0, 1):
        raise ValueError("La direction doit être 0 ou 1.")
    # Match the current Arduino default motor/driver microstepping assumption.
    if not (0 < (high-low)*200*8*ratio/pitch < 1_000_000_000):
        raise ValueError("Trop d'impulsions pour le compteur du moteur.")
    return values


class PlateConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuration de la platine")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        notice = QLabel(
            "Paramètres réels de la platine. Vérifiez la course, l'avance par "
            "tour et le rapport mécanique avant de sauvegarder. "
            "Un nouveau calibrage sera obligatoire."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        form = QFormLayout()
        self.inputs = {}
        for key, label, default in FIELDS:
            field = QLineEdit(default)
            self.inputs[key] = field
            form.addRow(label, field)
        layout.addLayout(form)
        self.confirm = QCheckBox("J'ai vérifié les caractéristiques physiques de la platine.")
        layout.addWidget(self.confirm)
        self.status = QLabel("Lire la configuration sauvegardée avant de modifier.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.read_button = QPushButton("Lire Arduino")
        self.save_button = QPushButton("Enregistrer dans Arduino")
        self.close_button = QPushButton("Fermer")
        row.addWidget(self.read_button)
        row.addWidget(self.save_button)
        row.addWidget(self.close_button)
        layout.addLayout(row)
        self.close_button.clicked.connect(self.reject)

    def populate(self, values):
        for key, _, _ in FIELDS:
            if key in values:
                self.inputs[key].setText(str(values[key]))
        self.status.setText("Configuration lue depuis l'EEPROM Arduino.")

    def values(self):
        try:
            vals = [float(self.inputs[k].text().strip().replace(",", ".")) for k, _, _ in FIELDS]
        except ValueError as error:
            raise ValueError("Saisissez sept valeurs numériques valides.") from error
        return validate_config(vals)

    def set_busy(self, busy):
        for field in self.inputs.values():
            field.setEnabled(not busy)
        self.save_button.setEnabled(not busy)
        self.read_button.setEnabled(not busy)
        self.close_button.setEnabled(not busy)
        self.status.setText("Écriture EEPROM en cours…" if busy else self.status.text())

    def reject(self):
        if self.save_button.isEnabled():
            super().reject()

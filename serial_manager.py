from PySide6.QtCore import QObject, Signal, QIODeviceBase
from PySide6.QtSerialPort import QSerialPort, QSerialPortInfo


class SerialManager(QObject):
    connected = Signal()
    disconnected = Signal()
    message_received = Signal(str)
    error_occurred = Signal(str)

    def __init__(self):
        super().__init__()

        self.serial = QSerialPort(self)
        self.serial.setBaudRate(115200)

        self.buffer = bytearray()

        self.serial.readyRead.connect(self.read_data)
        self.serial.errorOccurred.connect(self.handle_error)

    def available_ports(self):
        return [
            (port.portName(), port.description())
            for port in QSerialPortInfo.availablePorts()
        ]

    def connect_port(self, port_name):
        if self.serial.isOpen():
            self.serial.close()

        self.buffer.clear()
        self.serial.setPortName(port_name)

        if not self.serial.open(
            QIODeviceBase.OpenModeFlag.ReadWrite
        ):
            raise ConnectionError(
                self.serial.errorString()
            )

        self.connected.emit()

    def disconnect_port(self):
        if self.serial.isOpen():
            self.serial.close()
            self.disconnected.emit()

    def send_command(self, command):
        if not self.serial.isOpen():
            raise ConnectionError(
                "Arduino non connecté."
            )

        data = (command + "\n").encode("ascii")
        self.serial.write(data)

    def read_data(self):
        self.buffer.extend(
            bytes(self.serial.readAll())
        )

        while b"\n" in self.buffer:
            line, _, remaining = self.buffer.partition(b"\n")
            self.buffer = bytearray(remaining)

            message = line.decode(
                "utf-8", errors="replace"
            ).strip()

            if message:
                self.message_received.emit(message)

    def handle_error(self, error):
        if error == QSerialPort.SerialPortError.NoError:
            return

        self.error_occurred.emit(
            self.serial.errorString()
        )
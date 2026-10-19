"""Non-blocking USB serial transport for the existing Arduino firmware."""
from PySide6.QtCore import QObject, Signal, QIODeviceBase
from PySide6.QtSerialPort import QSerialPort, QSerialPortInfo


class SerialManager(QObject):
    connected = Signal()
    disconnected = Signal()
    message_received = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.serial = QSerialPort(self)
        self.serial.setBaudRate(115200)
        self.buffer = bytearray()
        self.serial.readyRead.connect(self.read_data)
        self.serial.errorOccurred.connect(self.handle_error)

    @property
    def is_connected(self):
        return self.serial.isOpen()

    @staticmethod
    def available_ports():
        return [(p.portName(), p.description()) for p in QSerialPortInfo.availablePorts()]

    def connect_port(self, port_name):
        if self.is_connected:
            self.disconnect_port()
        self.buffer.clear()
        self.serial.setPortName(port_name)
        if not self.serial.open(QIODeviceBase.OpenModeFlag.ReadWrite):
            raise ConnectionError(self.serial.errorString())
        self.connected.emit()

    def disconnect_port(self):
        was_open = self.is_connected
        if was_open:
            self.serial.close()
        self.buffer.clear()
        if was_open:
            self.disconnected.emit()

    def send_command(self, command):
        if not self.is_connected:
            raise ConnectionError("Arduino non connecté.")
        data = (command.rstrip("\r\n") + "\n").encode("ascii")
        if self.serial.write(data) < 0:
            raise ConnectionError(self.serial.errorString())

    def read_data(self):
        self.buffer.extend(bytes(self.serial.readAll()))
        if len(self.buffer) > 8192:
            self.buffer.clear()
            self.error_occurred.emit("Réponse série trop longue.")
            return
        while b"\n" in self.buffer:
            line, _, rest = self.buffer.partition(b"\n")
            self.buffer = bytearray(rest)
            msg = line.decode("utf-8", errors="replace").strip()
            if msg:
                self.message_received.emit(msg)

    def handle_error(self, error):
        if error in (QSerialPort.SerialPortError.NoError,
                     QSerialPort.SerialPortError.TimeoutError):
            return
        reason = self.serial.errorString()
        self.error_occurred.emit(reason)
        if error in (QSerialPort.SerialPortError.ResourceError,
                     QSerialPort.SerialPortError.DeviceNotFoundError,
                     QSerialPort.SerialPortError.PermissionError):
            self.disconnect_port()

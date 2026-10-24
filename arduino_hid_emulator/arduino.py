import serial
import serial.tools.list_ports
import time


class ArduinoConnection:
    """
    Класс для управления подключением к Arduino.
    """

    def __init__(self, baud_rate=9600, *, port=None, legacy=False):
        if not legacy or not port:
            raise ValueError("Legacy firmware requires legacy=True and an explicit port; use HidDevice for v1")
        self.port = port
        self.connection = serial.Serial(self.port, baud_rate, timeout=1, write_timeout=0.1)
        time.sleep(2)  # Даем время Arduino на перезапуск

    @staticmethod
    def _find_arduino_port():
        """
        Определяет порт Arduino.
        """
        ports = serial.tools.list_ports.comports()
        for port in ports:
            if "Arduino" in port.description or "CH340" in port.description:
                return port.device
        return None

    def send_command(self, command):
        """
        Отправляет команду на Arduino и возвращает результат выполнения.

        :param command: Команда для отправки.
        :return: True, если команда успешно выполнена, иначе False.
        """
        if not isinstance(command, str) or not command or len(command.encode('utf-8'))>127 or any(c in command for c in '\r\n\x00'):
            raise ValueError("Invalid legacy command")
        if not self.connection.is_open:
            raise RuntimeError("Подключение к Arduino не активно.")
        self.connection.write((command + "\n").encode())
        time.sleep(0.05)  # Небольшая задержка для обработки команды Arduino
        response = self.connection.readline().decode().strip()
        return response == "True"

    def close(self):
        """
        Закрывает соединение с Arduino.
        """
        if self.connection.is_open:
            self.connection.close()

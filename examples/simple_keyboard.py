from arduino_hid_emulator.arduino import ArduinoConnection
from arduino_hid_emulator.constants import KEY_LEFT_CTRL, KEY_LEFT_ALT, KEY_DELETE, KEY_F12
from arduino_hid_emulator.keyboard import KeyboardController

arduino = ArduinoConnection()
keyboard = KeyboardController(arduino)

keyboard.press_key("a")  # Нажимает клавишу "a"
keyboard.release_key("a")  # Отпускает клавишу "a"
keyboard.type_key("b")  # Нажимает и отпускает клавишу "b"
keyboard.type_key(KEY_F12)  # Нажимает и отпускает клавишу F12
keyboard.key_combo("alt+tab")  # Выполняет комбинацию
keyboard.key_combo(KEY_LEFT_CTRL+"+"+KEY_LEFT_ALT+"+"+KEY_DELETE)  # Выполняет комбинацию из констант
arduino.close()

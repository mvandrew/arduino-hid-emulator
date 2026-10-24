from unittest.mock import MagicMock
import pytest
pytest.importorskip('pyautogui')
from arduino_hid_emulator.mouse import MouseController


def test_calibrate():
    mock_arduino = MagicMock()
    mock_arduino.send_command.return_value = "True"
    mouse = MouseController(mock_arduino, default_factor_x=1/3, default_factor_y=1/3)

    # Имитация экрана
    screen_width = 1920
    screen_height = 1080

    # Убедимся, что коэффициенты по умолчанию
    assert mouse.factor_x == 1/3
    assert mouse.factor_y == 1/3

    # Здесь вы можете подменить вызовы pyautogui для симуляции работы, например:
    # with patch('pyautogui.position', return_value=(100, 100)):
    #     ...

    # После калибровки убедитесь, что коэффициенты изменились
    # (Требуется мокировать pyautogui и реализацию движения)

# Arduino HID Emulator

> Historical 0.4.0 README, retained for migration context. Its implicit-port
> examples are obsolete: current legacy connections require `port=..., legacy=True`
> and the old sketch. Use the current [README](../README.md) for supported commands.

`arduino-hid-emulator` is a Python library designed to control HID devices (keyboard and mouse) emulated using Arduino. The library allows you to send commands to control mouse movements, key presses, and mouse button actions, as well as perform calibration for precise positioning.

## Features

- **Mouse Control**:
  - Direct movement by specified offset.
  - Smooth mouse movement using a Bézier curve.
  - Press, release, and click mouse buttons.

- **Keyboard Control**:
  - Press and release keys.
  - Simulate key combinations (e.g., `Ctrl + C`).

- **Calibration**:
  - Automatic calibration of mouse movement factors for precise positioning.

- **Flexibility**:
  - Adjustable minimum and maximum duration for mouse movements.
  - Easy connection and control via serial port.

## Installation

Ensure Python 3.x is installed on your system, then install the library using `pip`:

```bash
pip install arduino-hid-emulator
```

## Requirements

- Arduino with HID support (e.g., Arduino Pro Micro or Leonardo).
- Upload the Arduino sketch (`hid_emulator.ino`) located in the `arduino/hid_emulator` directory.
- Python libraries:
  - `pyserial`
  - `pyautogui`

## Quick Start

1. **Connect Arduino**:
   Upload the `hid_emulator.ino` sketch to your Arduino board and connect it to your computer via USB.

2. **Create a connection object**:
   ```python
   from arduino_hid_emulator.arduino import ArduinoConnection
   from arduino_hid_emulator.mouse import MouseController

   arduino = ArduinoConnection()
   mouse = MouseController(arduino)
   ```

3. **Usage example**:
   ```python
   # Move the mouse to a specified point
   mouse.move_direct(100, 100)

   # Smoothly move the mouse to a specified point
   mouse.mouse_move(500, 500, duration_min=1000, duration_max=2000)

   # Click the left mouse button
   mouse.click("left")
   ```

4. **Close the connection**:
   ```python
   arduino.close()
   ```

## Calibration

For precise movement, it is recommended to perform calibration:
```python
mouse.calibrate()
```
Calibration is performed automatically, adjusting mouse movement factors.

## Project Structure

- `arduino_hid_emulator/` — source code of the library.
- `arduino/hid_emulator/` — sketch for uploading to Arduino.
- `examples/` — usage examples.

## License

The project is distributed under the [GPL-3.0](https://www.gnu.org/licenses/gpl-3.0.html) license. You are free to use, modify, and distribute the library under its terms.

## Contributing

If you want to suggest improvements, report issues, or contribute, create a pull request or open an issue in the [project repository](https://github.com/mvandrew/arduino-hid-emulator).

---
**Note**: Make sure the Arduino sketch is uploaded and the device supports HID.

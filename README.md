# Arduino HID Emulator 1.0.0

A bounded, explicit-port Python client and Leonardo firmware implementing HID v1.
The keyboard sends raw USB usage/modifier reports. Unicode text, OS layout
selection, file jobs, typing rhythm, and observation of a user's mouse belong to
the application, not this library.

## Install

Python >=3.10; validated on CPython 3.12.14 / Windows 11 Pro build 28000.
Install from the checked-out repository (a parent project may pin it as a submodule):

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -e .
```

Runtime dependency: pyserial 3.5. No PyAutoGUI or clipboard dependency for HID v1.
Do not install the unrelated PyPI distribution named `serial`.

## Firmware (Leonardo / ATmega32U4 only)

Validated toolchain: Arduino CLI 1.5.1, Arduino AVR Boards 1.8.8,
AVR GCC 7.3.0-atmel3.6.1-arduino7. HID is provided by that core; external
Keyboard/Mouse libraries are not required for the v1 image.

```powershell
arduino-cli core install arduino:avr@1.8.8
arduino-cli board list
arduino-cli compile --fqbn arduino:avr:leonardo --build-path build/leonardo arduino/hid_emulator
arduino-cli upload --fqbn arduino:avr:leonardo --port COM3 --input-dir build/leonardo arduino/hid_emulator
```

Select the actual connected board/port; COM3 is the validated Windows fixture.
Firmware upload changes that board. The normal image contains no fault-test
commands, no startup typing, and no automatic legacy fallback. A 1200-baud touch
enters the bootloader; the application watchdog deliberately stops being fed for
that transition. The USB serial string remains HIDFG to preserve the original
Windows COM association; it is not a globally unique physical device identifier.
Other boards/cores are not claimed supported by this direct AVR endpoint driver.

## API

```python
from arduino_hid_emulator import HidDevice, Outcome

with HidDevice("COM3", identity=(0x2341, 0x8036, "HIDFG")) as device:
    print(device.capabilities)  # handshake only: no keyboard input
    assert device.begin(1).completed
    # In a prepared target window with the correct OS keyboard layout:
    result = device.tap(1, 4, modifiers=2, hold_ms=10)  # raw A key + Left Shift
    if result.outcome is Outcome.UNKNOWN:
        raise RuntimeError("Inspect the target; never blindly retry this action")
    assert device.cancel(1).completed
```

`tap(generation, usage, modifiers=0, hold_ms=10)`, `down(generation, usage,
modifiers=0)`, `up(generation)`, `cancel(generation)`, `release()`, `close()`.
Use standard page 0x07 usages 4..115 (Enter 40, Backspace 42, Space 44), not
legacy Arduino Keyboard API numeric constants. A new generation must exceed the
session's previous BEGIN/CANCEL fence. CANCEL invalidates local dispatch before
waiting for transport, and can run while another thread awaits a TAP reply.
One HID action may be in flight; a second returns NOT_EXECUTED/BUSY.

Results distinguish COMPLETED, NOT_EXECUTED, UNKNOWN. Inspect `.outcome` or
`.completed`: implicit truth testing intentionally raises TypeError. ACCEPTED
is not completion; DONE means both TAP reports were committed to the device USB
endpoint, not that an editor's contents were verified.

A reader and automatic heartbeat run independently of caller pauses. All writes
are serialized without holding the writer while awaiting replies. Read/write
timeouts are 50/100ms; the operation deadline defaults to 1s, open including
lease-drain/handshake to 5s, close to at most 1s of protocol waiting. A stalled
OS port-open has one process-wide bounded waiter; abandoned opens are closed on
completion, not multiplied into unlimited workers. As with pyserial, injected
transports must honor I/O cancellation/timeouts.

Timeout, partial write, corrupt reply, conflicting result or disconnect fail the
session closed. No HID retransmission, automatic reconnect, legacy fallback, or
old-generation resume occurs. Create a new instance after inspecting the target.
Closing does not prove release reached a disconnected USB host; firmware also
has a 1000ms heartbeat lease, 100ms maximum DOWN hold, and AVR hardware WDT 2s.
Timer3 is reserved for a 1kHz independent hold guard: it releases a key within
100 ticks even when the main loop hangs, before the WDT disconnects USB.
See [wire protocol](docs/protocol-v1.md) and [validation](docs/validation-v1.md).

## Tests

```powershell
python -m pip install -e ".[test]" ziglang==0.14.1
python -m pytest -q
# Explicit real HID input in a dedicated test window (keep it active):
python tests/hardware_windows.py --port COM3 --output build/hardware.json
```

Native tests compile the same `Engine.h` as the sketch and inject USB endpoint
stalls, packet loss/duplication, cancellation and virtual time. Install Zig for
these tests; without it pytest reports those cases skipped, not hardware passed.
The hardware script uses only its own Tk window and a fixed sample, not user
files. It requires Tkinter and Windows and is never run by ordinary pytest.

## Legacy migration

This is a breaking major version: the new sketch rejects old textual key/mouse
commands. For old consumers only, the former sketch is preserved as
`arduino/legacy_hid_emulator/legacy_hid_emulator.ino`. Old keyboard/mouse classes
are explicitly legacy:

```python
from arduino_hid_emulator.arduino import ArduinoConnection
legacy = ArduinoConnection(port="COM3", legacy=True)
```

The legacy port must run the matching old sketch. Legacy calls retain their
True/False interface and do not provide the new protocol's cancellation/lease
or outcome guarantees. Read/write waits are now bounded. Legacy mouse examples
require `pip install -e ".[legacy-mouse]"`; the keyboard v1 client never imports
PyAutoGUI. Old examples under `examples/simple_*` are marked legacy; the safe
handshake-only v1 example is `python examples/hid_v1.py --port COM3` (a keyboard
press requires the explicit `--tap-a` flag). Mouse HID is not advertised by v1.

GPL-3.0; see LICENSE. No package publication is required to use a pinned checkout.

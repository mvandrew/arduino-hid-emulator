# HID v1 validation — 24 October 2026

## Addendum: staged chords, library / firmware 1.1.0

The current pair extends wire v1 with capability STAGED_CHORD (0x40), flags
0x7F. The baseline evidence below remains the 1.0.0 historical record.
89 automated tests pass, including native execution of the actual Engine.h:
four distinct reports/timings; cancellation and disconnect in every phase;
NOT_EXECUTED before the main key; malformed timing rejection; stale-loop
UNKNOWN/no late down; continuous 100ms interrupt guard across intermediate reports.
The Python client validates the feature before sending and does not fall back.

On Leonardo COM3 with AVR Boards 1.8.8 the normal image was compiled and uploaded:
flash 11786/28672 bytes, RAM 1432/2560 bytes. HEX SHA256:
`942BBB55F676C22C6E0C026AE4493733D04409342C98AE250A8420C16B02816C`.
Parent keyboard-service's owned-editor hardware fixture passed 15/15 checks:
Home 0x4A with modifier 0x02 selects the indentation; separate Shift/Home edges
were observed; cancellation at Shift-only / Home-held / Shift-tail released
both keys in 13.405 / 10.480 / 10.218ms with no modifier left down.
These are individual Windows observations, not hard real-time maxima.
The 1.1.0 interrupt guard was exercised natively; a fresh physical WDT injection
was not performed in this addendum. The test helper's post-WDT version check is
updated for the new pair. VS Code UI automation was rejected by access review;
owned Tk autoindent behavior is not reported as VS Code integration evidence.

Validated pair: Python API 1.0.0 / firmware 1.0.0 / wire 1, local checked-out
source in branch `codex/data-transfer-hid-v1`. Git commit identifies the exact
source; no PyPI release or remote push was performed as part of validation.

## Environment

- Windows 11 Pro x64 10.0.28000, CPython 3.12.14 x64.
- Arduino Leonardo-compatible ATmega32U4, COM3, VID 2341 / PID 8036,
  USB serial HIDFG. Physical reset exposed the bootloader on COM4.
- Arduino CLI 1.5.1, Arduino AVR core 1.8.8,
  AVR GCC 7.3.0-atmel3.6.1-arduino7.
- Native Engine tests: Zig 0.14.1; pyserial 3.5, pytest 9.1.1.
- Production build: **11052 / 28672 bytes flash, 1412 / 2560 bytes static RAM**.
  Warnings with `--warnings all`: unused core `new.cpp` parameters only.
- Installed production HEX SHA-256:
  `AAE2640D745E802CA08BD82CA092CE0A6BA1A17E976882E45CAACAD1B01D90A0`.

## Software checks

`python -m pytest -q`: **67 passed**, no skipped native Engine tests.

The client cases cover complete/accepted-only/lost/late replies, partial writes,
write disconnection, CRC corruption, wrong session/generation/completion code,
duplicate and conflicting terminal replies, concurrent cancel/TAP and
cancel/BEGIN, validation before write, heartbeat during caller idle, bounded
close, fresh nonce on reconnect and one bounded outstanding stalled OS open.

Native tests compile the actual AVR-independent `Engine.h` and `HoldGuard.h`:
raw reports, timer boundaries, cancel before/after down, no HID queue, generation
fences, idempotence/result eviction/conflicting IDs, heartbeat lease, USB loss,
stalled endpoints, failed release, TX backpressure, oversized/malformed/partial
frames and canonical argument validation. These tests do not simulate Windows
editor behavior and are not a replacement for the hardware checks below.

The wheel builds successfully. A separate clean venv installed only the v1
wheel and pyserial 3.5 from a local wheel directory; importing HidDevice succeeds
without PyAutoGUI installed. `pip check` passed in both environments. The parent
application continues using the editable submodule checkout, not that wheel.
`make test` / `manage_package.bat test` now run local pytest only, without
publishing packages or deleting build artifacts.

## Real production-image checks

`tests/hardware_windows.py --port COM3 --output <ignored build path>` passed.
Its own Tk Text window was the active US-layout target; fixed text only.

| Check | Result |
|---|---|
| HELLO/capabilities, BEGIN, CANCEL, RELEASE/CLOSE | Passed, correct wire v1 profile |
| Raw A with Shift, Space, Enter, Backspace, b | Full fixed reference matched |
| Replayed terminal TAP | No repeated character, correlated duplicate accepted |
| Bad CRC, oversized frame and legacy key_press | No extra input, subsequent session alive |
| DOWN without UP | Real key-up observed at **99.949 ms** after key-down |
| Cancel during a 100ms TAP | Terminal cancel ACK in **5.357 ms**, no further down |
| Old cancelled generation | Rejected locally; new BEGIN required |
| Long idle with automatic heartbeat | Session remained active beyond lease interval |
| DTR loss with Shift+F13 held | Shift release observed after **2.289 ms** |
| Heartbeat disabled / lease expired | Old-session TAP rejected BAD_SESSION, no character |
| Final own modifiers | No Shift/Ctrl/Alt/Win held |

Measurements are individual Windows observations, not worst-case statistical
guarantees. Key event latency includes the USB/Windows/Tk path; CRC test payloads
are fixed protocol fixtures, never user job contents.

## Real watchdog and re-enumeration

An explicitly built `-DHIDV1_FAULT_INJECTION` image was loaded. The dedicated
`tests/hardware_watchdog_windows.py` window held Shift+F13, then injected `!` to
freeze only the main loop while interrupts continued. This is not a production
wire command. All final checks passed:

- Timer3 released the test Shift before reset; first polling observation
  **0.1022 s after fault injection**, with 20ms polling granularity.
- USB disappeared and returned on COM3 after **2.4662 s**.
- The old client failed closed. A newly constructed client received a fresh
  session and required BEGIN; no old generation resumed.
- No test modifier remained held after reconnect.

The ordinary image was subsequently restored by normal CLI upload and the full
production hardware script passed again. Diagnostic fault injection is absent
from the image left installed on the device.

Final mode check sent the test-only `!` byte to production, waited 2.3s, and
confirmed that heartbeat, BEGIN/CANCEL and close still worked with no held
modifiers. Thus the installed image did not contain the diagnostic loop freeze.

Two failures found and fixed during development are relevant to regression:
feeding the application WDT originally defeated CDC 1200-baud bootloader touch;
physical RST-to-GND recovered the first image, and software uploads have since
passed repeatedly. Separately, Windows retained Shift when reset happened before
release; the independent Timer3 guard fixes the tested interrupt-enabled loop
hang. A pure zero report after re-enumeration alone did not fix that case.

## Limits / follow-up integration

Physical cable removal, host sleep/secure desktop, interrupt-disabled MCU hangs,
alternative core/board/clock and editor/OS keyboard layouts are not accepted by
this report. A disconnected USB host cannot receive key-up; do not claim a
universal Windows-global key-state guarantee for those conditions. The MCU
clears/disarms its own state and never replays old input.

Russian Unicode mapping/OS layout coordination, file jobs, user mouse pauses,
rhythm/corrections and full Windows application integration are later parent
tasks (DT-006/009/010/013), not capabilities of this library or firmware.

Raw generated JSON, binary builds, venvs and machine paths remain under ignored
`keyboard-service/build/` on the validation host; this report, scripts, protocol
fixtures and source are the versioned evidence.

## DT-009 integration repair — 2026-10-24

The parent application's real Windows serial-close test exposed a pyserial
overlapped-I/O race: a concurrent handle close can raise TypeError rather than
SerialException. Reader/writer transport exceptions now fault the session and
resolve possibly delivered commands as UNKNOWN; no retry or healthy orphaned
reader is allowed. Close attempts both I/O cancellations and joins the workers
even if the driver reports an exception. Regression tests cover read/write and
cancel/close failures. The complete suite passes **71 tests**, including native
Engine tests with Zig 0.14.1, with no skips. API/wire/firmware remain 1.0.0/v1;
the unpublished implementation is identified by its new Git commit. The
parent's DT-009 report records the repeated physical pipeline validation.

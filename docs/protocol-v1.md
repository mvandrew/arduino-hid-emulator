# HID v1 (library / firmware 1.1.0)

This standalone contract is implemented by `device.py`, `protocol.py` and
`arduino/hid_emulator/Engine.h`. There is no text/Unicode/mouse command in v1.
The legacy sketch and API are separate and never selected automatically.

## Frames

115200 baud, 8N1, DTR true. ASCII, single spaces, no CR/NUL, maximum 128 bytes
including LF. Canonical unsigned decimal integers (no leading zero except 0).

```text
Q1 <session> <id> <generation> <verb> [args] *<crc>\n
R1 <session> <id> <generation> <status> <code> [data] *<crc>\n
```

`\n` denotes LF. CRC-16/CCITT-FALSE, poly 0x1021, init 0xFFFF, no reflection or
final xor; four uppercase hex digits. Coverage is the ASCII body before the
space preceding `*`. `123456789` gives 29B1. CRC is integrity checking, not
authentication. Golden full-frame examples: `tests/fixtures/hid-v1-vectors.json`.

Session is a fresh nonzero 64-bit host nonce encoded as 16 uppercase hex digits.
ID is 1..4294967295 and strictly increases in physical write order, including
heartbeats/control commands. Generation is 0 for global control or a positive
uint32 for HID generations. Counters never wrap. Firmware caches the last four
terminal results and the current operation with a request fingerprint; repeated
IDs never execute a second action. A conflicting ID closes the session. Evicted
old IDs are rejected STALE_ID. The host never retries a potentially sent action.

## Commands

| Command | Generation / args | Behavior |
|---|---|---|
| HELLO | 0 / `1` | Fresh disarmed session after old lease ended/close |
| HB | 0 | Renew session lease; no HID |
| BEGIN | new positive | Arm a generation above every BEGIN/CANCEL fence |
| TAP | active / usage mask hold_ms | One down report, then zero report; hold 1..100ms |
| CHORD | active / usage mask lead_ms hold_ms tail_ms | Modifier-only, modifier+key, modifier-only, zero; positive phases, total <=90ms |
| DOWN | active / usage mask | One down report, automatic zero after at most 100ms |
| UP | active | Zero report |
| CANCEL | positive | Invalidate all generations <= value, release their keys |
| RELEASE | 0 | Release/disarm current generation |
| CLOSE | 0 | Release, respond, close session |

Raw usages are page 0x07 values 4..115; mask 0..255 encodes modifier usages E0..E7
as bits 0..7. Enter=40, Backspace=42, Space=44. There is one basic key with any
modifier mask in a report, no queued HID operations. A simultaneous action is
rejected BUSY. Unsupported usages, reserved/error values, invalid argument count
and noncanonical/overflowed numbers are rejected before any down.

HELLO returns `DONE READY 1 1.1.0 0000007F 128 0 1000 100`: wire major,
firmware semver, caps, maximum frame, pending HID depth, lease and max hold.
Caps bits 0..5 are RAW_TAP, BOUNDED_DOWN_UP, CANCEL_FENCE, RELEASE, HEARTBEAT,
CRC16. The client validates the entire bounded profile before permitting input.
Bit 6 (0x40) adds STAGED_CHORD. Old 0x3F firmware remains usable for old primitives;
`chord()` checks the bit before sending. CHORD requires a nonzero modifier mask.
There is still one HID operation in flight and zero queued operations.

All chord phases are processed by the nonblocking engine; control/HB remain
available. CANCEL/RELEASE/UP release both key and modifier without later chord
reports. If the main key never went down, termination is REJECTED /
CANCELLED_BEFORE_DOWN (only the modifier was pressed and then released). If it
already went down, release completes the action with DONE / OK. A late/stalled
chord at 100ms ends UNKNOWN / IO_UNCERTAIN and disarms the session, without
reasserting a modifier after the safety guard. Intermediate reports do not reset
the interrupt-level countdown: continuous nonzero state stays bounded by 100ms.

## Results and failure

ACCEPTED/OK acknowledges acceptance, not completion. DONE confirms completion;
codes: READY for HELLO, ALIVE for HB, CANCELLED for CANCEL, RELEASED for RELEASE,
OK otherwise. TAP DONE requires both reports committed to the raw USB endpoint.
No acknowledgement proves editor contents or exactly-once delivery in an app.

REJECTED is pre-execution refusal: BAD_ARGUMENT, BUSY, STALE_GENERATION,
BAD_SESSION, UNSUPPORTED_VERSION, UNSUPPORTED_USAGE, STALE_ID, SESSION_CONFLICT,
CANCELLED_BEFORE_DOWN or UNKNOWN_COMMAND. UNKNOWN/IO_UNCERTAIN is a possible
partial execution. Host Outcome values are COMPLETED / NOT_EXECUTED / UNKNOWN.
A failed/partial write, timeout after a possible send, bad reply, reset or
disconnect never becomes NOT_EXECUTED just because no ACK was received.

The reader checks CRC, session/id/generation, permitted status/code/data and
duplicate consistency. A duplicate terminal/late ACCEPTED does not move the
result backwards; conflicting terminal replies stop the session. Uncertain
results never turn into success on a late reply. No automatic reconnect/resume.

CANCEL is processed while TAP is active. Before down it rejects that action;
after down it may only complete its up/zero report, then returns the action's
terminal result before CANCEL's terminal result. Resume requires a new greater
generation, while application text position belongs to the application. An old
CANCEL must not release a newer generation. RELEASE/CLOSE never create a down.

## Bounds and implementation

Host read/write timeouts: 50/100ms. Operation including response: at most 1s;
open/lease-drain/handshake: 5s; close protocol waiting: 1s. The one writer path
serializes frames, but no response wait holds its lock. Reader and 100ms
heartbeat are separate threads. At most four pending requests, one HID action;
there is no background text queue. Caller pauses do not stop heartbeat.

Firmware parser uses a 128-byte static buffer and 100ms partial-frame deadline;
overflow/non-ASCII frames discard through the next LF. Input and serial output
have per-loop work limits. Reply backpressure fails/disarms instead of blocking.
Raw HID writes an entire 8-byte report only if the AVR endpoint has room. It
does not call the core's potentially 250ms-blocking USB_Send. Endpoint failure or
20ms lack of report space makes the action uncertain and closes the session;
zero reports continue being attempted. No down can occur after invalidation.

Only HB renews the 1000ms lease. Lease expiry, DTR loss, suspend/disconnect and
reset disarm and clear old operations. The firmware also limits DOWN to 100ms
and has an independent AVR WDT 2s. The Leonardo 1200-baud/DTR-low reset path
stops feeding the WDT so normal uploads remain possible. At reset a zero report
must be sent before HELLO is accepted. No key-up can physically reach a USB host
while the device is absent; re-enumeration/startup must not replay old keys.

Timer3 is reserved at 1kHz (16MHz / 64 / 250). Its interrupt-level HoldGuard
requests a zero report within 100 ticks of every nonzero report, independently
of the main loop, and retries if the endpoint is busy. This is necessary because
Windows can retain a modifier across USB reset: clearing only MCU RAM/starting
with zero is insufficient. The 2s WDT is the fallback after this early release.
An interrupt-disabled hang or physical cable removal can still prevent delivery
of key-up; those cases cannot provide a host-key-state guarantee.

The raw endpoint driver is pinned to ATmega32U4 and Arduino AVR core 1.8.8.
Unsupported chips fail compilation; broad board/core support is not implied.

## Hardware fault test image

`HIDV1_FAULT_INJECTION` is a diagnostic compiler define only. In that build an
out-of-band `!` byte freezes the main loop to test the hardware WDT; it is not
a v1 command/capability and is absent from a normal build. Never leave that image
installed for use. `tests/hardware_watchdog_windows.py` requires this image and
an isolated own window; restore/recheck the production image afterward.

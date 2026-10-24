"""HID v1 wire format. No Unicode text or legacy Arduino keycodes on this wire."""
import binascii
import re
from dataclasses import dataclass
from enum import Enum

MAX_FRAME = 128
UINT32_MAX = 0xFFFFFFFF
VERBS = {"HELLO", "HB", "BEGIN", "TAP", "DOWN", "UP", "CANCEL", "RELEASE", "CLOSE", "CHORD"}
STATUSES = {"ACCEPTED", "DONE", "REJECTED", "UNKNOWN"}


class ProtocolError(ValueError):
    pass


class Outcome(Enum):
    COMPLETED = "completed"
    NOT_EXECUTED = "not_executed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Result:
    outcome: Outcome
    code: str
    session: str
    command_id: int
    generation: int

    @property
    def completed(self):
        return self.outcome is Outcome.COMPLETED

    def __bool__(self):
        raise TypeError("Inspect result.outcome or result.completed explicitly")


@dataclass(frozen=True)
class Frame:
    kind: str
    session: str
    command_id: int
    generation: int
    fields: tuple


def uint32(value, *, positive=False):
    if type(value) is not int or not (int(positive) <= value <= UINT32_MAX):
        raise ProtocolError("Unsigned 32-bit value outside range")
    return value


def encode(body):
    if not isinstance(body, str) or not re.fullmatch(r"[A-Za-z0-9_.]+(?: [A-Za-z0-9_.]+)*", body):
        raise ProtocolError("Noncanonical frame body")
    data = body.encode("ascii")
    frame = data + f" *{binascii.crc_hqx(data, 0xFFFF):04X}\n".encode("ascii")
    if len(frame) > MAX_FRAME:
        raise ProtocolError("Frame too long")
    return frame


def decode(data, kind):
    if not isinstance(data, bytes) or len(data) > MAX_FRAME or not data.endswith(b"\n"):
        raise ProtocolError("Incomplete or oversized frame")
    try:
        body, crc = data[:-1].decode("ascii").rsplit(" *", 1)
    except (UnicodeError, ValueError) as exc:
        raise ProtocolError("Invalid frame encoding") from exc
    if not re.fullmatch(r"[0-9A-F]{4}", crc) or encode(body) != data:
        raise ProtocolError("CRC mismatch or noncanonical body")
    fields = body.split(" ")
    if len(fields) < (6 if kind == "R1" else 5) or fields[0] != kind:
        raise ProtocolError("Invalid frame version or header")
    if not re.fullmatch(r"[0-9A-F]{16}", fields[1]) or int(fields[1], 16) == 0:
        raise ProtocolError("Invalid session")
    for index in (2, 3):
        if not re.fullmatch(r"0|[1-9][0-9]{0,9}", fields[index]):
            raise ProtocolError("Noncanonical integer")
    command_id = uint32(int(fields[2]), positive=True)
    generation = uint32(int(fields[3]))
    if fields[4] not in (STATUSES if kind == "R1" else VERBS):
        raise ProtocolError("Unknown verb or status")
    return Frame(kind, fields[1], command_id, generation, tuple(fields[4:]))


def request(session, command_id, generation, verb, *args):
    if verb not in VERBS:
        raise ProtocolError("Unknown command")
    uint32(command_id, positive=True)
    uint32(generation)
    body = " ".join(map(str, ("Q1", session, command_id, generation, verb, *args)))
    result = encode(body)
    decode(result, "Q1")
    return result


@dataclass(frozen=True)
class Capabilities:
    protocol: int
    firmware: str
    flags: int
    max_frame: int
    pending_hid: int
    lease_ms: int
    max_hold_ms: int

    @classmethod
    def parse(cls, fields):
        if len(fields) != 7 or fields[0] != "1" or not re.fullmatch(r"1\.[0-9]+\.[0-9]+", fields[1]):
            raise ProtocolError("Incompatible firmware/protocol")
        if not re.fullmatch(r"[0-9A-F]{8}", fields[2]):
            raise ProtocolError("Invalid capability mask")
        if tuple(fields[3:]) != ("128", "0", "1000", "100") or int(fields[2], 16) & 0x3F != 0x3F:
            raise ProtocolError("Required bounded HID profile unavailable")
        return cls(1, fields[1], int(fields[2], 16), 128, 0, 1000, 100)

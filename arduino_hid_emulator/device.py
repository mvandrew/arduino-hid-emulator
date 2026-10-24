"""Explicit-port, bounded HID v1 client. All uncertain writes fail closed."""
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

import serial
from serial.tools import list_ports

from .protocol import (Capabilities, MAX_FRAME, Outcome, ProtocolError, Result,
                       decode, request, uint32)


class ConnectionError(RuntimeError):
    """Connection failed without issuing any HID operation."""


@dataclass
class _Pending:
    verb: str
    generation: int
    event: threading.Event = field(default_factory=threading.Event)
    result: object = None
    terminal: object = None
    sent: bool = False
    capabilities: object = None


class HidDevice:
    """One serial writer lock, independent reader and heartbeat; no HID queue.

    Construct a new instance to reconnect. No replay or automatic legacy fallback.
    serial_factory is injectable for fault tests and must obey pyserial timeouts.
    """
    _opening = threading.Semaphore(1)

    def __init__(self, port, *, identity=None, command_timeout=1.0,
                 open_timeout=5.0, serial_factory=serial.Serial, heartbeat=True):
        if not isinstance(port, str) or not port.strip():
            raise ValueError("An explicit port is required")
        if not 0.05 <= command_timeout <= 1.0 or not 1.2 <= open_timeout <= 5.0:
            raise ValueError("Timeout outside bounded profile")
        if identity is not None:
            matches = [p for p in list_ports.comports() if p.device == port]
            if len(matches) != 1 or (matches[0].vid, matches[0].pid, matches[0].serial_number) != identity:
                raise ConnectionError("Selected port does not match device identity")
        self.port = port
        self.session = f"{secrets.randbelow(0xFFFFFFFFFFFFFFFF) + 1:016X}"
        self.command_timeout = command_timeout
        self._state = threading.RLock()
        self._writer = threading.Lock()
        self._hid = threading.Lock()
        self._pending = {}
        self._history = OrderedDict()
        self._next_id = 1
        self._generation = 0
        self._fence = 0
        self._epoch = 0
        self._healthy = True
        self._closing = False
        self._closed = False
        self._stop = threading.Event()
        self._heartbeat_stop = threading.Event()
        self.capabilities = None
        deadline = time.monotonic() + open_timeout
        # A driver open can stall outside pyserial's read/write timeouts. One
        # outstanding opener process-wide; never spawn unlimited abandoned opens.
        if not self._opening.acquire(blocking=False):
            raise ConnectionError("Previous serial open is still outstanding")
        opened = threading.Event()
        abandoned = threading.Event()
        holder = {}

        def open_port():
            try:
                transport = serial_factory(port=port, baudrate=115200, timeout=0.05, write_timeout=0.1)
                holder['transport'] = transport
            except Exception as exc:
                holder['error'] = type(exc).__name__
            finally:
                opened.set()
                try:
                    if abandoned.is_set() and 'transport' in holder:
                        holder['transport'].close()
                finally:
                    self._opening.release()

        threading.Thread(target=open_port, name="hid-open", daemon=True).start()
        if not opened.wait(max(0, deadline - time.monotonic())):
            abandoned.set()
            # Cover completion racing the timeout flag.
            if opened.is_set() and 'transport' in holder:
                holder['transport'].close()
            raise ConnectionError("Serial open deadline exceeded")
        if 'error' in holder:
            raise ConnectionError("Serial open failed: " + holder['error'])
        self._serial = holder['transport']
        self._reader_thread = None
        self._heartbeat_thread = None
        try:
            # Existing lease is 1000ms. Drain only at a new session boundary,
            # never flush away replies while an operation is in progress.
            time.sleep(min(1.1, max(0, deadline - time.monotonic())))
            self._serial.reset_output_buffer()
            self._serial.reset_input_buffer()
            self._reader_thread = threading.Thread(target=self._read_loop, name="hid-reader", daemon=True)
            self._reader_thread.start()
            hello = self._request('HELLO', 0, 1, timeout=min(command_timeout, max(0, deadline-time.monotonic())))
            if not hello.completed or self.capabilities is None:
                raise ConnectionError("HID v1 handshake failed: " + hello.code)
            if heartbeat:
                self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, name="hid-heartbeat", daemon=True)
                self._heartbeat_thread.start()
        except Exception:
            self.close(timeout=max(0, min(1, deadline-time.monotonic())))
            raise

    @property
    def healthy(self):
        with self._state:
            return self._healthy and not self._closing and not self._closed

    def _result(self, outcome, code, command_id, generation):
        return Result(outcome, code, self.session, command_id, generation)

    def _fault(self, code):
        with self._state:
            self._healthy = False
            self._generation = 0
            self._heartbeat_stop.set()
            for command_id, pending in self._pending.items():
                if pending.result is None:
                    pending.result = self._result(Outcome.UNKNOWN if pending.sent else Outcome.NOT_EXECUTED,
                                                  code, command_id, pending.generation)
                    pending.event.set()

    def _request(self, verb, generation, *args, timeout=None):
        timeout = self.command_timeout if timeout is None else timeout
        deadline = time.monotonic() + timeout
        if timeout <= 0:
            return self._result(Outcome.NOT_EXECUTED, 'DEADLINE_EXCEEDED', 0, generation)
        if not self._writer.acquire(timeout=max(0, min(0.1, timeout))):
            return self._result(Outcome.NOT_EXECUTED, 'WRITER_BUSY', 0, generation)
        pending = None
        command_id = 0
        try:
            with self._state:
                if self._closed or (self._closing and verb != 'CLOSE'):
                    return self._result(Outcome.NOT_EXECUTED, 'CLOSED', 0, generation)
                if not self._healthy and verb not in ('RELEASE', 'CANCEL', 'CLOSE'):
                    return self._result(Outcome.NOT_EXECUTED, 'SESSION_UNCERTAIN', 0, generation)
                if len(self._pending) >= 4:
                    return self._result(Outcome.NOT_EXECUTED, 'BUSY', 0, generation)
                if verb in ('TAP', 'DOWN', 'UP') and (generation != self._generation or not generation):
                    return self._result(Outcome.NOT_EXECUTED, 'STALE_GENERATION', 0, generation)
                if self._next_id > 0xFFFFFFFF:
                    self._fault('ID_EXHAUSTED')
                    return self._result(Outcome.NOT_EXECUTED, 'ID_EXHAUSTED', 0, generation)
                command_id = self._next_id
                frame = request(self.session, command_id, generation, verb, *args)
                self._next_id += 1
                pending = _Pending(verb, generation)
                self._pending[command_id] = pending
                # Conservative: a write exception may follow partial OS delivery.
                pending.sent = True
            try:
                count = self._serial.write(frame)
                if count != len(frame):
                    self._fault('PARTIAL_WRITE')
            except (OSError, serial.SerialException):
                self._fault('WRITE_FAILED')
        finally:
            self._writer.release()
        if not pending.event.wait(max(0, deadline - time.monotonic())):
            self._fault('RESPONSE_TIMEOUT')
        with self._state:
            self._pending.pop(command_id, None)
            if pending.terminal is not None:
                self._history[command_id] = (pending.generation, pending.terminal)
                while len(self._history) > 16:
                    self._history.popitem(last=False)
            return pending.result

    def _read_loop(self):
        buffer = bytearray()
        started = None
        try:
            while not self._stop.is_set():
                chunk = self._serial.read(1)
                if not chunk:
                    if started is not None and time.monotonic() - started > 0.1:
                        raise ProtocolError('Partial response deadline')
                    continue
                if started is None:
                    started = time.monotonic()
                buffer.extend(chunk)
                if len(buffer) > MAX_FRAME:
                    raise ProtocolError('Response overflow')
                if chunk != b'\n':
                    continue
                frame = decode(bytes(buffer), 'R1')
                buffer.clear()
                started = None
                self._accept_response(frame)
        except (OSError, serial.SerialException, ProtocolError):
            if not self._stop.is_set():
                self._fault('INVALID_RESPONSE_OR_DISCONNECT')

    def _accept_response(self, frame):
        with self._state:
            if frame.session != self.session:
                raise ProtocolError('Response from another session')
            pending = self._pending.get(frame.command_id)
            status, code, *data = frame.fields
            if pending is None:
                previous = self._history.get(frame.command_id)
                if previous and previous[0] == frame.generation:
                    if status == 'ACCEPTED' or previous[1] == frame.fields:
                        return
                raise ProtocolError('Uncorrelated or conflicting reply')
            if pending.generation != frame.generation:
                raise ProtocolError('Response generation mismatch')
            if pending.result is not None and pending.terminal is None:
                return  # A late ACK can never turn an uncertain write into success.
            if pending.terminal is not None:
                if status == 'ACCEPTED' or pending.terminal == frame.fields:
                    return
                raise ProtocolError('Conflicting terminal reply')
            if status == 'ACCEPTED':
                if pending.verb not in ('TAP', 'DOWN', 'UP', 'CANCEL', 'RELEASE', 'CLOSE', 'BEGIN') or code != 'OK' or data:
                    raise ProtocolError('Invalid acceptance')
                return
            if status == 'DONE':
                expected = {'HELLO': 'READY', 'HB': 'ALIVE', 'CANCEL': 'CANCELLED',
                            'RELEASE': 'RELEASED'}.get(pending.verb, 'OK')
                if code != expected or (data and pending.verb != 'HELLO'):
                    raise ProtocolError('Invalid completion')
                if pending.verb == 'HELLO':
                    self.capabilities = Capabilities.parse(data)
                outcome = Outcome.COMPLETED
            elif status == 'REJECTED':
                if data or code not in {'BAD_ARGUMENT', 'BUSY', 'STALE_GENERATION', 'BAD_SESSION',
                                       'UNSUPPORTED_VERSION', 'UNSUPPORTED_USAGE', 'STALE_ID',
                                       'SESSION_CONFLICT', 'CANCELLED_BEFORE_DOWN', 'UNKNOWN_COMMAND'}:
                    raise ProtocolError('Invalid rejection')
                outcome = Outcome.NOT_EXECUTED
            else:
                if data or code != 'IO_UNCERTAIN':
                    raise ProtocolError('Invalid uncertain result')
                outcome = Outcome.UNKNOWN
            pending.terminal = frame.fields
            pending.result = self._result(outcome, code, frame.command_id, frame.generation)
            pending.event.set()
            if outcome is Outcome.UNKNOWN or code in ('STALE_ID', 'SESSION_CONFLICT', 'BAD_SESSION'):
                self._fault('SESSION_UNCERTAIN')

    def _heartbeat_loop(self):
        while not self._heartbeat_stop.wait(0.1):
            result = self._request('HB', 0)
            if not result.completed:
                self._fault('HEARTBEAT_FAILED')
                return

    def begin(self, generation):
        uint32(generation, positive=True)
        if not self._hid.acquire(blocking=False):
            return self._result(Outcome.NOT_EXECUTED, 'BUSY', 0, generation)
        try:
            with self._state:
                if generation <= self._fence or self._generation:
                    return self._result(Outcome.NOT_EXECUTED, 'STALE_GENERATION', 0, generation)
                self._fence = generation
                epoch = self._epoch
            result = self._request('BEGIN', generation)
            with self._state:
                if result.completed and self._healthy and self._fence == generation and self._epoch == epoch:
                    self._generation = generation
            return result
        finally:
            self._hid.release()

    def _key(self, verb, generation, *args):
        uint32(generation, positive=True)
        if not self._hid.acquire(blocking=False):
            return self._result(Outcome.NOT_EXECUTED, 'BUSY', 0, generation)
        try:
            return self._request(verb, generation, *args)
        finally:
            self._hid.release()

    @staticmethod
    def _validate_key(usage, modifiers):
        if type(usage) is not int or not 4 <= usage <= 115 or type(modifiers) is not int or not 0 <= modifiers <= 255:
            raise ValueError('Raw HID usage 4..115 and modifier mask 0..255 required')

    def tap(self, generation, usage, modifiers=0, hold_ms=10):
        self._validate_key(usage, modifiers)
        if type(hold_ms) is not int or not 1 <= hold_ms <= 100:
            raise ValueError('Hold must be 1..100ms')
        return self._key('TAP', generation, usage, modifiers, hold_ms)

    def down(self, generation, usage, modifiers=0):
        self._validate_key(usage, modifiers)
        return self._key('DOWN', generation, usage, modifiers)

    def up(self, generation):
        return self._key('UP', generation)

    def cancel(self, generation):
        uint32(generation, positive=True)
        with self._state:
            self._epoch += 1
            self._fence = max(self._fence, generation)
            # CANCEL only invalidates <=generation; cannot cancel a newer job.
            if self._generation <= generation:
                self._generation = 0
        return self._request('CANCEL', generation)

    def release(self):
        with self._state:
            self._epoch += 1
            self._generation = 0
        return self._request('RELEASE', 0)

    def close(self, *, timeout=1.0):
        if not 0 <= timeout <= 1:
            raise ValueError('Close deadline must be 0..1 second')
        with self._state:
            if self._closing or self._closed:
                return
            self._closing = True
            self._generation = 0
        deadline = time.monotonic() + timeout
        self._heartbeat_stop.set()
        if not self._stop.is_set() and self._reader_thread is not None:
            self._request('CLOSE', 0, timeout=max(0, deadline-time.monotonic()))
        self._stop.set()
        self._fault('CLOSED')
        # pyserial cancellation wakes native pending I/O before closing handles.
        for name in ('cancel_read', 'cancel_write'):
            method = getattr(self._serial, name, None)
            if method:
                try:
                    method()
                except (OSError, serial.SerialException):
                    pass
        self._serial.close()
        for thread in (self._reader_thread, self._heartbeat_thread):
            if thread and thread is not threading.current_thread():
                thread.join(max(0, deadline-time.monotonic()))
        with self._state:
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

import queue
import threading
import time

import pytest
import serial
from arduino_hid_emulator import HidDevice, Outcome, ConnectionError
from arduino_hid_emulator.protocol import decode, encode


class FakeSerial:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.rx = queue.Queue()
        self.writes = []
        self.closed = False
        self.on_command = None
        self.fail_write = False
        self.partial_write = False

    def reply(self, frame, status='DONE', code='OK', data='', delay=0):
        def send():
            for byte in encode(f'R1 {frame.session} {frame.command_id} {frame.generation} {status} {code}' + (' '+data if data else '')):
                self.rx.put(bytes([byte]))
        if delay:
            threading.Timer(delay, send).start()
        else:
            send()

    def write(self, data):
        self.writes.append(data)
        if self.fail_write:
            raise serial.SerialException('simulated partial driver failure')
        if self.partial_write:
            return len(data)//2
        frame = decode(data, 'Q1')
        if frame.fields[0] == 'HELLO':
            self.reply(frame, code='READY', data='1 1.0.0 0000003F 128 0 1000 100')
        elif self.on_command is not None and self.on_command(frame):
            pass
        else:
            self.reply(frame, code={'CANCEL':'CANCELLED', 'HB':'ALIVE', 'RELEASE':'RELEASED'}.get(frame.fields[0], 'OK'))
        return len(data)

    def read(self, size):
        try:
            return self.rx.get(timeout=0.005)
        except queue.Empty:
            return b''

    def reset_input_buffer(self):
        pass

    def reset_output_buffer(self):
        pass

    def close(self):
        self.closed = True


@pytest.fixture
def device(monkeypatch):
    # Skip only the lease-drain sleep, not event/response deadlines.
    monkeypatch.setattr('arduino_hid_emulator.device.time.sleep', lambda _: None)
    transport = FakeSerial()
    client = HidDevice('MOCK', command_timeout=0.1, serial_factory=lambda **kw: transport, heartbeat=False)
    yield client, transport
    client.close()


def test_exact_completion_and_explicit_outcome(device):
    client, transport = device
    assert client.capabilities.flags == 0x3F
    assert client.begin(1).completed
    result = client.tap(1, 4)
    assert result.outcome is Outcome.COMPLETED
    with pytest.raises(TypeError):
        bool(result)
    assert client.cancel(1).completed
    assert client.tap(1, 4).outcome is Outcome.NOT_EXECUTED
    assert client.begin(2).completed
    assert client.release().completed
    assert client.tap(2, 4).outcome is Outcome.NOT_EXECUTED


@pytest.mark.parametrize('mode', ['ack_lost', 'accepted_only', 'partial', 'disconnect', 'bad_crc', 'wrong_generation', 'wrong_session', 'wrong_code', 'late'])
def test_uncertain_commands_are_never_retried(device, mode):
    client, transport = device
    client.begin(1)
    def command(frame):
        if frame.fields[0] != 'TAP':
            return False
        if mode == 'accepted_only':
            transport.reply(frame, 'ACCEPTED')
        elif mode == 'bad_crc':
            for byte in b'R1 0123456789ABCDEF 3 1 DONE OK *0000\n':
                transport.rx.put(bytes([byte]))
        elif mode in ('wrong_generation', 'wrong_session'):
            gen = 2 if mode == 'wrong_generation' else frame.generation
            session = 'FFFFFFFFFFFFFFFF' if mode == 'wrong_session' else frame.session
            for byte in encode(f'R1 {session} {frame.command_id} {gen} DONE OK'):
                transport.rx.put(bytes([byte]))
        elif mode == 'wrong_code':
            transport.reply(frame, code='ALIVE')
        elif mode == 'late':
            transport.reply(frame, delay=0.15)
        return True
    transport.on_command = command
    transport.partial_write = mode == 'partial'
    transport.fail_write = mode == 'disconnect'
    result = client.tap(1, 4)
    assert result.outcome is Outcome.UNKNOWN
    assert not client.healthy
    assert client.tap(1, 4).outcome is Outcome.NOT_EXECUTED
    taps = [x for x in transport.writes if decode(x, 'Q1').fields[0] == 'TAP']
    assert len(taps) == 1


def test_cancel_during_pending_tap_does_not_wait_for_tap_ack(device):
    client, transport = device
    client.begin(1)
    accepted = threading.Event()
    def command(frame):
        if frame.fields[0] == 'TAP':
            transport.reply(frame, 'ACCEPTED')
            accepted.set()
            transport.reply(frame, delay=0.06)
            return True
        return False
    transport.on_command = command
    results=[]
    worker=threading.Thread(target=lambda: results.append(client.tap(1,4,hold_ms=100)))
    worker.start()
    assert accepted.wait(0.2)
    started=time.monotonic()
    assert client.cancel(1).completed
    assert time.monotonic()-started < 0.05
    assert client.tap(1,5).outcome is Outcome.NOT_EXECUTED
    worker.join(0.3)
    assert results[0].completed


def test_terminal_duplicate_and_late_acceptance_are_ignored(device):
    client, transport = device
    client.begin(1)
    def command(frame):
        if frame.fields[0] == 'TAP':
            transport.reply(frame)
            transport.reply(frame)
            transport.reply(frame, 'ACCEPTED')
            return True
        return False
    transport.on_command=command
    assert client.tap(1,4).completed
    assert client.tap(1,5).completed
    assert client.healthy


def test_conflicting_reply_faults_session(device):
    client,transport=device
    client.begin(1)
    def command(frame):
        if frame.fields[0]=='TAP':
            transport.reply(frame)
            transport.reply(frame,'REJECTED','BUSY')
            return True
        return False
    transport.on_command=command
    client.tap(1,4)
    deadline=time.monotonic()+0.2
    while client.healthy and time.monotonic()<deadline:
        threading.Event().wait(0.005)
    assert not client.healthy


def test_cancel_while_begin_ack_is_pending_does_not_rearm(device):
    client,transport=device
    received=threading.Event()
    def command(frame):
        if frame.fields[0]=='BEGIN':
            received.set()
            transport.reply(frame,delay=0.06)
            return True
        return False
    transport.on_command=command
    worker=threading.Thread(target=lambda:client.begin(1))
    worker.start(); assert received.wait(0.2)
    assert client.cancel(1).completed
    worker.join(0.3)
    assert client.tap(1,4).outcome is Outcome.NOT_EXECUTED


def test_validation_prevents_any_write(device):
    client,transport=device
    before=len(transport.writes)
    for args in [(3,0,10),(116,0,10),(4,256,10),(4,0,101),(True,0,10)]:
        with pytest.raises(ValueError):
            client.tap(1,*args)
    assert len(transport.writes)==before


def test_required_port_and_timeout_profile():
    with pytest.raises(ValueError):
        HidDevice('')
    with pytest.raises(ValueError):
        HidDevice('COM3',command_timeout=60)


def test_heartbeat_continues_while_user_is_idle(monkeypatch):
    monkeypatch.setattr('arduino_hid_emulator.device.time.sleep', lambda _: None)
    transport=FakeSerial()
    client=HidDevice('MOCK',serial_factory=lambda **kw:transport)
    try:
        assert client.begin(1).completed
        threading.Event().wait(0.35)
        assert len([w for w in transport.writes if decode(w,'Q1').fields[0]=='HB'])>=2
        assert client.healthy
    finally:
        client.close()


def test_close_cancels_pending_without_hid_replay(device):
    client,transport=device
    client.begin(1)
    accepted=threading.Event()
    def command(frame):
        if frame.fields[0]=='TAP':
            accepted.set()
            return True
        return False
    transport.on_command=command
    values=[]
    worker=threading.Thread(target=lambda:values.append(client.tap(1,4)))
    worker.start(); assert accepted.wait(.2)
    started=time.perf_counter()
    client.close()
    worker.join(.2)
    count=len(transport.writes)
    client.close()
    assert len(transport.writes)==count
    assert transport.closed
    assert time.perf_counter()-started<1.05
    assert values[0].outcome is Outcome.UNKNOWN


def test_new_instance_has_new_nonce_and_no_generation(monkeypatch):
    monkeypatch.setattr('arduino_hid_emulator.device.time.sleep', lambda _: None)
    first=HidDevice('MOCK',serial_factory=FakeSerial,heartbeat=False)
    assert first.begin(1).completed
    first.close()
    second=HidDevice('MOCK',serial_factory=FakeSerial,heartbeat=False)
    try:
        assert second.session!=first.session
        assert second.tap(1,4).outcome is Outcome.NOT_EXECUTED
        assert second._serial.kwargs=={'port':'MOCK','baudrate':115200,'timeout':.05,'write_timeout':.1}
    finally:
        second.close()


def test_stalled_open_has_one_bounded_waiter():
    released=threading.Event()
    transport=FakeSerial()
    def stalled(**kw):
        released.wait(5)
        return transport
    try:
        started=time.perf_counter()
        with pytest.raises(ConnectionError,match='deadline'):
            HidDevice('MOCK',open_timeout=1.2,serial_factory=stalled)
        assert time.perf_counter()-started<1.5
        with pytest.raises(ConnectionError,match='outstanding'):
            HidDevice('MOCK',serial_factory=FakeSerial)
    finally:
        released.set()
        deadline=time.monotonic()+.5
        while not transport.closed and time.monotonic()<deadline:
            threading.Event().wait(.01)
    assert transport.closed

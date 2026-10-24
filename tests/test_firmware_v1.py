"""Execute the same C++ Engine.h used by the Leonardo sketch, with fake USB/time."""
import ctypes
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest
from arduino_hid_emulator.protocol import decode, request

SID = '0123456789ABCDEF'


@pytest.fixture(scope='session')
def native_library(tmp_path_factory):
    root=Path(__file__).resolve().parents[1]
    if not importlib.util.find_spec('ziglang'):
        pytest.skip('Native Engine tests require ziglang==0.14.1; hardware tests are separate')
    binary=tmp_path_factory.mktemp('hid-engine')/('engine.dll' if os.name=='nt' else 'engine.so')
    subprocess.run([sys.executable,'-m','ziglang','c++','-std=c++11','-shared','-O1',
                    str(root/'tests/native/engine_harness.cpp'),'-o',str(binary)],
                   check=True,capture_output=True,timeout=180)
    lib=ctypes.CDLL(str(binary))
    lib.feed_engine.argtypes=[ctypes.c_char_p,ctypes.c_uint]
    lib.tick_engine.argtypes=[ctypes.c_uint,ctypes.c_int]
    lib.get_output.restype=ctypes.c_char_p
    lib.report_count.restype=ctypes.c_uint
    lib.report_at.argtypes=[ctypes.c_uint]
    lib.report_at.restype=ctypes.c_uint
    return lib


class Engine:
    def __init__(self,lib):
        self.lib=lib
        self.now=0
        self.next_id=1
        lib.reset_engine()

    def send(self,verb,gen=0,*args,tick=True,command_id=None,session=SID):
        command_id=self.next_id if command_id is None else command_id
        self.next_id=max(self.next_id,command_id+1)
        self.lib.feed_engine(request(session,command_id,gen,verb,*args),self.now)
        if tick:
            self.tick(0)
        return self.replies()

    def tick(self,delta,connected=True):
        self.now+=delta
        self.lib.tick_engine(self.now,int(connected))

    def replies(self):
        data=self.lib.get_output()
        self.lib.clear_output()
        return [decode(line+b'\n','R1') for line in data.splitlines()]

    def reports(self):
        return [self.lib.report_at(i) for i in range(self.lib.report_count())]


@pytest.fixture
def engine(native_library):
    e=Engine(native_library)
    assert e.send('HELLO',0,1)[0].fields==('DONE','READY','1','1.0.0','0000003F','128','0','1000','100')
    assert e.send('BEGIN',1)[0].fields==('DONE','OK')
    return e


def test_tap_exact_raw_report_and_completion(engine):
    assert engine.send('TAP',1,4,2,10)[0].fields==('ACCEPTED','OK')
    assert engine.reports()==[0x0204]
    engine.tick(9); assert engine.replies()==[]
    engine.tick(1); assert engine.replies()[0].fields==('DONE','OK')
    assert engine.reports()==[0x0204,0]


def test_cancel_before_down_and_generation_fence(engine):
    engine.send('TAP',1,4,0,10,tick=False)
    replies=engine.send('CANCEL',1)
    assert [r.fields for r in replies]==[('REJECTED','CANCELLED_BEFORE_DOWN'),('DONE','CANCELLED')]
    assert engine.reports()==[0]
    assert engine.send('TAP',1,4,0,10)[0].fields==('REJECTED','STALE_GENERATION')
    assert engine.send('BEGIN',1)[0].fields==('REJECTED','STALE_GENERATION')
    assert engine.send('BEGIN',2)[0].fields==('DONE','OK')
    assert engine.send('CANCEL',1)[0].fields==('DONE','CANCELLED')
    assert engine.lib.is_armed()


def test_cancel_after_down_finishes_only_up(engine):
    engine.send('TAP',1,4,0,100)
    replies=engine.send('CANCEL',1)
    assert [r.fields for r in replies]==[('DONE','OK'),('DONE','CANCELLED')]
    engine.tick(500)
    assert engine.reports()==[4,0]
    assert not engine.lib.is_held()


def test_busy_has_no_hid_queue(engine):
    engine.send('TAP',1,4,0,10)
    assert engine.send('TAP',1,5,0,10)[0].fields==('REJECTED','BUSY')
    engine.tick(10)
    assert engine.reports()==[4,0]


def test_down_auto_release_and_explicit_up(engine):
    replies=engine.send('DOWN',1,4,1)
    assert [r.fields for r in replies]==[('ACCEPTED','OK'),('DONE','OK')]
    engine.tick(99); assert engine.lib.is_held()
    engine.tick(1); assert not engine.lib.is_held()
    assert engine.reports()==[0x0104,0]
    engine.send('DOWN',1,5,0)
    assert engine.send('UP',1)[0].fields==('DONE','OK')
    assert engine.reports()==[0x0104,0,5,0]


def test_duplicate_does_not_repeat_and_conflict_disarms(engine):
    engine.send('TAP',1,4,0,10,command_id=3)
    assert engine.send('TAP',1,4,0,10,command_id=3)[0].fields==('ACCEPTED','OK')
    engine.tick(10); engine.replies()
    assert engine.send('TAP',1,4,0,10,command_id=3)[0].fields==('DONE','OK')
    assert engine.reports()==[4,0]
    assert engine.send('TAP',1,5,0,10,command_id=3)[0].fields==('REJECTED','SESSION_CONFLICT')
    assert not engine.lib.is_armed()
    assert engine.reports()[-1]==0


def test_old_result_eviction_rejects_without_replay(engine):
    engine.send('TAP',1,4,0,10,command_id=3)
    engine.tick(10); engine.replies()
    for _ in range(5):
        engine.send('HB')
    assert engine.send('TAP',1,4,0,10,command_id=3)[0].fields==('REJECTED','STALE_ID')
    assert engine.reports()==[4,0]


@pytest.mark.parametrize('verb,args', [('TAP',(3,0,10)),('TAP',(116,0,10)),('TAP',(4,256,10)),
                                       ('TAP',(4,0,0)),('TAP',(4,0,101)),('DOWN',(4,999))])
def test_bad_keys_are_rejected_before_down(engine,verb,args):
    assert engine.send(verb,1,*args)[0].fields[0]=='REJECTED'
    assert engine.reports()==[]


def test_lease_and_usb_loss_invalidate_old_commands(engine):
    engine.send('TAP',1,4,0,100)
    engine.tick(1000)
    assert not engine.lib.is_armed()
    assert engine.reports()==[4,0]
    assert engine.send('TAP',1,5,0,10)[0].fields==('REJECTED','BAD_SESSION')
    assert engine.send('HELLO',0,1,session='FEDCBA9876543210')[0].fields[0]=='DONE'
    engine.tick(0,False)
    assert not engine.lib.is_armed()
    assert engine.send('BEGIN',1,session='FEDCBA9876543210')[0].fields==('REJECTED','BAD_SESSION')


def test_heartbeat_keeps_long_pause_alive(engine):
    for _ in range(30):
        engine.tick(100)
        assert engine.send('HB')[0].fields==('DONE','ALIVE')
    assert engine.lib.is_armed()
    assert engine.reports()==[]


def test_endpoint_stall_cannot_make_late_down(engine):
    engine.lib.set_io(1)
    engine.send('TAP',1,4,0,10)
    engine.tick(20)
    assert engine.replies()[0].fields==('UNKNOWN','IO_UNCERTAIN')
    assert not engine.lib.is_armed()
    engine.lib.set_io(0)
    engine.tick(100)
    assert engine.reports()==[0]


def test_failed_release_never_reports_success(engine):
    engine.send('TAP',1,4,0,10)
    engine.lib.set_io(1)
    engine.send('CANCEL',1)
    engine.tick(20)
    assert [r.fields for r in engine.replies()]==[('UNKNOWN','IO_UNCERTAIN'),('UNKNOWN','IO_UNCERTAIN')]
    engine.lib.set_io(0); engine.tick(1)
    assert engine.reports()==[4,0]


def test_tx_backpressure_cancels_pending_down(engine):
    engine.lib.set_writable(0)
    engine.send('TAP',1,4,0,10)
    engine.lib.set_writable(1); engine.tick(1)
    assert not engine.lib.is_armed()
    assert all(report==0 for report in engine.reports())


@pytest.mark.parametrize('payload', [
    b'X'*200+b'\n', b'Q1 0123456789ABCDEF 3 1 TAP 4 0 10 *0000\n',
    b'key_press a\n', b'\xff\n',
])
def test_malformed_frames_do_not_type(engine,payload):
    engine.lib.feed_engine(payload,engine.now)
    engine.tick(1)
    assert engine.replies()==[]
    assert engine.reports()==[]
    assert engine.send('HB')[0].fields==('DONE','ALIVE')


def test_partial_frame_times_out_and_resynchronizes(engine):
    frame=request(SID,3,1,'TAP',4,0,10)
    engine.lib.feed_engine(frame[:10],engine.now)
    engine.tick(101)
    engine.lib.feed_engine(frame[10:],engine.now)
    engine.tick(1)
    assert engine.reports()==[]
    assert engine.send('HB',command_id=4)[0].fields==('DONE','ALIVE')


@pytest.mark.parametrize('args', [('04','0','10'),('4','00','10'),('4294967296','0','10'),
                                 ('4','0','010'),('4','0','10','99')])
def test_nonnumeric_or_extra_arguments_never_type(engine,args):
    assert engine.send('TAP',1,*args)[0].fields==('REJECTED','BAD_ARGUMENT')
    assert engine.reports()==[]


def test_release_and_close_disarm_and_allow_clean_handshake(engine):
    engine.send('DOWN',1,4,2)
    assert engine.send('RELEASE')[0].fields==('DONE','RELEASED')
    assert engine.send('TAP',1,4,0,10)[0].fields==('REJECTED','STALE_GENERATION')
    assert engine.send('BEGIN',2)[0].fields==('DONE','OK')
    assert engine.send('CLOSE')[0].fields==('DONE','OK')
    assert not engine.lib.is_armed()
    assert engine.send('BEGIN',3)[0].fields==('REJECTED','BAD_SESSION')
    assert engine.send('HELLO',0,1,session='FEDCBA9876543210')[0].fields[0]=='DONE'


def test_interrupt_hold_guard_expires_even_without_engine_ticks(native_library):
    lib=native_library
    lib.guard_commit(1)
    assert all(lib.guard_tick()==0 for _ in range(99))
    assert lib.guard_tick()==1
    assert lib.guard_tick()==1  # endpoint busy: keep requesting release
    lib.guard_commit(0)
    assert all(lib.guard_tick()==0 for _ in range(200))
